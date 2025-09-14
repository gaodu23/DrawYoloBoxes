#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
剔除两个文件夹内不同名字的文件
只保留两个文件夹中都存在的同名文件
"""

import os
import shutil
from pathlib import Path
import argparse


def get_file_info(folder_path):
    """
    获取文件夹中所有文件的信息（不包括子文件夹）
    
    Args:
        folder_path (str): 文件夹路径
        
    Returns:
        tuple: (文件名集合(不包括后缀), 文件名映射字典{stem: [full_names]})
    """
    folder = Path(folder_path)
    if not folder.exists():
        print(f"警告: 文件夹 {folder_path} 不存在")
        return set(), {}
    
    file_stems = set()
    stem_to_files = {}
    
    for item in folder.iterdir():
        if item.is_file():
            stem = item.stem  # 不包括后缀的文件名
            full_name = item.name  # 完整文件名
            
            file_stems.add(stem)
            if stem not in stem_to_files:
                stem_to_files[stem] = []
            stem_to_files[stem].append(full_name)
    
    return file_stems, stem_to_files


def remove_different_files(folder1_path, folder2_path, backup_dir=None, dry_run=False):
    """
    剔除两个文件夹内不同名字的文件
    
    Args:
        folder1_path (str): 第一个文件夹路径
        folder2_path (str): 第二个文件夹路径
        backup_dir (str, optional): 备份目录路径，如果提供则将删除的文件移动到此目录
        dry_run (bool): 是否只是预览操作而不实际删除文件
    """
    
    # 检查文件夹是否存在
    folder1 = Path(folder1_path)
    folder2 = Path(folder2_path)
    
    if not folder1.exists():
        print(f"错误: 文件夹 {folder1_path} 不存在")
        return
    
    if not folder2.exists():
        print(f"错误: 文件夹 {folder2_path} 不存在")
        return
    
    # 获取两个文件夹中的文件信息
    files1, stem_to_files1 = get_file_info(folder1_path)
    files2, stem_to_files2 = get_file_info(folder2_path)
    
    print(f"文件夹1 ({folder1_path}) 包含 {len(files1)} 个不同名称的文件")
    print(f"文件夹2 ({folder2_path}) 包含 {len(files2)} 个不同名称的文件")
    
    # 找出共同的文件和不同的文件
    common_files = files1.intersection(files2)
    files_only_in_folder1 = files1 - files2
    files_only_in_folder2 = files2 - files1
    
    print(f"\n共同文件: {len(common_files)} 个")
    print(f"只在文件夹1中的文件: {len(files_only_in_folder1)} 个")
    print(f"只在文件夹2中的文件: {len(files_only_in_folder2)} 个")
    
    # 创建备份目录（如果需要）
    if backup_dir and not dry_run:
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)
        
        backup_folder1 = backup_path / "folder1_removed"
        backup_folder2 = backup_path / "folder2_removed"
        backup_folder1.mkdir(exist_ok=True)
        backup_folder2.mkdir(exist_ok=True)
    
    # 处理只在文件夹1中的文件
    if files_only_in_folder1:
        print(f"\n准备删除文件夹1中的以下文件:")
        for file_stem in sorted(files_only_in_folder1):
            # 获取该文件名对应的所有完整文件名
            full_names = stem_to_files1[file_stem]
            print(f"  - {file_stem} (对应文件: {', '.join(full_names)})")
            
            if not dry_run:
                for full_name in full_names:
                    file_path = folder1 / full_name
                    try:
                        if backup_dir:
                            # 移动到备份目录
                            backup_file = backup_folder1 / full_name
                            shutil.move(str(file_path), str(backup_file))
                            print(f"    已移动到备份目录: {backup_file}")
                        else:
                            # 直接删除
                            file_path.unlink()
                            print(f"    已删除: {full_name}")
                    except Exception as e:
                        print(f"    删除失败 {full_name}: {e}")
    
    # 处理只在文件夹2中的文件
    if files_only_in_folder2:
        print(f"\n准备删除文件夹2中的以下文件:")
        for file_stem in sorted(files_only_in_folder2):
            # 获取该文件名对应的所有完整文件名
            full_names = stem_to_files2[file_stem]
            print(f"  - {file_stem} (对应文件: {', '.join(full_names)})")
            
            if not dry_run:
                for full_name in full_names:
                    file_path = folder2 / full_name
                    try:
                        if backup_dir:
                            # 移动到备份目录
                            backup_file = backup_folder2 / full_name
                            shutil.move(str(file_path), str(backup_file))
                            print(f"    已移动到备份目录: {backup_file}")
                        else:
                            # 直接删除
                            file_path.unlink()
                            print(f"    已删除: {full_name}")
                    except Exception as e:
                        print(f"    删除失败 {full_name}: {e}")
    
    # 显示保留的文件
    if common_files:
        print(f"\n保留的共同文件 ({len(common_files)} 个):")
        for file_stem in sorted(common_files):
            files1_names = stem_to_files1[file_stem]
            files2_names = stem_to_files2[file_stem]
            print(f"  ✓ {file_stem}")
            print(f"    文件夹1: {', '.join(files1_names)}")
            print(f"    文件夹2: {', '.join(files2_names)}")
    
    print(f"\n操作完成!")
    if dry_run:
        print("注意: 这是预览模式，没有实际删除任何文件")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="剔除两个文件夹内不同名字的文件")
    parser.add_argument("folder1", help="第一个文件夹路径")
    parser.add_argument("folder2", help="第二个文件夹路径")
    parser.add_argument("--backup", "-b", help="备份目录路径（可选）")
    parser.add_argument("--dry-run", "-d", action="store_true", 
                       help="预览模式，不实际删除文件")
    
    args = parser.parse_args()
    
    print("=== 剔除两个文件夹内不同名字的文件 ===")
    print(f"文件夹1: {args.folder1}")
    print(f"文件夹2: {args.folder2}")
    
    if args.backup:
        print(f"备份目录: {args.backup}")
    
    if args.dry_run:
        print("模式: 预览模式（不会实际删除文件）")
    else:
        print("模式: 实际执行")
        
        # 确认操作
        confirm = input("\n确认要执行此操作吗？(y/N): ")
        if confirm.lower() not in ['y', 'yes', '是']:
            print("操作已取消")
            return
    
    print("\n开始处理...")
    remove_different_files(args.folder1, args.folder2, args.backup, args.dry_run)


if __name__ == "__main__":
    # 如果直接运行脚本，可以在这里设置默认的文件夹路径进行测试
    
    # 示例用法:
    folder1 = r"Z:\yolo\XY-YOLO-Tools\train_data\0909\images"
    folder2 = r"Z:\yolo\XY-YOLO-Tools\train_data\0909\labels"
    backup_dir = r"Z:\yolo\XY-YOLO-Tools\train_data\0909\backup"

    # # 预览模式
    # print("=== 预览模式 ===")
    # remove_different_files(folder1, folder2, backup_dir, dry_run=True)
    
    # # 实际执行（取消注释下面的代码）
    print("\n=== 实际执行 ===")
    remove_different_files(folder1, folder2, backup_dir, dry_run=False)
    
    # 使用命令行参数
    main()
