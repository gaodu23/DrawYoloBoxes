import os
import shutil

# YOLO检测完第一遍，删掉0kb文本，移动相应文件到未检测出文件夹。
# 下一步进行人工核对。核对后再运行一遍本程序进行二次删除。
# 再下一步标注上红框。

# 定义基础文件夹路径
# base_dir = r'd:\yolo\XY-YOLO-Tools\train_data\0904'
# base_dir = r'd:\yolo\XY-YOLO-Tools\train_data\0906'
# base_dir = r'D:\yolo\XY-YOLO-Tools\train_data\YIHEDUI\0908'
# base_dir = r'd:\yolo\XY-YOLO-Tools\train_data\0908'
# base_dir = r'd:\yolo\XY-YOLO-Tools\train_data\0909'

# base_dir = r'd:\yolo\XY-YOLO-Tools\train_data\YIHEDUI\0904'
base_dir = r'd:\yolo\XY-YOLO-Tools\train_data\YIHEDUI\90431'
# base_dir = r'd:\yolo\XY-YOLO-Tools\train_data\YIHEDUI\90634'
# base_dir = r'd:\yolo\XY-YOLO-Tools\train_data\YIHEDUI\0908'
# base_dir = r'd:\yolo\XY-YOLO-Tools\train_data\YIHEDUI\0909'

labels_dir = os.path.join(base_dir, 'labels')
images_dir = os.path.join(base_dir, 'images')
unchecked_dir = os.path.join(base_dir, '未检出')

# 创建未检出文件夹（如果不存在）
if not os.path.exists(unchecked_dir):
    os.makedirs(unchecked_dir)
    print(f"已创建文件夹: {unchecked_dir}")

# 遍历labels文件夹中的所有文件
for label_file in os.listdir(labels_dir):
    if label_file.endswith('.txt'):
        label_path = os.path.join(labels_dir, label_file)
        
        # 检查文件大小是否为0KB
        if os.path.getsize(label_path) == 0:
            print(f"找到0KB文件: {label_file}")
            
            # 删除0KB的标签文件
            os.remove(label_path)
            print(f"已删除: {label_file}")
            
            # 移动对应的图片文件到未检出文件夹
            image_name = os.path.splitext(label_file)[0]
            for ext in ['.jpg', '.jpeg', '.png']:
                image_file = image_name + ext
                image_path = os.path.join(images_dir, image_file)
                
                if os.path.exists(image_path):
                    unchecked_image_path = os.path.join(unchecked_dir, image_file)
                    shutil.move(image_path, unchecked_image_path)
                    print(f"已移动对应的图片到未检出文件夹: {image_file}")
                    break

# 新增：尝试导入 piexif 用于读取 EXIF GPS
try:
    import piexif
    _PIEXIF_AVAILABLE = True
except ImportError:
    _PIEXIF_AVAILABLE = False

# 新增：获取图片GPS (lat, lon)
def get_image_gps(image_path):
    if not _PIEXIF_AVAILABLE:
        return None
        
    try:
        exif_dict = piexif.load(image_path)
        if "GPS" in exif_dict and exif_dict["GPS"]:
            gps = exif_dict["GPS"]
            if all(tag in gps for tag in [piexif.GPSIFD.GPSLatitude, 
                                         piexif.GPSIFD.GPSLatitudeRef,
                                         piexif.GPSIFD.GPSLongitude,
                                         piexif.GPSIFD.GPSLongitudeRef]):
                # 读取纬度
                lat_ref = gps[piexif.GPSIFD.GPSLatitudeRef].decode('ascii')
                lat = gps[piexif.GPSIFD.GPSLatitude]
                lat_deg = lat[0][0] / lat[0][1]
                lat_min = lat[1][0] / lat[1][1]
                lat_sec = lat[2][0] / lat[2][1]
                lat_val = lat_deg + (lat_min / 60.0) + (lat_sec / 3600.0)
                if lat_ref == 'S':
                    lat_val = -lat_val
                
                # 读取经度
                lon_ref = gps[piexif.GPSIFD.GPSLongitudeRef].decode('ascii')
                lon = gps[piexif.GPSIFD.GPSLongitude]
                lon_deg = lon[0][0] / lon[0][1]
                lon_min = lon[1][0] / lon[1][1]
                lon_sec = lon[2][0] / lon[2][1]
                lon_val = lon_deg + (lon_min / 60.0) + (lon_sec / 3600.0)
                if lon_ref == 'W':
                    lon_val = -lon_val
                
                return lat_val, lon_val
    except Exception as e:
        print(f"读取GPS失败 {os.path.basename(image_path)}: {str(e)}")
        
    return None

# 新增：生成 KML 文件
def generate_kml(image_dir, kml_path, folder_name='Images'):
    placemarks = []
    count_total = 0
    count_with_gps = 0
    no_gps_count = 0
    for fname in sorted(os.listdir(image_dir)):
        if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
            count_total += 1
            fpath = os.path.join(image_dir, fname)
            gps = get_image_gps(fpath)
            if not gps:
                no_gps_count += 1
                if no_gps_count <= 5:  # 只打印前5个无GPS的文件
                    print(f"无GPS: {fname}")
                elif no_gps_count == 6:
                    print("更多无GPS文件省略显示...")
                continue
            count_with_gps += 1
            lat, lon = gps
            placemark = f"""
        <Placemark>
            <name>{fname}</name>
            <Point><coordinates>{lon},{lat},0</coordinates></Point>
        </Placemark>"""
            placemarks.append(placemark)
    
    # 如果没有GPS数据，添加提示信息
    if count_with_gps == 0:
        placemark = f"""
        <Placemark>
            <name>无GPS数据</name>
            <description>文件夹中的{count_total}张图片均无GPS信息。请确认照片包含地理标签。</description>
            <Point><coordinates>116.3,39.9,0</coordinates></Point>
        </Placemark>"""
        placemarks.append(placemark)
    
    kml_content = f"""<?xml version='1.0' encoding='UTF-8'?>
<kml xmlns='http://www.opengis.net/kml/2.2'>
  <Document>
    <name>{folder_name}</name>
    <Folder>
      <name>{folder_name}</name>{''.join(placemarks)}
    </Folder>
  </Document>
</kml>"""
    with open(kml_path, 'w', encoding='utf-8') as f:
        f.write(kml_content)
    print(f"KML生成: {kml_path} (共{count_total}张, 有GPS {count_with_gps}张{', 无GPS ' + str(no_gps_count) + '张' if no_gps_count > 0 else ''})")
    
    # 返回是否有GPS数据，用于判断是否复制到对应文件夹
    return count_with_gps > 0

# 新增：生成两个KML（images + 未检出）
if _PIEXIF_AVAILABLE:
    try:
        # 在 images 文件夹内生成 KML
        if os.path.isdir(images_dir):
            images_local_kml_path = os.path.join(images_dir, 'checked.kml')
            generate_kml(images_dir, images_local_kml_path, 'checked')
        
        # 在 未检出 文件夹内生成 KML
        if os.path.isdir(unchecked_dir):
            unchecked_local_kml_path = os.path.join(unchecked_dir, 'unchecked.kml')
            generate_kml(unchecked_dir, unchecked_local_kml_path, 'unchecked')

    except Exception as e:
        print(f"生成KML出错: {e}")
else:
    print("未安装 piexif，跳过KML生成。可: pip install piexif")

print("完成")