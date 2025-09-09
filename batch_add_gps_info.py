import os
import csv
import sys
import datetime
from PIL import Image
import piexif
from fractions import Fraction
import pandas as pd
import time
import glob

# 在打包版本中，完全禁用XMP功能，避免依赖exempi库
LIBXMP_AVAILABLE = False
if not getattr(sys, 'frozen', False):
    try:
        from libxmp import XMPFiles, consts
        from libxmp.core import XMPMeta, XMPError
        
        # 测试XMP库是否可用
        test_xmp = XMPMeta()
        LIBXMP_AVAILABLE = True
    except Exception as e:
        print(f"警告: XMP功能不可用: {str(e)}")
        print("将使用标准EXIF方法而非DJI XMP格式")
else:
    print("EXE打包模式: 已禁用DJI XMP格式支持，仅使用EXIF")

# 尝试导入OPT转换工具
try:
    from opt_converter import create_dji_dewarp_xmp, parse_opt_file
    OPT_CONVERTER_AVAILABLE = True
except ImportError:
    OPT_CONVERTER_AVAILABLE = False
    print("警告: 未找到opt_converter.py，无法使用相机畸变参数转换功能")

def decimal_to_dms(decimal):
    """将十进制度数转换为度分秒格式，用于GPS信息"""
    absolute = abs(decimal)
    degrees = int(absolute)
    minutes_float = (absolute - degrees) * 60
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60
    
    # 转换为EXIF中使用的分数格式
    degrees_fraction = (degrees, 1)
    minutes_fraction = (minutes, 1)
    seconds_fraction = (int(seconds * 100), 100)
    
    return [degrees_fraction, minutes_fraction, seconds_fraction]

def parse_timestamp(timestamp_str):
    """解析时间字符串，支持多种格式"""
    if not timestamp_str:
        return None
    
    # 尝试不同的时间格式
    formats = [
        '%Y-%m-%d %H:%M:%S',      # 标准格式：2024-08-18 10:30:00
        '%Y-%m-%d_%H:%M:%S',      # 下划线格式：2020-10-18_12:19:00
        '%Y/%m/%d %H:%M:%S',      # 斜杠格式
        '%Y-%m-%d %H-%M-%S',      # 连字符格式
    ]
    
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(timestamp_str, fmt)
            return dt.strftime('%Y:%m:%d %H:%M:%S')  # 返回EXIF标准格式
        except ValueError:
            continue
    
    print(f"时间格式错误: 无法解析时间格式 '{timestamp_str}'")
    return None

def detect_csv_format(csv_file):
    """检测CSV文件格式：是否有表头"""
    try:
        with open(csv_file, 'r', encoding='utf-8-sig') as f:
            first_line = f.readline().strip()
            # 如果第一行包含这些关键词，认为是有表头的格式
            if any(keyword in first_line.lower() for keyword in 
                   ['文件名', 'filename', '纬度', '经度', 'latitude', 'longitude', 'lat', 'lng', 'lon']):
                return 'with_header'
            else:
                return 'no_header'
    except:
        return 'no_header'

def normalize_angle(angle):
    """标准化角度值到 0-360 度范围"""
    if angle is None:
        return 0
    
    # 将角度标准化到 0-360 范围
    while angle < 0:
        angle += 360
    while angle >= 360:
        angle -= 360
    
    return angle

