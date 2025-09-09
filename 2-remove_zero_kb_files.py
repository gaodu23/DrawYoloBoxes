import os
import shutil

# YOLO检测完第一遍后，删掉0kb文本，移动相应文件到未检测出文件夹。
# 下一步进行人工核对。核对后再运行一遍本程序进行二次删除。
# 再下一步标注上红框。

# 定义基础文件夹路径
# base_dir = r'd:\yolo\XY-YOLO-Tools\train_data\0907'
base_dir = r'd:\yolo\XY-YOLO-Tools\train_data\YIHEDUI\90621'
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

print("完成")