import os
import glob
from batch_add_gps_info import process_images_from_csv

# 启蒙拷贝完原始航天用此工具批量。复制和写入exif


# 可选：相机参数文件路径（如有需要可填写）
opt_file = r'D:\FLY\PicExifAdd\cameraInfo\4200-40.opt'

def run_all_tasks():
    # 输入输出路径配对
    task_pairs = [
        (r'D:\202509宁晋环境\0908\21', r'D:\yolo\XY-YOLO-Tools\train_data\090822\images'),
        (r'D:\202509宁晋环境\0908\22', r'D:\yolo\XY-YOLO-Tools\train_data\0908\images'),
        (r'D:\202509宁晋环境\0908\23', r'D:\yolo\XY-YOLO-Tools\train_data\0908\images'),
        (r'D:\202509宁晋环境\0908\31', r'D:\yolo\XY-YOLO-Tools\train_data\0908\images'),
        (r'D:\202509宁晋环境\0908\32', r'D:\yolo\XY-YOLO-Tools\train_data\0908\images'),
        (r'D:\202509宁晋环境\0908\33', r'D:\yolo\XY-YOLO-Tools\train_data\0908\images'),
    ]
    for idx, (folder, out_folder) in enumerate(task_pairs, 1):
        print(f"\n{'='*60}")
        print(f"任务{idx}: 目录: {folder}")
        csv_files, jpg_files = find_csv_and_jpg(folder)
        print(f"  找到CSV文件: {csv_files}")
        print(f"  找到JPG文件数量: {len(jpg_files)}")
        if not csv_files:
            print("  未找到CSV文件，跳过！")
            print(f"{'='*60}\n")
            continue
        if len(csv_files) > 1:
            print("  发现多个CSV文件，请手动处理，跳过！")
            print(f"{'='*60}\n")
            continue
        import pandas as pd
        try:
            df = pd.read_csv(csv_files[0], header=None, encoding='utf-8-sig')
            # 只用csv第四列做照片名比对
            csv_names = set(str(row[3]).strip() for _, row in df.iterrows())
        except Exception as e:
            print(f"  CSV读取失败: {e}，跳过！")
            print(f"{'='*60}\n")
            continue
        # 取照片文件名（不含路径，统一小写）
        jpg_names = set(os.path.basename(f).lower() for f in jpg_files)
        # 只用csv第四列做照片名比对（统一小写）
        csv_names = set(str(row[3]).strip().lower() for _, row in df.iterrows())
        # 比对文件名集合
        missing_in_jpg = csv_names - jpg_names
        extra_in_jpg = jpg_names - csv_names
        if missing_in_jpg or extra_in_jpg:
            print(f"  文件名不一致，跳过！")
            if missing_in_jpg:
                print(f"  CSV有但照片文件夹缺失: {sorted(missing_in_jpg)}")
            if extra_in_jpg:
                print(f"  照片文件夹有但CSV未列出: {sorted(extra_in_jpg)}")
            print(f"  CSV照片名总数: {len(csv_names)}，照片文件名总数: {len(jpg_names)}")
            print(f"{'='*60}\n")
            continue
        print(f"  文件名完全对应，准备处理。")
        print(f"  输出文件夹: {out_folder}")
        print(f"{'-'*60}")
        result = process_images_from_csv(csv_files[0], folder, opt_file=opt_file, output_dir=out_folder)
        print(f"结果: 成功={result['success']} 失败={result['failed']} 跳过={result['skipped']}")
        if result['errors']:
            print("错误信息:")
            for err in result['errors']:
                print(f"  - {err}")
        print(f"{'='*60}\n")


def find_csv_and_jpg(folder):
    # 查找csv文件（只在主目录）
    csv_files = glob.glob(os.path.join(folder, '*.csv'))
    # 查找所有下一级文件夹里的JPG/JPEG文件（支持大小写）
    jpg_files = []
    for subdir in os.listdir(folder):
        sub_path = os.path.join(folder, subdir)
        if os.path.isdir(sub_path):
            jpg_files += glob.glob(os.path.join(sub_path, '*.jpg'))
            jpg_files += glob.glob(os.path.join(sub_path, '*.jpeg'))
            jpg_files += glob.glob(os.path.join(sub_path, '*.JPG'))
            jpg_files += glob.glob(os.path.join(sub_path, '*.JPEG'))
    return csv_files, jpg_files

if __name__ == "__main__":
    run_all_tasks()