def create_dji_xmp(lat, lng, alt, roll, pitch, yaw, timestamp=None, opt_file=None, opt_data=None):
    """创建DJI格式的XMP元数据"""
    if not LIBXMP_AVAILABLE:
        return None
    
    try:    
        xmp = XMPMeta()
        
        # 设置基本命名空间
        DJI_NS = "http://www.dji.com/drone-dji/1.0/"
        xmp.register_namespace(DJI_NS, "drone-dji")
        
        # 设置经纬度和高度
        xmp.set_property(DJI_NS, "drone-dji:GpsLatitude", f"{lat}")
        xmp.set_property(DJI_NS, "drone-dji:GpsLongtitude", f"{lng}")  # DJI使用Longtitude而不是Longitude
        xmp.set_property(DJI_NS, "drone-dji:AbsoluteAltitude", f"{alt}")
        
        # 设置姿态角（飞行器姿态）
        xmp.set_property(DJI_NS, "drone-dji:FlightRollDegree", f"{roll}")
        xmp.set_property(DJI_NS, "drone-dji:FlightPitchDegree", f"{pitch}")
        xmp.set_property(DJI_NS, "drone-dji:FlightYawDegree", f"{yaw}")
        
        # 写入焦距信息到XMP
        try:
            if opt_data and 'FocalLength' in opt_data:
                actual_focal = opt_data.get('FocalLength')
                # 设置实际焦距
                xmp.set_property(consts.XMP_NS_EXIF, 'exif:FocalLength', f"{actual_focal}")
                
                # 计算并设置35mm等效焦距
                if 'SensorSize' in opt_data and opt_data.get('SensorSize') > 0:
                    sensor_size = opt_data.get('SensorSize')
                    equiv_focal = int(round(actual_focal * (35.0 / sensor_size)))
                    xmp.set_property(consts.XMP_NS_EXIF, 'exif:FocalLengthIn35mmFilm', f"{equiv_focal}")
            elif opt_file and OPT_CONVERTER_AVAILABLE:
                # 如果没有传递opt_data但有opt_file，尝试解析
                opt_data = parse_opt_file(opt_file)
                if opt_data and 'FocalLength' in opt_data:
                    actual_focal = opt_data.get('FocalLength')
                    xmp.set_property(consts.XMP_NS_EXIF, 'exif:FocalLength', f"{actual_focal}")
                    
                    if 'SensorSize' in opt_data and opt_data.get('SensorSize') > 0:
                        sensor_size = opt_data.get('SensorSize')
                        equiv_focal = int(round(actual_focal * (35.0 / sensor_size)))
                        xmp.set_property(consts.XMP_NS_EXIF, 'exif:FocalLengthIn35mmFilm', f"{equiv_focal}")
        except Exception as e:
            print(f"XMP焦距写入失败: {e}")
        
        # 设置时间戳
        if timestamp:
            try:
                # 从EXIF格式的时间戳中提取日期和时间
                dt_parts = timestamp.split(" ")
                if len(dt_parts) == 2:
                    date_part = dt_parts[0].replace(":", "-")
                    time_part = dt_parts[1]
                    xmp_date = f"{date_part}T{time_part}"
                    
                    # 设置XMP日期时间
                    xmp.set_property(consts.XMP_NS_XMP, 'xmp:CreateDate', xmp_date)
                    xmp.set_property(consts.XMP_NS_XMP, 'xmp:ModifyDate', xmp_date)
            except Exception as e:
                print(f"XMP时间格式错误: {e}")
        
        # 如果提供了OPT文件，添加相机畸变参数
        if opt_file and OPT_CONVERTER_AVAILABLE:
            try:
                dewarp_data = create_dji_dewarp_xmp(opt_file)
                if dewarp_data:
                    for key, value in dewarp_data.items():
                        xmp.set_property(DJI_NS, key, value)
            except Exception as e:
                print(f"添加相机畸变参数失败: {e}")
        
        return xmp
    except Exception as e:
        print(f"创建DJI XMP元数据失败: {e}")
        return None

