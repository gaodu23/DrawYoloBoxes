#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YOLO标注数据可视化工具
在图片上绘制红色边界框
"""

import os
import cv2
import numpy as np
import sys
import csv
import datetime
from pathlib import Path
import argparse
import piexif

# 添加PIL库导入
try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    print("警告: PIL/Pillow库未安装，某些EXIF功能可能受限。请安装: pip install pillow")
    _PIL_AVAILABLE = False


def get_exif_data(image_path):
    """
    获取图片的EXIF信息
    
    Args:
        image_path (str): 图片路径
        
    Returns:
        bytes: EXIF数据
    """
    try:
        # 优先使用piexif直接获取EXIF数据
        try:
            exif_dict = piexif.load(image_path)
            exif_bytes = piexif.dump(exif_dict)
            return exif_bytes
        except Exception as e:
            # 如果piexif失败，尝试使用PIL
            if _PIL_AVAILABLE:
                # 使用PIL读取EXIF数据
                img = Image.open(image_path)
                if 'exif' in img.info:
                    return img.info['exif']
        
        # 如果没有EXIF数据或读取失败，创建一个空的EXIF字典
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        return piexif.dump(exif_dict)
    except Exception as e:
        print(f"获取EXIF数据出错: {e}")
        # 创建一个空的EXIF字典
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        return piexif.dump(exif_dict)


def get_gps_info(image_path):
    """
    从图片的EXIF数据中提取GPS信息
    
    Args:
        image_path (str): 图片路径
        
    Returns:
        tuple: (经度, 纬度, 海拔) 或者 (None, None, None)
    """
    try:
        # 直接使用piexif读取EXIF信息
        exif_dict = piexif.load(image_path)
        
        # 检查是否有GPS信息
        if 'GPS' not in exif_dict or not exif_dict['GPS']:
            return None, None, None
        
        gps_info = exif_dict['GPS']
        
        # 获取经度
        longitude = None
        if piexif.GPSIFD.GPSLongitude in gps_info and piexif.GPSIFD.GPSLongitudeRef in gps_info:
            longitude_ref = gps_info[piexif.GPSIFD.GPSLongitudeRef].decode('ascii')
            longitude_data = gps_info[piexif.GPSIFD.GPSLongitude]
            
            # 转换为度分秒
            degrees = longitude_data[0][0] / longitude_data[0][1]
            minutes = longitude_data[1][0] / longitude_data[1][1]
            seconds = longitude_data[2][0] / longitude_data[2][1]
            
            # 转换为小数格式
            longitude = degrees + minutes / 60.0 + seconds / 3600.0
            
            # 如果是西经，值为负
            if longitude_ref == 'W':
                longitude = -longitude
        
        # 获取纬度
        latitude = None
        if piexif.GPSIFD.GPSLatitude in gps_info and piexif.GPSIFD.GPSLatitudeRef in gps_info:
            latitude_ref = gps_info[piexif.GPSIFD.GPSLatitudeRef].decode('ascii')
            latitude_data = gps_info[piexif.GPSIFD.GPSLatitude]
            
            # 转换为度分秒
            degrees = latitude_data[0][0] / latitude_data[0][1]
            minutes = latitude_data[1][0] / latitude_data[1][1]
            seconds = latitude_data[2][0] / latitude_data[2][1]
            
            # 转换为小数格式
            latitude = degrees + minutes / 60.0 + seconds / 3600.0
            
            # 如果是南纬，值为负
            if latitude_ref == 'S':
                latitude = -latitude
        
        # 获取海拔
        altitude = None
        if piexif.GPSIFD.GPSAltitude in gps_info:
            altitude_data = gps_info[piexif.GPSIFD.GPSAltitude]
            altitude = altitude_data[0] / altitude_data[1]
            
            # 如果有海拔参考，判断是否为负值
            if piexif.GPSIFD.GPSAltitudeRef in gps_info:
                alt_ref = gps_info[piexif.GPSIFD.GPSAltitudeRef]
                if alt_ref == 1:  # 海平面以下
                    altitude = -altitude
        
        return longitude, latitude, altitude
    except Exception as e:
        print(f"提取GPS信息出错: {image_path}, 错误: {e}")
        return None, None, None


def save_image_with_exif(image, output_path, exif_data=None):
    """
    保存图片并保留EXIF信息
    
    Args:
        image (numpy.ndarray): OpenCV图像
        output_path (str): 输出路径
        exif_data (bytes): EXIF数据
        
    Returns:
        bool: 是否成功
    """
    try:
        # 先用OpenCV保存图片
        success = cv2.imwrite(output_path, image)
        if not success:
            print(f"保存图片失败: {output_path}")
            return False
            
        # 如果有EXIF数据，则尝试添加EXIF信息
        if exif_data:
            try:
                if _PIL_AVAILABLE:
                    # 用PIL打开图片
                    pil_img = Image.open(output_path)
                    # 保存图片并添加EXIF数据
                    pil_img.save(output_path, exif=exif_data)
                    print(f"已保存带EXIF信息的标注图片: {output_path}")
                else:
                    # 如果PIL不可用，尝试直接使用piexif写入EXIF
                    piexif.insert(exif_data, output_path)
                    print(f"已保存带EXIF信息的标注图片: {output_path}")
            except Exception as e:
                print(f"保存EXIF信息失败: {e}")
                # 虽然EXIF保存失败，但图片已保存成功
                print(f"已保存标注图片(无EXIF): {output_path}")
                return True
        else:
            print(f"已保存标注图片: {output_path}")
            
        return True
    except Exception as e:
        print(f"保存图片时出错: {e}")
        return False


def read_class_names(classes_file):
    """
    读取类别名称文件
    
    Args:
        classes_file (str): 类别文件路径
        
    Returns:
        list: 类别名称列表
    """
    class_names = []
    if not os.path.exists(classes_file):
        print(f"类别文件不存在: {classes_file}")
        return class_names
        
    try:
        with open(classes_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    class_names.append(line)
    except Exception as e:
        print(f"读取类别文件出错: {classes_file}, 错误: {e}")
    
    return class_names


def read_yolo_labels(label_file):
    """
    读取YOLO格式的标注文件
    
    Args:
        label_file (str): 标注文件路径
        
    Returns:
        list: 标注信息列表，每个元素为 [class_id, x_center, y_center, width, height]
    """
    labels = []
    if not os.path.exists(label_file):
        return labels
        
    try:
        with open(label_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split()
                    if len(parts) >= 5:
                        class_id = int(parts[0])
                        x_center = float(parts[1])
                        y_center = float(parts[2])
                        width = float(parts[3])
                        height = float(parts[4])
                        labels.append([class_id, x_center, y_center, width, height])
    except Exception as e:
        print(f"读取标注文件出错: {label_file}, 错误: {e}")
    
    return labels


def yolo_to_bbox(yolo_coords, img_width, img_height):
    """
    将YOLO格式坐标转换为边界框坐标
    
    Args:
        yolo_coords (list): [x_center, y_center, width, height] (归一化坐标)
        img_width (int): 图片宽度
        img_height (int): 图片高度
        
    Returns:
        tuple: (x1, y1, x2, y2) 边界框坐标
    """
    x_center, y_center, width, height = yolo_coords
    
    # 转换为像素坐标
    x_center_px = x_center * img_width
    y_center_px = y_center * img_height
    width_px = width * img_width
    height_px = height * img_height
    
    # 计算边界框的左上角和右下角坐标
    x1 = int(x_center_px - width_px / 2)
    y1 = int(y_center_px - height_px / 2)
    x2 = int(x_center_px + width_px / 2)
    y2 = int(y_center_px + height_px / 2)
    
    return x1, y1, x2, y2


def draw_boxes_on_image(image_path, label_path, classes_file=None, output_path=None, box_color=(0, 0, 255), box_thickness=8):
    """
    在图片上绘制边界框
    
    Args:
        image_path (str): 图片路径
        label_path (str): 标注文件路径
        classes_file (str): 类别文件路径
        output_path (str): 输出图片路径，如果为None则覆盖原图
        box_color (tuple): 边界框颜色 (B, G, R)，默认红色
        box_thickness (int): 边界框线条粗细
        
    Returns:
        bool: 是否成功
    """
    # 读取类别名称
    class_names = []
    if classes_file:
        class_names = read_class_names(classes_file)
    
    # 读取图片
    if not os.path.exists(image_path):
        print(f"图片文件不存在: {image_path}")
        return False
        
    # 获取原始图片的EXIF信息
    exif_data = get_exif_data(image_path)
    
    image = cv2.imread(image_path)
    if image is None:
        print(f"无法读取图片: {image_path}")
        return False
    
    img_height, img_width = image.shape[:2]
    
    # 读取标注
    labels = read_yolo_labels(label_path)
    
    if not labels:
        print(f"标注文件为空或不存在: {label_path}")
        # 如果没有标注，仍然可以保存原图
        if output_path:
            save_image_with_exif(image, output_path, exif_data)
        return True
    
    # 在图片上绘制边界框
    for label in labels:
        class_id, x_center, y_center, width, height = label
        
        # 转换坐标
        x1, y1, x2, y2 = yolo_to_bbox([x_center, y_center, width, height], img_width, img_height)
        
        # 确保坐标在图片范围内
        x1 = max(0, min(x1, img_width - 1))
        y1 = max(0, min(y1, img_height - 1))
        x2 = max(0, min(x2, img_width - 1))
        y2 = max(0, min(y2, img_height - 1))
        
        # 绘制边界框
        cv2.rectangle(image, (x1, y1), (x2, y2), box_color, box_thickness)
        
        # 添加类别标签
        if class_names and 0 <= class_id < len(class_names):
            label_text = class_names[class_id]
        else:
            label_text = f"Class {class_id}"
        
        # 计算文本背景框的大小
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 3
        text_thickness = 3
        (text_width, text_height), _ = cv2.getTextSize(label_text, font, font_scale, text_thickness)
        
        # 绘制文本背景（半透明黑色）
        text_bg_x1 = x1
        text_bg_y1 = y1 - text_height - 10
        text_bg_x2 = x1 + text_width + 10
        text_bg_y2 = y1
        
        # 确保文本背景在图片范围内
        text_bg_y1 = max(0, text_bg_y1)
        text_bg_x2 = min(img_width, text_bg_x2)
        
        # 绘制半透明背景
        overlay = image.copy()
        cv2.rectangle(overlay, (text_bg_x1, text_bg_y1), (text_bg_x2, text_bg_y2), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, image, 0.4, 0, image)
        
        # 绘制文本
        text_x = x1 + 5
        text_y = y1 - 5 if y1 >= text_height + 15 else y1 + text_height + 5
        cv2.putText(image, label_text, (text_x, text_y), font, font_scale, box_color, text_thickness)
    
    # 保存图片
    if output_path is None:
        output_path = image_path
    
    # 使用自定义函数保存图片并保留EXIF信息
    success = save_image_with_exif(image, output_path, exif_data)
    
    return success


def generate_gps_csv(image_files, output_csv):
    """
    生成包含图片GPS信息的CSV文件
    
    Args:
        image_files (list): 图片文件路径列表
        output_csv (str): 输出CSV文件路径
    """
    # 准备CSV数据
    csv_data = [["照片名", "经度", "纬度", "海拔(米)"]]
    
    for image_file in image_files:
        image_path = str(image_file)
        image_name = os.path.basename(image_path)
        
        # 获取GPS信息
        longitude, latitude, altitude = get_gps_info(image_path)
        
        # 格式化GPS数据
        longitude_str = f"{longitude:.6f}" if longitude is not None else "无数据"
        latitude_str = f"{latitude:.6f}" if latitude is not None else "无数据"
        altitude_str = f"{altitude:.2f}" if altitude is not None else "无数据"
        
        # 添加到CSV数据
        csv_data.append([image_name, longitude_str, latitude_str, altitude_str])
    
    # 写入CSV文件
    try:
        with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)
        print(f"已生成GPS信息CSV文件: {output_csv}")
        return True
    except Exception as e:
        print(f"生成CSV文件出错: {e}")
        return False


def generate_kml(image_files, output_kml, classes_file=None, labels_dir=None):
    """
    生成包含图片位置的KML文件，可在Google Earth等软件中查看
    
    Args:
        image_files (list): 图片文件路径列表
        output_kml (str): 输出KML文件路径
        classes_file (str): 类别文件路径，用于获取标注类别名称
        labels_dir (str): 标注文件夹路径，用于获取每张图片的标注类别
        
    Returns:
        bool: 是否成功生成KML文件
    """
    try:
        # 读取类别名称
        class_names = []
        if classes_file and os.path.exists(classes_file):
            class_names = read_class_names(classes_file)
            
        # KML文件头
        kml_header = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>图片位置信息</name>
  <description>基于EXIF数据生成的照片位置</description>
  
  <!-- 定义样式 -->
  <Style id="photoIcon">
    <IconStyle>
      <Icon>
        <href>http://maps.google.com/mapfiles/kml/pal4/icon38.png</href>
      </Icon>
    </IconStyle>
  </Style>
'''

        # KML文件尾
        kml_footer = '''
</Document>
</kml>'''

        # 生成Placemark内容
        placemarks = []
        
        for image_file in image_files:
            image_path = str(image_file)
            image_name = os.path.basename(image_path)
            
            # 获取GPS信息
            longitude, latitude, altitude = get_gps_info(image_path)
            
            # 如果没有GPS信息，跳过
            if longitude is None or latitude is None:
                continue
                
            # 获取标注类别信息
            image_classes = []
            if labels_dir and class_names:
                label_file = Path(labels_dir) / f"{Path(image_path).stem}.txt"
                if label_file.exists():
                    labels = read_yolo_labels(str(label_file))
                    for label in labels:
                        class_id = label[0]
                        if 0 <= class_id < len(class_names):
                            image_classes.append(class_names[class_id])
            
            # 生成描述信息
            desc = f"<![CDATA[<b>照片名:</b> {image_name}<br/>"
            if altitude is not None:
                desc += f"<b>海拔:</b> {altitude:.2f}米<br/>"
            if image_classes:
                desc += f"<b>标注类别:</b> {', '.join(image_classes)}<br/>"
            desc += f"<b>时间:</b> {datetime.datetime.now().strftime('%Y-%m-%d')}<br/>"
            desc += f"<img src='file:///{image_path}' width='400'/>"
            desc += "]]>"
            
            # 创建Placemark
            placemark = f'''
  <Placemark>
    <name>{image_name}</name>
    <description>{desc}</description>
    <styleUrl>#photoIcon</styleUrl>
    <Point>
      <coordinates>{longitude},{latitude},{altitude if altitude is not None else 0}</coordinates>
    </Point>
  </Placemark>'''
            
            placemarks.append(placemark)
        
        # 如果没有有效的位置数据，则返回失败
        if not placemarks:
            print("没有找到有效的GPS信息，无法生成KML文件")
            return False
            
        # 写入KML文件
        with open(output_kml, 'w', encoding='utf-8') as f:
            f.write(kml_header)
            for placemark in placemarks:
                f.write(placemark)
            f.write(kml_footer)
            
        print(f"已生成KML文件: {output_kml}")
        print(f"包含 {len(placemarks)} 个位置点")
        return True
        
    except Exception as e:
        print(f"生成KML文件出错: {e}")
        return False


def process_dataset(images_dir, labels_dir, classes_file=None, output_dir=None, box_color=(0, 0, 255), generate_csv=True, generate_kml_file=True):
    """
    批量处理数据集
    
    Args:
        images_dir (str): 图片文件夹路径
        labels_dir (str): 标注文件夹路径
        classes_file (str): 类别文件路径
        output_dir (str): 输出文件夹路径，如果为None则覆盖原图
        box_color (tuple): 边界框颜色 (B, G, R)
        generate_csv (bool): 是否生成GPS信息CSV文件
        generate_kml_file (bool): 是否生成KML文件
    """
    images_dir = Path(images_dir)
    labels_dir = Path(labels_dir)
    
    if not images_dir.exists():
        print(f"图片文件夹不存在: {images_dir}")
        return
    
    if not labels_dir.exists():
        print(f"标注文件夹不存在: {labels_dir}")
        return
    
    # 读取类别名称
    class_names = []
    if classes_file and os.path.exists(classes_file):
        class_names = read_class_names(classes_file)
        print(f"已读取类别文件: {classes_file}")
        print(f"类别列表: {class_names}")
    
    # 创建输出文件夹
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"输出文件夹: {output_dir}")
    
    # 支持的图片格式（不区分大小写）
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
    
    # 获取所有图片文件
    image_files = []
    for file in os.listdir(images_dir):
        file_path = images_dir / file
        if file_path.is_file() and file_path.suffix.lower() in image_extensions:
            image_files.append(file_path)
    
    # 确保文件排序
    image_files.sort()
    
    processed_count = 0
    total_count = len(image_files)
    
    print(f"找到 {total_count} 张图片")
    if total_count > 0:
        print(f"文件列表:")
        for i, img in enumerate(image_files, 1):
            print(f"  {i}. {img.name}")
    
    for image_file in image_files:
        # 构造对应的标注文件路径
        label_file = labels_dir / f"{image_file.stem}.txt"
        
        # 构造输出路径
        if output_dir:
            output_file = output_dir / image_file.name
        else:
            output_file = None
        
        # 处理图片
        success = draw_boxes_on_image(str(image_file), str(label_file), classes_file, str(output_file) if output_file else None, box_color)
        
        if success:
            processed_count += 1
            print(f"进度: {processed_count}/{total_count} - {image_file.name}")
        else:
            print(f"处理失败: {image_file.name}")
    
    print(f"\n处理完成！成功处理 {processed_count}/{total_count} 张图片")
    
    # 生成GPS信息CSV文件
    if generate_csv and total_count > 0:
        if output_dir:
            csv_path = output_dir / "gps_info.csv"
        else:
            csv_path = Path(images_dir).parent / "gps_info.csv"
        
        print(f"\n正在生成GPS信息CSV文件...")
        generate_gps_csv(image_files, str(csv_path))
    
    # 生成KML文件
    if generate_kml_file and total_count > 0:
        if output_dir:
            kml_path = output_dir / "photo_locations.kml"
        else:
            kml_path = Path(images_dir).parent / "photo_locations.kml"
        
        print(f"\n正在生成KML文件...")
        generate_kml(image_files, str(kml_path), classes_file, labels_dir)


def main():
    parser = argparse.ArgumentParser(description='YOLO标注数据可视化工具')
    parser.add_argument('--images_dir', type=str, default='0907/images', help='图片文件夹路径')
    parser.add_argument('--labels_dir', type=str, default='0907/labels', help='标注文件夹路径')
    parser.add_argument('--classes_file', type=str, default='0907/classes.txt', help='类别文件路径')
    parser.add_argument('--output_dir', type=str, default='0907/output_with_boxes', help='输出文件夹路径')
    parser.add_argument('--single_image', type=str, help='处理单张图片的路径')
    parser.add_argument('--single_label', type=str, help='单张图片对应的标注文件路径')
    parser.add_argument('--box_thickness', type=int, default=2, help='边界框线条粗细')
    parser.add_argument('--overwrite', action='store_true', help='是否覆盖原图片（不创建输出文件夹）')
    parser.add_argument('--no_csv', action='store_true', help='不生成GPS信息CSV文件')
    parser.add_argument('--no_kml', action='store_true', help='不生成KML文件')
    
    args = parser.parse_args()
    
    # 边界框颜色 (B, G, R) - 红色
    box_color = (0, 0, 255)
    
    if args.single_image and args.single_label:
        # 处理单张图片
        output_path = args.single_image.replace('.', '_with_boxes.') if not args.overwrite else None
        draw_boxes_on_image(args.single_image, args.single_label, args.classes_file, output_path, box_color, args.box_thickness)
    else:
        # 批量处理
        output_dir = None if args.overwrite else args.output_dir
        process_dataset(args.images_dir, args.labels_dir, args.classes_file, output_dir, box_color, 
                      not args.no_csv, not args.no_kml)


if __name__ == "__main__":
    # 如果直接运行脚本，使用默认参数处理当前目录下的数据
    if len(sys.argv) == 1:
        print("YOLO标注数据可视化工具")
        print("=" * 50)

        # 默认处理0907文件夹
        images_dir = "0907/images"
        labels_dir = "0907/labels"
        classes_file = "0907/classes.txt"
        output_dir = "0907/output_with_boxes"
        
        print(f"图片文件夹: {images_dir}")
        print(f"标注文件夹: {labels_dir}")
        print(f"类别文件: {classes_file}")
        print(f"输出文件夹: {output_dir}")
        print()
        
        process_dataset(images_dir, labels_dir, classes_file, output_dir, generate_csv=True, generate_kml_file=True)
    else:
        main()
