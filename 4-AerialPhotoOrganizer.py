#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AerialPhotoOrganizer - 航片自动分类工具
使用piexif提取照片GPS信息并按行政区划自动整理

功能:
- 从照片中提取GPS经纬度信息
- 将照片与KML文件中的行政区划进行匹配
- 自动归类到对应的县市/乡镇/村庄三级文件夹
- 添加地理位置水印标注
- 生成包含照片信息的CSV报告和KML文件
"""

# 默认配置
DEFAULT_SOURCE_DIR = r"D:\yolo\XY-YOLO-Tools\train_data\YIHEDUI\0906\images"  # 默认源文件夹路径
DEFAULT_ADD_WATERMARK = False  # 默认是否添加水印
DEFAULT_GENERATE_CSV = True   # 默认是否生成CSV报告
DEFAULT_GENERATE_KML = True   # 默认是否生成KML报告
DEFAULT_KML_PARSE_MODE = "nested"  # KML解析模式: "standard"(标准)或"nested"(嵌套文件夹)
# DEFAULT_KML_PARSE_MODE = "standard"  # KML解析模式: "standard"(标准)或"nested"(嵌套文件夹)
USE_DEFAULT_SETTINGS = True   # 是否使用默认设置（True表示直接使用默认设置，不提示用户输入）


import os
import sys
import csv
import piexif
import shutil
import datetime
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon, Point
import numpy as np
import math
import re

# 支持的图片格式
SUPPORTED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.tiff', '.tif']

# 定义KML命名空间
KML_NS = {
    'kml': 'http://www.opengis.net/kml/2.2',
    'gx': 'http://www.google.com/kml/ext/2.2',
    '': 'http://www.opengis.net/kml/2.2'  # 默认命名空间
}

# 定义KML标签名称映射，适应不同的KML格式
KML_TAG_MAPPING = {
    'name': ['name', 'n'],  # 有些KML使用<n>替代<name>
    'coordinates': ['coordinates']
}

class PhotoInfo:
    """存储照片信息的类"""
    def __init__(self, filename, lat=None, lon=None, alt=None, datetime_original=None, 
                 make=None, model=None, district=None, town=None, village=None):
        self.filename = filename
        self.lat = lat
        self.lon = lon
        self.alt = alt
        self.datetime_original = datetime_original
        self.make = make
        self.model = model
        self.district = district  # 县区
        self.town = town          # 乡镇
        self.village = village    # 村庄

    def __str__(self):
        return f"{self.filename}: 位置({self.lat}, {self.lon}), 时间: {self.datetime_original}"

class AdministrativeRegion:
    """存储行政区划信息的类"""
    def __init__(self, name, level, polygon=None):
        self.name = name      # 名称
        self.level = level    # 级别：3=县市，2=乡镇，1=村庄
        self.polygon = polygon  # 边界多边形
        self._parent = None   # 上级行政区划
        self.children = []    # 下级行政区划列表

    def __str__(self):
        return f"{self.name} (Level {self.level})"

    def contains(self, point):
        """判断点是否在该区域内"""
        if self.polygon is None:
            return False
        return self.polygon.contains(point)
        
    @property
    def parent(self):
        return self._parent
        
    @parent.setter
    def parent(self, value):
        self._parent = value

def extract_exif_with_piexif(image_path):
    """
    使用piexif库从照片中提取EXIF信息
    
    Args:
        image_path: 图片文件路径
        
    Returns:
        photo_info: PhotoInfo对象，包含提取的信息
    """
    photo_info = PhotoInfo(os.path.basename(image_path))
    
    try:
        # 使用piexif库提取EXIF数据
        exif_dict = piexif.load(image_path)
        
        # 提取GPS信息
        if "GPS" in exif_dict and exif_dict["GPS"]:
            gps_data = exif_dict["GPS"]
            
            # 提取纬度
            if piexif.GPSIFD.GPSLatitude in gps_data and piexif.GPSIFD.GPSLatitudeRef in gps_data:
                lat_ref = gps_data[piexif.GPSIFD.GPSLatitudeRef].decode('ascii')
                lat_degrees = _convert_to_degrees(gps_data[piexif.GPSIFD.GPSLatitude])
                if lat_degrees is not None and lat_ref == 'S':
                    lat_degrees = -lat_degrees
                photo_info.lat = lat_degrees
            
            # 提取经度
            if piexif.GPSIFD.GPSLongitude in gps_data and piexif.GPSIFD.GPSLongitudeRef in gps_data:
                lon_ref = gps_data[piexif.GPSIFD.GPSLongitudeRef].decode('ascii')
                lon_degrees = _convert_to_degrees(gps_data[piexif.GPSIFD.GPSLongitude])
                if lon_degrees is not None and lon_ref == 'W':
                    lon_degrees = -lon_degrees
                photo_info.lon = lon_degrees
            
            # 提取海拔
            if piexif.GPSIFD.GPSAltitude in gps_data:
                alt_tuple = gps_data[piexif.GPSIFD.GPSAltitude]
                if alt_tuple and len(alt_tuple) == 2 and alt_tuple[1] != 0:
                    altitude = alt_tuple[0] / alt_tuple[1]
                    # 检查海拔参考（是否在海平面以下）
                    if piexif.GPSIFD.GPSAltitudeRef in gps_data and gps_data[piexif.GPSIFD.GPSAltitudeRef] == 1:
                        altitude = -altitude
                    photo_info.alt = altitude
        
        # 提取拍摄时间
        if "0th" in exif_dict and piexif.ImageIFD.DateTime in exif_dict["0th"]:
            try:
                dt_str = exif_dict["0th"][piexif.ImageIFD.DateTime].decode('ascii')
                photo_info.datetime_original = dt_str
            except:
                pass
                
        # 优先使用Exif信息中的拍摄时间
        if "Exif" in exif_dict and piexif.ExifIFD.DateTimeOriginal in exif_dict["Exif"]:
            try:
                dt_str = exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal].decode('ascii')
                photo_info.datetime_original = dt_str
            except:
                pass
        
        # 提取相机信息
        if "0th" in exif_dict:
            if piexif.ImageIFD.Make in exif_dict["0th"]:
                try:
                    photo_info.make = exif_dict["0th"][piexif.ImageIFD.Make].decode('ascii').strip()
                except:
                    pass
                    
            if piexif.ImageIFD.Model in exif_dict["0th"]:
                try:
                    photo_info.model = exif_dict["0th"][piexif.ImageIFD.Model].decode('ascii').strip()
                except:
                    pass
                    
    except Exception as e:
        print(f"提取EXIF数据出错 {image_path}: {e}")
    
    return photo_info

def _convert_to_degrees(value):
    """将EXIF中的GPS坐标转换为十进制度数"""
    try:
        d = float(value[0][0]) / float(value[0][1])
        m = float(value[1][0]) / float(value[1][1])
        s = float(value[2][0]) / float(value[2][1])
        return d + (m / 60.0) + (s / 3600.0)
    except (TypeError, ZeroDivisionError, IndexError, ValueError):
        return None

def parse_kml(kml_path, parse_mode="standard"):
    """
    解析KML文件，提取行政区划信息
    
    Args:
        kml_path: KML文件路径
        parse_mode: 解析模式，"standard"(标准)或"nested"(嵌套文件夹)
        
    Returns:
        regions_by_level: 按级别分组的行政区划字典
    """
    print(f"正在解析KML文件: {kml_path}，使用{parse_mode}模式")
    
    if parse_mode == "nested":
        return parse_kml_nested(kml_path)
    else:
        return parse_kml_standard(kml_path)

def parse_kml_standard(kml_path):
    """
    使用标准模式解析KML文件，通过LineStyle宽度确定级别
    
    Args:
        kml_path: KML文件路径
        
    Returns:
        regions_by_level: 按级别分组的行政区划字典
    """
    try:
        tree = ET.parse(kml_path)
        root = tree.getroot()
        
        # 创建存储不同级别行政区划的字典
        regions_by_level = {
            3: [],  # 县市级
            2: [],  # 乡镇级
            1: []   # 村庄级
        }
        
        # 查找所有Placemark元素
        for placemark in root.findall('.//kml:Placemark', KML_NS):
            name_elem = placemark.find('./kml:name', KML_NS)
            if name_elem is None or not name_elem.text:
                continue
                
            name = name_elem.text.strip()
            
            # 确定级别
            style_elem = placemark.find('./kml:Style/kml:LineStyle/kml:width', KML_NS)
            if style_elem is None or not style_elem.text:
                continue
                
            try:
                level = int(style_elem.text)
                if level not in [1, 2, 3]:
                    continue
            except ValueError:
                continue
            
            # 解析边界坐标
            coords_elem = placemark.find('.//kml:coordinates', KML_NS)
            if coords_elem is None or not coords_elem.text:
                # 创建无边界的区域（有些KML文件可能只包含名称）
                region = AdministrativeRegion(name, level)
                regions_by_level[level].append(region)
                continue
                
            coords_text = coords_elem.text.strip()
            
            # 解析坐标
            coords = []
            for point in coords_text.split():
                if not point.strip():
                    continue
                parts = point.split(',')
                if len(parts) >= 2:
                    try:
                        lon = float(parts[0])
                        lat = float(parts[1])
                        coords.append((lon, lat))
                    except ValueError:
                        pass
            
            if len(coords) >= 3:  # 至少需要3个点形成多边形
                # 创建Shapely多边形
                polygon = Polygon(coords)
                region = AdministrativeRegion(name, level, polygon)
                regions_by_level[level].append(region)
            else:
                # 边界点不足，创建无边界的区域
                region = AdministrativeRegion(name, level)
                regions_by_level[level].append(region)
        
        # 建立行政区划层级关系
        # 县市包含乡镇，乡镇包含村庄
        for town in regions_by_level[2]:
            for district in regions_by_level[3]:
                if town.polygon and district.polygon and town.polygon.intersects(district.polygon):
                    if town.polygon.area * 0.5 <= town.polygon.intersection(district.polygon).area:
                        town.parent = district
                        if town not in district.children:
                            district.children.append(town)
        
        for village in regions_by_level[1]:
            for town in regions_by_level[2]:
                if village.polygon and town.polygon and village.polygon.intersects(town.polygon):
                    if village.polygon.area * 0.5 <= village.polygon.intersection(town.polygon).area:
                        village.parent = town
                        if village not in town.children:
                            town.children.append(village)
                        # 设置县市级关系
                        if town.parent:
                            village.district = town.parent
        
        # 输出统计信息
        print(f"解析完成! 共发现 {len(regions_by_level[3])} 个县市, {len(regions_by_level[2])} 个乡镇, {len(regions_by_level[1])} 个村庄")
        
        return regions_by_level
        
    except Exception as e:
        print(f"解析KML文件出错: {e}")
        return {3: [], 2: [], 1: []}

def parse_kml_nested(kml_path):
    """
    使用嵌套文件夹模式解析KML文件，通过层级:
      Document -> 县级(3)
      Document/Folder -> 乡镇级(2)
      Document/Folder/Placemark -> 村级(1)
    规则:
      - 县名取 Document 下第一个不含 乡/镇/村 的 <name>/<n> 内容，找不到则回退第一个名称，再失败用 "未知县"。
      - 乡镇名取各 Folder 下第一个 <name>/<n>。
      - 村名取各 Placemark 下第一个 <name>/<n>。
      - 村解析坐标生成 polygon；乡镇/县暂不合成 polygon。
    """
    try:
        tree = ET.parse(kml_path)
        root = tree.getroot()

        def local_name(tag: str):
            return tag.split('}')[-1] if tag else tag

        regions_by_level = {3: [], 2: [], 1: []}

        # 找 Document
        document = None
        for child in root.iter():  # 容忍结构嵌套
            if local_name(child.tag) == 'Document':
                document = child
                break
        if document is None:
            print("警告：未找到Document元素")
            return regions_by_level

        # 提取县级名称
        district_name = None
        name_candidates = []
        for elem in document:
            ln = local_name(elem.tag)
            if ln in ('name', 'n') and elem.text and elem.text.strip():
                txt = elem.text.strip()
                name_candidates.append(txt)
                if not any(s in txt for s in ('乡', '镇', '村')):
                    district_name = txt
                    break
        if district_name is None and name_candidates:
            district_name = name_candidates[0]
        if not district_name:
            district_name = "未知县"
            print("使用默认县市级: 未知县")
        # else:
            # print(f"发现县市级: {district_name}")

        district_region = AdministrativeRegion(district_name, 3)
        regions_by_level[3].append(district_region)

        # 处理乡镇 (Folder)
        folder_count = 0
        village_count = 0
        for folder in document:
            if local_name(folder.tag) != 'Folder':
                continue
            folder_count += 1
            # 乡镇名称
            town_name = None
            for fc in folder:
                if local_name(fc.tag) in ('name', 'n') and fc.text and fc.text.strip():
                    town_name = fc.text.strip()
                    break
            if not town_name:
                print("跳过无名称Folder")
                continue
            town_region = AdministrativeRegion(town_name, 2)
            town_region.parent = district_region
            district_region.children.append(town_region)
            regions_by_level[2].append(town_region)
            # print(f"发现乡镇级: {town_name} (属于 {district_name})")

            # 处理村 (Placemark)
            for pm in folder:
                if local_name(pm.tag) != 'Placemark':
                    continue
                # 村名
                village_name = None
                for pc in pm:
                    if local_name(pc.tag) in ('name', 'n') and pc.text and pc.text.strip():
                        village_name = pc.text.strip()
                        break
                if not village_name:
                    continue
                village_region = AdministrativeRegion(village_name, 1)
                village_region.parent = town_region
                town_region.children.append(village_region)

                # 坐标 (第一个 coordinates)
                coords_text = None
                for sub in pm.iter():
                    if local_name(sub.tag) == 'coordinates' and sub.text and sub.text.strip():
                        coords_text = sub.text
                        break
                if coords_text:
                    coords = parse_coordinates(coords_text)
                    if len(coords) >= 3:
                        village_region.polygon = Polygon(coords)
                regions_by_level[1].append(village_region)
                village_count += 1
                # print(f"发现村庄级: {village_name} (属于 {town_name})")

        print(f"解析完成! 共发现 {len(regions_by_level[3])} 个县市, {len(regions_by_level[2])} 个乡镇, {len(regions_by_level[1])} 个村庄")
        return regions_by_level
    except Exception as e:
        print(f"解析KML文件出错: {e}")
        return {3: [], 2: [], 1: []}

def parse_boundary_for_region(folder, region, namespaces=None):
    """
    解析文件夹中的边界信息并设置到区域对象
    
    Args:
        folder: 文件夹元素
        region: 行政区划对象
        namespaces: 命名空间字典，默认为KML_NS
    """
    if namespaces is None:
        namespaces = KML_NS
        
    # 先查找文件夹下的直接Placemark（与文件夹同名表示边界）
    placemarks = folder.findall('./kml:Placemark', namespaces) or folder.findall('./Placemark')
    for placemark in placemarks:
        # 尝试查找name标签，如果没有则尝试查找n标签
        name_elem = placemark.find('./kml:name', namespaces) or placemark.find('./name') or placemark.find('./kml:n', namespaces) or placemark.find('./n')
            
        if name_elem is not None and name_elem.text and name_elem.text.strip() == region.name:
            coords_elem = placemark.find('.//kml:coordinates', namespaces) or placemark.find('.//coordinates')
            if coords_elem is not None and coords_elem.text:
                coords = parse_coordinates(coords_elem.text)
                if len(coords) >= 3:
                    region.polygon = Polygon(coords)
                    return
    
    # 如果没有找到，则查找任意边界
    for placemark in placemarks:
        coords_elem = placemark.find('.//kml:coordinates', namespaces) or placemark.find('.//coordinates')
        if coords_elem is not None and coords_elem.text:
            coords = parse_coordinates(coords_elem.text)
            if len(coords) >= 3:
                region.polygon = Polygon(coords)
                return

def parse_coordinates(coords_text):
    """
    解析KML坐标文本
    
    Args:
        coords_text: 坐标文本字符串
        
    Returns:
        coords: 坐标点列表[(lon, lat), ...]
    """
    coords = []
    for point in coords_text.strip().split():
        if not point.strip():
            continue
        parts = point.split(',')
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                coords.append((lon, lat))
            except ValueError:
                pass
    return coords

def find_region_for_point(point, regions_by_level):
    """查找包含指定点的行政区划(支持仅村有多边形场景)
    逻辑:
      1. 遍历村 polygon: contains / touches / intersects -> 命中即通过 parent 还原乡镇/县
      2. 如果未来乡镇或县补充 polygon，可继续匹配
    返回 (district, town, village)
    """
    district = None
    town = None
    village = None

    # 优先匹配村庄
    for v in regions_by_level[1]:
        poly = v.polygon
        if not poly:
            continue
        try:
            if poly.contains(point) or poly.touches(point) or poly.intersects(point):
                village = v
                town = v.parent if v.parent else None
                district = town.parent if (town and town.parent) else None
                break
        except Exception:
            continue

    # 备用: 若未来给乡镇加 polygon，可匹配
    if village is None:
        for t in regions_by_level[2]:
            poly = t.polygon
            if not poly:
                continue
            try:
                if poly.contains(point) or poly.touches(point) or poly.intersects(point):
                    town = t
                    district = t.parent if t.parent else None
                    break
            except Exception:
                continue

    # 备用: 匹配县级
    if village is None and town is None:
        for d in regions_by_level[3]:
            poly = d.polygon
            if not poly:
                continue
            try:
                if poly.contains(point) or poly.touches(point) or poly.intersects(point):
                    district = d
                    break
            except Exception:
                continue

    return district, town, village

def organize_photos(source_dir, target_dir, kml_path, add_watermark=True, generate_csv=True, generate_kml=True, kml_parse_mode="standard"):
    """
    主要处理函数，整理照片到行政区划文件夹
    
    Args:
        source_dir: 源文件夹路径
        target_dir: 目标文件夹路径
        kml_path: KML文件路径
        add_watermark: 是否添加水印
        generate_csv: 是否生成CSV报告
        generate_kml: 是否生成KML报告
        kml_parse_mode: KML解析模式，"standard"(标准)或"nested"(嵌套文件夹)
    """
    # 创建目标文件夹
    os.makedirs(target_dir, exist_ok=True)
    
    # 定义无GPS信息和未匹配行政区划文件夹路径
    no_gps_dir = os.path.join(target_dir, "无GPS信息")
    unmatched_dir = os.path.join(target_dir, "未匹配行政区划")
    
    # 解析KML文件
    regions_by_level = parse_kml(kml_path, kml_parse_mode)
    
    # 按行政区划组织的照片信息字典
    photos_by_region = {}
    
    # 收集所有照片文件
    photo_files = []
    print(f"正在扫描源文件夹: {source_dir}")
    
    for root, _, files in os.walk(source_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in SUPPORTED_IMAGE_EXTENSIONS:
                photo_files.append(os.path.join(root, file))
    
    total_photos = len(photo_files)
    print(f"找到 {total_photos} 张照片")
    
    processed = 0
    with_gps = 0
    matched = 0
    
    # 处理每张照片
    for photo_path in photo_files:
        processed += 1
        print(f"处理中: {processed}/{total_photos} - {os.path.basename(photo_path)}")
        
        # 提取EXIF信息
        photo_info = extract_exif_with_piexif(photo_path)
        
        # 检查是否有GPS信息
        if photo_info.lat is None or photo_info.lon is None:
            # 无GPS信息，移到特殊文件夹
            # 确保无GPS信息文件夹存在
            if not os.path.exists(no_gps_dir):
                os.makedirs(no_gps_dir, exist_ok=True)
                
            dest_path = os.path.join(no_gps_dir, os.path.basename(photo_path))
            shutil.copy2(photo_path, dest_path)
            print(f"  无GPS信息: {os.path.basename(photo_path)}")
            continue
        
        with_gps += 1
        
        # 创建Point对象
        point = Point(photo_info.lon, photo_info.lat)
        
        # 查找对应的行政区划
        district, town, village = find_region_for_point(point, regions_by_level)
        
        # 设置行政区划信息
        if district:
            photo_info.district = district.name
        if town:
            photo_info.town = town.name
        if village:
            photo_info.village = village.name
        
        # 根据匹配结果决定目标路径
        if village and town and district:
            # 完全匹配，创建三级目录结构
            district_dir = os.path.join(target_dir, district.name)
            town_dir = os.path.join(district_dir, town.name)
            village_dir = os.path.join(town_dir, village.name)
            
            os.makedirs(village_dir, exist_ok=True)
            dest_dir = village_dir
            matched += 1
            
            # 将照片信息添加到区域字典
            region_key = f"{district.name}/{town.name}/{village.name}"
            if region_key not in photos_by_region:
                photos_by_region[region_key] = []
            photos_by_region[region_key].append(photo_info)
            
            print(f"  匹配到: {district.name}/{town.name}/{village.name}")
            
        elif town and district:
            # 匹配到乡镇级别
            district_dir = os.path.join(target_dir, district.name)
            town_dir = os.path.join(district_dir, town.name)
            
            os.makedirs(town_dir, exist_ok=True)
            dest_dir = town_dir
            
            # 将照片信息添加到区域字典
            region_key = f"{district.name}/{town.name}"
            if region_key not in photos_by_region:
                photos_by_region[region_key] = []
            photos_by_region[region_key].append(photo_info)
            
            print(f"  匹配到乡镇: {district.name}/{town.name}")
            
        elif district:
            # 仅匹配到县市级别
            district_dir = os.path.join(target_dir, district.name)
            
            os.makedirs(district_dir, exist_ok=True)
            dest_dir = district_dir
            
            # 将照片信息添加到区域字典
            region_key = district.name
            if region_key not in photos_by_region:
                photos_by_region[region_key] = []
            photos_by_region[region_key].append(photo_info)
            
            print(f"  匹配到县市: {district.name}")
            
        else:
            # 未匹配到行政区划
            # 确保未匹配行政区划文件夹存在
            if not os.path.exists(unmatched_dir):
                os.makedirs(unmatched_dir, exist_ok=True)
                
            dest_dir = unmatched_dir
            print(f"  未匹配行政区划: {os.path.basename(photo_path)} ({photo_info.lat}, {photo_info.lon})")
        
        # 复制照片到目标目录
        dest_path = os.path.join(dest_dir, os.path.basename(photo_path))
        
        if add_watermark:
            # 添加水印
            add_location_watermark(photo_path, dest_path, photo_info)
        else:
            # 直接复制
            shutil.copy2(photo_path, dest_path)
    
    print(f"\n处理完成!")
    print(f"总照片: {total_photos}")
    print(f"有GPS信息: {with_gps}")
    print(f"成功匹配行政区划: {matched}")
    
    # 生成报告
    if generate_csv or generate_kml:
        generate_reports(photos_by_region, target_dir, generate_csv, generate_kml)

def add_location_watermark(src_path, dest_path, photo_info):
    """
    在照片左上角添加行政区划名和经纬度水印，并保留原始EXIF信息
    
    Args:
        src_path: 源照片路径
        dest_path: 目标照片路径
        photo_info: 照片信息对象
    """
    try:
        # 打开图像
        img = Image.open(src_path)
        
        # 先提取原始EXIF数据，以便后续保存
        try:
            exif_dict = piexif.load(src_path)
            has_exif = True
        except:
            has_exif = False
        
        # 创建一个绘图对象
        draw = ImageDraw.Draw(img)
        
        # 尝试加载字体，如果失败则使用默认字体
        try:
            font = ImageFont.truetype("simhei.ttf", 60)  # 字体大小设为原来的一半(原来是120)
        except IOError:
            try:
                font = ImageFont.truetype("arial.ttf", 60)  # 字体大小设为原来的一半(原来是120)
            except IOError:
                font = ImageFont.load_default()  # 使用默认字体
        
        # 准备行政区划文本
        location_text = ""
        if photo_info.district:
            location_text += photo_info.district
        if photo_info.town:
            location_text += "/" + photo_info.town
        if photo_info.village:
            location_text += "/" + photo_info.village
            
        if not location_text:
            location_text = "未知区域"
            
        # 添加经纬度信息
        coord_text = f"经度: {photo_info.lon:.6f} 纬度: {photo_info.lat:.6f}"
            
        # 计算文本位置
        padding = 20  # 设为原来的一半(原来是40)
        
        # 估计文本大小来设置背景尺寸
        text_height = 160  # 设为原来的一半(原来是320)
        
        # 获取文本宽度估计
        try:
            location_width = draw.textlength(location_text, font=font)
            coord_width = draw.textlength(coord_text, font=font)
            bg_width = int(max(location_width, coord_width) + padding * 2)
        except AttributeError:  # 旧版PIL不支持textlength
            bg_width = int(len(location_text) * 40) + padding * 2  # 设为原来的一半(原来是80)
        
        # 画半透明背景，只覆盖文本区域
        draw.rectangle([(0, 0), (bg_width, text_height)], fill=(0, 0, 0, 30))  # 降低不透明度从128到80，使背景更透明
        
        # 绘制文本
        draw.text((padding, padding), location_text, fill=(255, 255, 255), font=font)
        draw.text((padding, padding + 80), coord_text, fill=(255, 255, 255), font=font)  # 设为原来的一半(原来是160)
        
        # 保存图像，并保留原始EXIF信息
        if has_exif:
            try:
                # 直接使用PIL和piexif的标准方法
                exif_bytes = piexif.dump(exif_dict)
                img.save(dest_path, format='JPEG', quality=95, exif=exif_bytes)
            except Exception as e:
                print(f"保存EXIF数据失败: {e}，尝试备选方法")
                try:
                    # 备选方法：保存为临时文件然后使用piexif.insert
                    temp_io = io.BytesIO()
                    img.save(temp_io, format='JPEG', quality=95)
                    temp_io.seek(0)
                    temp_data = temp_io.getvalue()
                    
                    # 使用piexif.insert
                    new_data = piexif.insert(exif_bytes, temp_data)
                    if new_data:  # 确保不是None
                        with open(dest_path, 'wb') as f:
                            f.write(new_data)
                    else:
                        # 如果insert失败，直接保存没有EXIF的图像
                        img.save(dest_path, quality=95)
                except Exception as e2:
                    print(f"备选方法也失败: {e2}，保存无EXIF图像")
                    img.save(dest_path, quality=95)
        else:
            # 如果原图没有EXIF信息，直接保存
            img.save(dest_path, quality=95)
        
    except Exception as e:
        print(f"添加水印失败: {e}")
        # 如果水印失败，直接复制原图
        shutil.copy2(src_path, dest_path)

def generate_reports(photos_by_region, target_dir, generate_csv=True, generate_kml=True):
    """
    为每个村庄生成报告
    
    Args:
        photos_by_region: 按区域分组的照片信息字典
        target_dir: 目标文件夹路径
        generate_csv: 是否生成CSV报告
        generate_kml: 是否生成KML报告
    """
    print("\n生成报告...")
    
    for region_key, photos in photos_by_region.items():
        if not photos:
            continue
            
        # 分解区域路径
        path_parts = region_key.split('/')
        
        # 确定保存报告的路径
        report_dir = os.path.join(target_dir, *path_parts)
        os.makedirs(report_dir, exist_ok=True)
        
        # 生成CSV报告
        if generate_csv:
            csv_path = os.path.join(report_dir, f"{path_parts[-1]}_照片报告.csv")
        
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                # 写入表头
                writer.writerow(['照片名', '经度', '纬度', '海拔(米)', '拍摄时间', '相机品牌', '相机型号'])
                
                # 写入照片数据
                for photo in photos:
                    writer.writerow([
                        photo.filename,
                        f"{photo.lon:.8f}" if photo.lon is not None else '',
                        f"{photo.lat:.8f}" if photo.lat is not None else '',
                        f"{photo.alt:.1f}" if photo.alt is not None else '',
                        photo.datetime_original or '',
                        photo.make or '',
                        photo.model or ''
                    ])
                
                # 写入照片数据
                for photo in photos:
                    writer.writerow([
                        photo.filename,
                        f"{photo.lon:.8f}" if photo.lon is not None else '',
                        f"{photo.lat:.8f}" if photo.lat is not None else '',
                        f"{photo.alt:.1f}" if photo.alt is not None else '',
                        photo.datetime_original or '',
                        photo.make or '',
                        photo.model or ''
                    ])
                    
            print(f"已生成CSV报告: {csv_path}")
                
        except Exception as e:
            print(f"生成CSV报告失败: {e}")
        
        # 生成KML报告
        if generate_kml:
            kml_path = os.path.join(report_dir, f"{path_parts[-1]}_照片位置.kml")
            
            try:
                generate_kml_report(photos, kml_path, region_key)
                print(f"已生成KML报告: {kml_path}")
                
            except Exception as e:
                print(f"生成KML报告失败: {e}")

def generate_kml_report(photos, kml_path, region_name):
    """
    生成KML报告文件
    
    Args:
        photos: 照片信息列表
        kml_path: KML文件保存路径
        region_name: 区域名称
    """
    # 创建KML基础结构
    kml_header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    kml_header += '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
    kml_header += '<Document>\n'
    kml_header += f'  <name>{region_name} 照片位置</name>\n'
    
    # 创建样式
    kml_header += '  <Style id="photoStyle">\n'
    kml_header += '    <IconStyle>\n'
    kml_header += '      <Icon><href>http://maps.google.com/mapfiles/kml/shapes/camera.png</href></Icon>\n'
    kml_header += '    </IconStyle>\n'
    kml_header += '  </Style>\n'
    
    kml_content = ''
    
    # 添加每张照片的标记点
    for photo in photos:
        if photo.lat is None or photo.lon is None:
            continue
            
        kml_content += '  <Placemark>\n'
        kml_content += f'    <name>{photo.filename}</name>\n'
        kml_content += '    <styleUrl>#photoStyle</styleUrl>\n'
        
        # 添加照片信息到描述
        description = f'<![CDATA[<b>照片名:</b> {photo.filename}<br/>'
        description += f'<b>经度:</b> {photo.lon:.8f}<br/>'
        description += f'<b>纬度:</b> {photo.lat:.8f}<br/>'
        
        if photo.alt is not None:
            description += f'<b>海拔:</b> {photo.alt:.1f} 米<br/>'
            
        if photo.datetime_original:
            description += f'<b>拍摄时间:</b> {photo.datetime_original}<br/>'
            
        if photo.make:
            description += f'<b>相机品牌:</b> {photo.make}<br/>'
            
        if photo.model:
            description += f'<b>相机型号:</b> {photo.model}<br/>'
            
        description += ']]>'
        
        kml_content += f'    <description>{description}</description>\n'
        kml_content += '    <Point>\n'
        kml_content += f'      <coordinates>{photo.lon},{photo.lat},{photo.alt or 0}</coordinates>\n'
        kml_content += '    </Point>\n'
        kml_content += '  </Placemark>\n'
    
    # 完成KML文件
    kml_footer = '</Document>\n</kml>'
    
    # 写入文件
    with open(kml_path, 'w', encoding='utf-8') as f:
        f.write(kml_header + kml_content + kml_footer)

def find_kml_files(directory):
    """
    在指定目录中查找KML或OVKML文件
    
    Args:
        directory: 要搜索的目录
        
    Returns:
        list: 找到的KML文件路径列表
    """
    kml_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            lower_name = file.lower()
            if lower_name.endswith('.kml') or lower_name.endswith('.ovkml'):
                kml_files.append(os.path.join(root, file))
    return kml_files

def main():
    """主函数"""
    print("\n== 航片自动分类工具 ==")
    
    # 使用默认设置或从命令行获取路径
    if USE_DEFAULT_SETTINGS:
        source_dir = DEFAULT_SOURCE_DIR
        add_watermark = DEFAULT_ADD_WATERMARK
        generate_csv = DEFAULT_GENERATE_CSV
        generate_kml = DEFAULT_GENERATE_KML
        kml_parse_mode = DEFAULT_KML_PARSE_MODE
    else:
        if len(sys.argv) != 2:
            print("用法: python AerialPhotoOrganizer.py <源文件夹>")
            source_dir = input("请输入源文件夹路径: ").strip()
        else:
            source_dir = sys.argv[1]
            
        # 验证路径存在
        if not os.path.isdir(source_dir):
            print(f"错误: 源文件夹不存在 - {source_dir}")
            return
            
        # 询问是否添加水印
        while True:
            choice = input("是否添加水印? (Y/N，默认Y): ").strip().upper()
            if choice == "" or choice == "Y":
                add_watermark = True
                break
            elif choice == "N":
                add_watermark = False
                break
            else:
                print("请输入Y或N")
        
        # 询问是否生成CSV报告
        while True:
            choice = input("是否生成CSV报告? (Y/N，默认Y): ").strip().upper()
            if choice == "" or choice == "Y":
                generate_csv = True
                break
            elif choice == "N":
                generate_csv = False
                break
            else:
                print("请输入Y或N")
        
        # 询问是否生成KML报告
        while True:
            choice = input("是否生成KML报告? (Y/N，默认Y): ").strip().upper()
            if choice == "" or choice == "Y":
                generate_kml = True
                break
            elif choice == "N":
                generate_kml = False
                break
            else:
                print("请输入Y或N")

        # 询问KML解析模式
        while True:
            print("\nKML解析模式:")
            print("1. 标准模式 (通过LineStyle宽度确定级别)")
            print("2. 嵌套文件夹模式 (通过Folder嵌套关系确定级别)")
            choice = input("请选择KML解析模式 (1/2，默认1): ").strip()
            if choice == "" or choice == "1":
                kml_parse_mode = "standard"
                break
            elif choice == "2":
                kml_parse_mode = "nested"
                break
            else:
                print("请输入1或2")
    
    # 验证路径
    if not os.path.isdir(source_dir):
        print(f"错误: 源文件夹不存在 - {source_dir}")
        return
    
    # 在源文件夹中查找KML/OVKML文件
    kml_files = find_kml_files(source_dir)
    
    if not kml_files:
        print(f"错误: 在 {source_dir} 及其子文件夹中未找到KML或OVKML文件")
        return
    
    # 如果找到多个KML文件，让用户选择或使用第一个
    if len(kml_files) == 1 or USE_DEFAULT_SETTINGS:
        kml_path = kml_files[0]
        print(f"找到KML文件: {kml_path}")
    else:
        print("找到多个KML/OVKML文件:")
        for i, kml_file in enumerate(kml_files):
            print(f"{i+1}. {kml_file}")
        
        while True:
            try:
                selection = input("请选择要使用的文件 (输入编号): ").strip()
                index = int(selection) - 1
                if 0 <= index < len(kml_files):
                    kml_path = kml_files[index]
                    break
                else:
                    print("无效的选择，请重试")
            except ValueError:
                print("请输入有效的数字")
    
    # 创建目标文件夹 (在源文件夹内创建 "已分类照片" 子文件夹)
    target_dir = os.path.join(source_dir, "已分类照片_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
    
    # 确保目标文件夹存在
    os.makedirs(target_dir, exist_ok=True)
    print(f"\n将照片整理到: {target_dir}")
    
    # 显示使用的设置
    print(f"使用设置: 添加水印 = {add_watermark}, 生成CSV = {generate_csv}, 生成KML = {generate_kml}, KML解析模式 = {kml_parse_mode}")
    
    # 执行主处理函数
    organize_photos(source_dir, target_dir, kml_path, add_watermark, generate_csv, generate_kml, kml_parse_mode)
    
    print("\n处理完成!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"\n程序出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("按Enter键退出...")
        input()