def set_gps_location(image_path, lat, lng, altitude=0, roll=0, pitch=0, yaw=0, timestamp=None, opt_file=None, output_path=None):
    """设置图片的GPS信息、姿态角和时间
    
    Args:
        image_path: 原始图片路径
        lat: 纬度
        lng: 经度
        altitude: 高度
        roll: 横滚角
        pitch: 俯仰角
        yaw: 偏航角
        timestamp: 时间戳
        opt_file: OPT文件路径
        output_path: 输出文件路径，若不提供则覆盖原图
    """
    try:
        # 解析时间戳
        parsed_time = None
        if timestamp:
            parsed_time = parse_timestamp(timestamp)
        
        # 标准化角度
        normalized_roll = float(roll) if roll is not None else 0
        normalized_pitch = float(pitch) if pitch is not None else 0
        normalized_yaw = normalize_angle(float(yaw)) if yaw is not None else 0
        
        # 从opt文件读取焦距和传感器大小
        focal_length = None
        focal_length_35mm_equiv = None
        if opt_file and os.path.exists(opt_file) and OPT_CONVERTER_AVAILABLE:
            try:
                opt_data = parse_opt_file(opt_file)
                if opt_data and 'FocalLength' in opt_data:
                    focal_length = opt_data.get('FocalLength')
                    # 计算35mm等效焦距
                    if 'SensorSize' in opt_data and opt_data.get('SensorSize') > 0:
                        sensor_size = opt_data.get('SensorSize')
                        # 35mm等效焦距 = 实际焦距 × (35 / 传感器尺寸)
                        focal_length_35mm_equiv = int(round(focal_length * (35.0 / sensor_size)))
                        print(f"计算35mm等效焦距: {focal_length_35mm_equiv}mm (实际焦距: {focal_length}mm, 传感器尺寸: {sensor_size}mm)")
                    else:
                        print("无法计算35mm等效焦距: 传感器尺寸缺失或无效")
            except Exception as e:
                print(f"读取焦距失败: {e}")
        
        # 1. 首先设置EXIF数据
        try:
            # 加载现有EXIF
            exif_dict = piexif.load(image_path)
        except:
            # 如果没有EXIF，创建新的
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        
        # 确保GPS字典存在
        if "GPS" not in exif_dict:
            exif_dict["GPS"] = {}
        
        # 设置GPS信息
        exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = decimal_to_dms(lat)
        exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = "N" if lat >= 0 else "S"
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = decimal_to_dms(lng)
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = "E" if lng >= 0 else "W"
        
        # 设置高度
        alt_value = abs(float(altitude))
        exif_dict["GPS"][piexif.GPSIFD.GPSAltitude] = (int(alt_value * 100), 100)
        exif_dict["GPS"][piexif.GPSIFD.GPSAltitudeRef] = 1 if altitude < 0 else 0
        
        # 设置方向（偏航角）
        exif_dict["GPS"][piexif.GPSIFD.GPSImgDirection] = (int(normalized_yaw * 100), 100)
        exif_dict["GPS"][piexif.GPSIFD.GPSImgDirectionRef] = "T"  # T表示真北
        
        # 写入焦距信息到EXIF
        if "Exif" not in exif_dict:
            exif_dict["Exif"] = {}
            
        # 设置实际焦距
        if focal_length is not None:
            # 将焦距转换为有理数格式
            focal_fraction = Fraction(focal_length).limit_denominator(1000)
            exif_dict["Exif"][piexif.ExifIFD.FocalLength] = (focal_fraction.numerator, focal_fraction.denominator)
            
        # 设置35mm等效焦距
        if focal_length_35mm_equiv is not None:
            exif_dict["Exif"][piexif.ExifIFD.FocalLengthIn35mmFilm] = focal_length_35mm_equiv
        
        # 设置时间戳
        if parsed_time:
            exif_dict["GPS"][piexif.GPSIFD.GPSDateStamp] = parsed_time.split(' ')[0].replace(':', '/')
            exif_dict["GPS"][piexif.GPSIFD.GPSTimeStamp] = tuple([
                (int(parsed_time.split(' ')[1].split(':')[0]), 1),  # 小时
                (int(parsed_time.split(' ')[1].split(':')[1]), 1),  # 分钟
                (int(parsed_time.split(' ')[1].split(':')[2]), 1)   # 秒钟
            ])
            # 设置拍摄时间到EXIF主字段
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = parsed_time
            exif_dict["0th"][piexif.ImageIFD.DateTime] = parsed_time
        
        # 在EXIF的UserComment中存储姿态角信息
        attitude_info = f"Roll={normalized_roll:.1f},Pitch={normalized_pitch:.1f},Yaw={normalized_yaw:.1f}"
        if "Exif" not in exif_dict:
            exif_dict["Exif"] = {}
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = attitude_info.encode('ascii', errors='replace')
        
        # 保存EXIF数据
        try:
            exif_bytes = piexif.dump(exif_dict)
        except Exception as e:
            print(f"EXIF数据序列化失败: {e}")
            return False
        
        # 2. 如果可用，再设置DJI XMP数据
        xmp = None
        # 提取opt_data以传递给XMP生成函数，避免重复解析
        opt_data_for_xmp = None
        if opt_file and os.path.exists(opt_file) and OPT_CONVERTER_AVAILABLE:
            try:
                if 'opt_data' in locals() and opt_data:
                    opt_data_for_xmp = opt_data
                else:
                    opt_data_for_xmp = parse_opt_file(opt_file)
            except Exception:
                pass
        
        if LIBXMP_AVAILABLE:
            xmp = create_dji_xmp(lat, lng, altitude, normalized_roll, normalized_pitch, normalized_yaw, parsed_time, opt_file, opt_data_for_xmp)
        
        # 确定输出路径
        save_path = output_path if output_path else image_path
        
        # 确保输出路径的目录存在
        output_dir = os.path.dirname(save_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 打印焦距信息，用于调试
        if focal_length is not None:
            print(f"写入实际焦距: {focal_length}mm")
        if focal_length_35mm_equiv is not None:
            print(f"写入35mm等效焦距: {focal_length_35mm_equiv}mm")
        
        # 调试：检查EXIF字典内容
        if focal_length is not None or focal_length_35mm_equiv is not None:
            print(f"EXIF焦距字段检查:")
            if piexif.ExifIFD.FocalLength in exif_dict["Exif"]:
                print(f"  - FocalLength: {exif_dict['Exif'][piexif.ExifIFD.FocalLength]}")
            if piexif.ExifIFD.FocalLengthIn35mmFilm in exif_dict["Exif"]:
                print(f"  - FocalLengthIn35mmFilm: {exif_dict['Exif'][piexif.ExifIFD.FocalLengthIn35mmFilm]}")
            
        # 3. 重新打开图像并保存带有EXIF的版本
        with Image.open(image_path) as img:
            img.save(save_path, "JPEG", exif=exif_bytes, quality=95)
        
        # 4. 如果有XMP数据，写入XMP
        if LIBXMP_AVAILABLE and xmp:
            try:
                xmpfile = XMPFiles(file_path=save_path, open_forupdate=True)
                if xmpfile.can_put_xmp(xmp):
                    xmpfile.put_xmp(xmp)
                    xmpfile.close_file()
            except Exception as e:
                print(f"XMP写入失败: {e}")
        
        return True
        
    except Exception as e:
        print(f"写入元数据失败: {e}")
        return False

def process_images_from_csv(csv_file, image_folder, opt_file=None, progress_callback=None, output_dir=None):
    """处理CSV文件并为对应图像添加地理信息
    支持4列或8列CSV，4列只写GPS和照片名，其他字段缺失时不写EXIF
    输出照片重命名为处理时的年月日时分秒加两位序号
    自动递归查找所有照片文件，支持大小写后缀和多级目录
    """
    def log(message):
        if progress_callback:
            progress_callback(message)
        else:
            print(message)

    success_count = 0
    failed_count = 0
    skipped_count = 0
    errors = []

    if not os.path.exists(csv_file):
        error_msg = f"CSV文件不存在: {csv_file}"
        log(error_msg)
        return {'success': 0, 'failed': 1, 'skipped': 0, 'errors': [error_msg]}

    if not os.path.exists(image_folder):
        error_msg = f"图像文件夹不存在: {image_folder}"
        log(error_msg)
        return {'success': 0, 'failed': 1, 'skipped': 0, 'errors': [error_msg]}

    try:
        df = pd.read_csv(csv_file, header=None, encoding='utf-8-sig')
    except Exception as e:
        error_msg = f"读取CSV文件失败: {e}"
        log(error_msg)
        return {'success': 0, 'failed': 1, 'skipped': 0, 'errors': [error_msg]}

    total_rows = len(df)
    log(f"开始处理 {total_rows} 条记录...")
    log("-" * 40)

    # 新增：递归查找所有照片文件，建立小写名到实际路径映射
    photo_map = {}
    for ext in ['jpg', 'jpeg', 'JPG', 'JPEG']:
        for f in glob.glob(os.path.join(image_folder, '**', f'*.{ext}'), recursive=True):
            photo_map[os.path.basename(f).lower()] = f

    # 新增：准备新CSV内容
    new_csv_rows = []
    csv_timestamp = time.strftime("%y%m%d%H%M%S")
    new_csv_name = f"{csv_timestamp}.csv"
    if output_dir:
        new_csv_path = os.path.join(output_dir, new_csv_name)
    else:
        new_csv_path = os.path.join(os.path.dirname(csv_file), new_csv_name)

    for i, (index, row) in enumerate(df.iterrows()):
        try:
            # 4列格式：纬度,经度,高度,文件名
            if len(row) == 4:
                latitude = float(row[0])
                longitude = float(row[1])
                altitude = int(float(row[2]))
                image_name = str(row[3]).strip()
                roll = pitch = yaw = 0
                timestamp = None
            # 8列格式：文件名,时间,经度,纬度,高度,Pitch,Roll,Yaw
            elif len(row) >= 8:
                image_name = str(row[0]).strip()
                timestamp = str(row[1]).strip()
                longitude = float(row[2])
                latitude = float(row[3])
                altitude = int(float(row[4])) if pd.notna(row[4]) else 0
                pitch = int(float(row[5])) if pd.notna(row[5]) else 0
                roll = int(float(row[6])) if pd.notna(row[6]) else 0
                yaw = int(float(row[7])) if pd.notna(row[7]) else 0
            else:
                log(f"第{i+1}行: CSV列数不足，仅支持4列或8列，跳过")
                failed_count += 1
                errors.append(f"第{i+1}行: 列数不足")
                continue

            if not image_name:
                log(f"第{i+1}行: 文件名为空，跳过")
                skipped_count += 1
                continue

            # 用小写查找实际路径
            image_path = photo_map.get(image_name.lower())
            if not image_path:
                log(f"第{i+1}行: 文件不存在: {image_name}")
                failed_count += 1
                errors.append(f"文件不存在: {image_name}")
                continue

            log(f"第{i+1}行: 处理 {image_name} ({latitude:.6f}, {longitude:.6f}, {altitude}m)")
            output_path = None
            if output_dir:
                # 生成处理时的时间戳+原照片名后四位
                current_timestamp = time.strftime("%y%m%d%H%M%S")
                # 提取原照片名（不含扩展名）后四位，不足补零
                base_name = os.path.splitext(image_name)[0]
                last4 = base_name[-4:].rjust(4, '0')
                new_filename = f"{current_timestamp}{last4}.jpg"
                output_path = os.path.join(output_dir, new_filename)
                log(f"  原文件名: {image_name} -> 新文件名: {new_filename}")

            # 只写有的EXIF字段
            from batch_add_gps_info import set_gps_location
            if set_gps_location(image_path, latitude, longitude, altitude, roll, pitch, yaw, timestamp, opt_file, output_path):
                success_count += 1
                log(f"  ✓ 成功 (已保存至: {new_filename})" if output_path else "  ✓ 成功")
            else:
                failed_count += 1
                errors.append(f"EXIF写入失败: {image_name}")
                log(f"  ✗ 失败")
            
            # 新增：记录新CSV行
            new_row = list(row) + [new_filename if output_dir else image_name]
            new_csv_rows.append(new_row)
        except Exception as e:
            failed_count += 1
            errors.append(f"第{i+1}行处理错误: {str(e)}")
            log(f"第{i+1}行: 错误 - {str(e)}")

    # 新增：写入新CSV
    try:
        with open(new_csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            # 写表头（原表头+新照片名），如无表头则用默认
            if hasattr(df, 'columns') and df.columns is not None:
                header = [f"列{i+1}" for i in range(len(df.columns))] + ["新照片名"]
                writer.writerow(header)
            else:
                writer.writerow(["新照片名"])
            writer.writerows(new_csv_rows)
        log(f"已生成新旧照片名对照表: {new_csv_path}")
    except Exception as e:
        log(f"新CSV写入失败: {e}")

    log("-" * 40)
    log(f"处理完成: 成功={success_count}, 失败={failed_count}, 跳过={skipped_count}")
    return {
        'success': success_count,
        'failed': failed_count,
        'skipped': skipped_count,
        'errors': errors
    }

def create_sample_csv(csv_path):
    """创建一个示例CSV文件"""
    sample_data = [
        {
            '文件名': 'IMG_001.jpg',
            '纬度': 39.9042135,
            '经度': 116.4074582,
            '高度': 100.25,
            'Roll': 15.2,
            'Pitch': 8.7,
            'Yaw': 45.0,
            '时间': '2024-08-18 10:30:00'
        },
        {
            '文件名': 'IMG_002.jpg',
            '纬度': 39.9050248,
            '经度': 116.4080693,
            '高度': 102.30,
            'Roll': 12.8,
            'Pitch': 6.3,
            'Yaw': 90.5,
            '时间': '2024-08-18 10:31:00'
        }
    ]
    
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        fieldnames = ['文件名', '纬度', '经度', '高度', 'Roll', 'Pitch', 'Yaw', '时间']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sample_data)
    
    print(f"已创建示例CSV文件: {csv_path}")

def main():
    """主函数"""
    print("=" * 40)
    print("JPG照片地理信息批量添加工具")
    print("=" * 40)
    
    while True:
        print("\n请选择操作:")
        print("1. 批量处理图片")
        print("2. 创建示例CSV文件")
        print("3. 退出")
        
        choice = input("\n请输入选择 (1-3): ").strip()
        
        if choice == '1':
            csv_file = input("请输入CSV文件路径: ").strip().strip('"')
            image_folder = input("请输入图像文件夹路径: ").strip().strip('"')
            
            if csv_file and image_folder:
                process_images_from_csv(csv_file, image_folder)
            else:
                print("路径不能为空!")
                
        elif choice == '2':
            csv_path = input("请输入要创建的CSV文件路径 (如: sample.csv): ").strip().strip('"')
            if csv_path:
                create_sample_csv(csv_path)
            else:
                print("文件路径不能为空!")
                
        elif choice == '3':
            print("再见!")
            break
            
        else:
            print("无效选择，请重新输入!")

if __name__ == "__main__":
    main()
