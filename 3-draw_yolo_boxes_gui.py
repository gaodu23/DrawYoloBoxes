#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YOLO标注数据可视化工具 - GUI版本

画红框，保留exif。
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import threading
import queue
import time

# 导入现有的绘制函数模块
try:
    from draw_yolo_boxes import process_dataset
except ImportError:
    messagebox.showerror("错误", "无法导入draw_yolo_boxes.py模块，请确保该文件与本程序在同一目录下。")
    sys.exit(1)

class RedirectText:
    """用于将控制台输出重定向到Tkinter文本框的类"""
    
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.queue = queue.Queue()
        self.updating = True
        threading.Thread(target=self.update_loop, daemon=True).start()
    
    def write(self, string):
        self.queue.put(string)
    
    def flush(self):
        pass
    
    def update_loop(self):
        while self.updating:
            try:
                while True:
                    string = self.queue.get_nowait()
                    self.text_widget.configure(state="normal")
                    self.text_widget.insert("end", string)
                    self.text_widget.see("end")
                    self.text_widget.configure(state="disabled")
                    self.queue.task_done()
            except queue.Empty:
                time.sleep(0.1)
    
    def stop_update(self):
        self.updating = False


class YOLOVisualizerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("YOLO标注数据可视化工具")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)
        
        self.setup_variables()
        self.create_widgets()
        self.setup_layout()
    
    def setup_variables(self):
        """初始化变量"""
        self.folder_path = tk.StringVar()
        self.output_var = tk.StringVar(value="output_with_boxes")
        self.generate_csv_var = tk.BooleanVar(value=True)
        self.generate_kml_var = tk.BooleanVar(value=True)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.processing = False
        self.progress_queue = queue.Queue()
        self.stop_progress_update = False
        
    def create_widgets(self):
        """创建GUI组件"""
        # 样式配置
        style = ttk.Style()
        style.configure("TFrame", background="#f0f0f0")
        style.configure("TButton", font=('Arial', 11))
        style.configure("TLabel", font=('Arial', 11), background="#f0f0f0")
        style.configure("Header.TLabel", font=('Arial', 14, 'bold'), background="#f0f0f0")
        
        # 主窗口容器
        self.main_frame = ttk.Frame(self.root, padding=15, style="TFrame")
        
        # 顶部标题
        self.title_label = ttk.Label(
            self.main_frame, 
            text="YOLO标注数据可视化工具", 
            style="Header.TLabel"
        )
        
        # 文件夹选择区域
        self.folder_frame = ttk.Frame(self.main_frame, style="TFrame")
        self.folder_label = ttk.Label(
            self.folder_frame, 
            text="数据集文件夹:", 
            style="TLabel"
        )
        self.folder_entry = ttk.Entry(
            self.folder_frame, 
            textvariable=self.folder_path, 
            width=50
        )
        self.browse_button = ttk.Button(
            self.folder_frame, 
            text="浏览...", 
            command=self.browse_folder
        )
        
        # 选项区域
        self.options_frame = ttk.Frame(self.main_frame, style="TFrame")
        
        # 输出文件夹
        self.output_label = ttk.Label(
            self.options_frame, 
            text="输出文件夹名:", 
            style="TLabel"
        )
        self.output_entry = ttk.Entry(
            self.options_frame, 
            textvariable=self.output_var, 
            width=20
        )
        
        # 复选框选项
        self.csv_check = ttk.Checkbutton(
            self.options_frame, 
            text="生成GPS信息CSV文件", 
            variable=self.generate_csv_var
        )
        self.kml_check = ttk.Checkbutton(
            self.options_frame, 
            text="生成KML文件", 
            variable=self.generate_kml_var
        )
        self.overwrite_check = ttk.Checkbutton(
            self.options_frame, 
            text="覆盖原图片（不创建输出文件夹）", 
            variable=self.overwrite_var,
            command=self.toggle_overwrite
        )
        
        # 目录格式说明
        self.format_frame = ttk.LabelFrame(
            self.main_frame, 
            text="数据集目录格式要求", 
            padding=10
        )
        self.format_text = tk.Text(
            self.format_frame, 
            height=6, 
            width=70, 
            wrap=tk.WORD, 
            font=('Courier', 10),
            bg="#fafafa"
        )
        self.format_text.insert(tk.END, "程序需要以下文件结构:\n\n")
        self.format_text.insert(tk.END, "selected_folder/\n")
        self.format_text.insert(tk.END, "├── images/         # 图片文件夹\n")
        self.format_text.insert(tk.END, "├── labels/         # YOLO标注文件夹\n")
        self.format_text.insert(tk.END, "└── classes.txt     # 类别名称文件")
        self.format_text.configure(state="disabled")
        
        # 控制按钮
        self.buttons_frame = ttk.Frame(self.main_frame, style="TFrame")
        self.process_button = ttk.Button(
            self.buttons_frame, 
            text="开始处理", 
            command=self.start_processing
        )
        self.cancel_button = ttk.Button(
            self.buttons_frame, 
            text="取消", 
            command=self.root.destroy
        )
        
        # 进度区域
        self.progress_frame = ttk.Frame(self.main_frame, style="TFrame")
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, 
            orient="horizontal", 
            length=500, 
            mode="determinate"
        )
        self.progress_label = ttk.Label(
            self.progress_frame,
            text="0%",
            style="TLabel"
        )
        
        # 日志输出区域
        self.log_frame = ttk.LabelFrame(
            self.main_frame, 
            text="处理日志", 
            padding=10
        )
        self.log_text = tk.Text(
            self.log_frame, 
            height=10, 
            width=70, 
            wrap=tk.WORD, 
            font=('Courier', 9)
        )
        self.log_text.configure(state="disabled")
        self.log_scroll = ttk.Scrollbar(
            self.log_frame, 
            orient="vertical", 
            command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=self.log_scroll.set)
        
        # 重定向控制台输出到日志文本框
        self.text_redirector = RedirectText(self.log_text)
        sys.stdout = self.text_redirector
    
    def setup_layout(self):
        """设置布局"""
        # 主框架填充整个窗口
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题居中
        self.title_label.pack(pady=(0, 15))
        
        # 文件夹选择区域
        self.folder_frame.pack(fill=tk.X, pady=(0, 10))
        self.folder_label.pack(side=tk.LEFT, padx=(0, 5))
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.browse_button.pack(side=tk.LEFT, padx=(5, 0))
        
        # 选项区域
        self.options_frame.pack(fill=tk.X, pady=(0, 10))
        self.output_label.pack(side=tk.LEFT, padx=(0, 5))
        self.output_entry.pack(side=tk.LEFT, padx=(0, 20))
        self.csv_check.pack(side=tk.LEFT, padx=5)
        self.kml_check.pack(side=tk.LEFT, padx=5)
        self.overwrite_check.pack(side=tk.LEFT, padx=5)
        
        # 目录格式说明
        self.format_frame.pack(fill=tk.X, pady=(0, 10))
        self.format_text.pack(fill=tk.X)
        
        # 按钮区域
        self.buttons_frame.pack(fill=tk.X, pady=(0, 5))
        self.process_button.pack(side=tk.RIGHT, padx=5)
        self.cancel_button.pack(side=tk.RIGHT, padx=5)
        
        # 进度条
        self.progress_frame.pack(fill=tk.X, pady=(0, 10))
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # 日志区域
        self.log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    def browse_folder(self):
        """浏览文件夹对话框"""
        folder_selected = filedialog.askdirectory(
            title="选择数据集文件夹",
            initialdir=os.getcwd()
        )
        if folder_selected:
            self.folder_path.set(folder_selected)
            
            # 检查文件夹结构
            folder_path = Path(folder_selected)
            images_dir = folder_path / "images"
            labels_dir = folder_path / "labels"
            classes_file = folder_path / "classes.txt"
            
            structure_valid = True
            missing_parts = []
            
            if not images_dir.exists() or not images_dir.is_dir():
                structure_valid = False
                missing_parts.append("images文件夹")
            
            if not labels_dir.exists() or not labels_dir.is_dir():
                structure_valid = False
                missing_parts.append("labels文件夹")
            
            if not classes_file.exists() or not classes_file.is_file():
                structure_valid = False
                missing_parts.append("classes.txt文件")
            
            if not structure_valid:
                messagebox.showwarning(
                    "文件夹结构警告", 
                    f"所选文件夹缺少以下部分：\n{', '.join(missing_parts)}\n\n"
                    f"请确保文件夹结构符合要求。"
                )
    
    def toggle_overwrite(self):
        """切换覆盖模式"""
        if self.overwrite_var.get():
            self.output_entry.configure(state="disabled")
        else:
            self.output_entry.configure(state="normal")
    
    def start_processing(self):
        """开始处理数据集"""
        if self.processing:
            return
        
        folder_path = self.folder_path.get().strip()
        if not folder_path:
            messagebox.showerror("错误", "请选择数据集文件夹")
            return
        
        # 检查文件夹是否存在
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            messagebox.showerror("错误", "所选文件夹不存在")
            return
        
        # 检查文件夹结构
        images_dir = os.path.join(folder_path, "images")
        labels_dir = os.path.join(folder_path, "labels")
        classes_file = os.path.join(folder_path, "classes.txt")
        
        structure_valid = True
        missing_parts = []
        
        if not os.path.exists(images_dir) or not os.path.isdir(images_dir):
            structure_valid = False
            missing_parts.append("images文件夹")
        
        if not os.path.exists(labels_dir) or not os.path.isdir(labels_dir):
            structure_valid = False
            missing_parts.append("labels文件夹")
        
        if not os.path.exists(classes_file) or not os.path.isfile(classes_file):
            structure_valid = False
            missing_parts.append("classes.txt文件")
        
        if not structure_valid:
            result = messagebox.askyesno(
                "文件夹结构警告", 
                f"所选文件夹缺少以下部分：\n{', '.join(missing_parts)}\n\n"
                f"是否仍要继续处理？"
            )
            if not result:
                return
        
        # 确定输出路径
        if self.overwrite_var.get():
            output_dir = None
        else:
            output_name = self.output_var.get().strip()
            if not output_name:
                output_name = "output_with_boxes"
            output_dir = os.path.join(folder_path, output_name)
        
        # 禁用UI组件
        self.process_button.configure(state="disabled")
        self.browse_button.configure(state="disabled")
        self.folder_entry.configure(state="disabled")
        if not self.overwrite_var.get():
            self.output_entry.configure(state="disabled")
        self.csv_check.configure(state="disabled")
        self.kml_check.configure(state="disabled")
        self.overwrite_check.configure(state="disabled")
        
        # 重置进度条
        self.progress_bar["value"] = 0
        self.progress_label.config(text="0%")
        self.stop_progress_update = False
        
        # 清空进度队列
        while not self.progress_queue.empty():
            try:
                self.progress_queue.get_nowait()
            except queue.Empty:
                break
        
        # 清空日志
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")
        
        self.processing = True
        
        # 启动进度更新线程
        threading.Thread(
            target=self.progress_update_loop,
            daemon=True
        ).start()
        
        # 在新线程中处理数据集
        threading.Thread(
            target=self.process_dataset_thread,
            args=(images_dir, labels_dir, classes_file, output_dir),
            daemon=True
        ).start()
    
    def update_progress(self, current, total):
        """更新进度信息"""
        self.progress_queue.put((current, total))
    
    def progress_update_loop(self):
        """进度更新循环"""
        while not self.stop_progress_update:
            try:
                # 检查进度队列
                if not self.progress_queue.empty():
                    current, total = self.progress_queue.get()
                    if total > 0:
                        percent = int(current / total * 100)
                        # 在GUI线程中更新进度条
                        self.root.after(0, self.update_progress_bar, percent)
                
                # 短暂休眠
                time.sleep(0.1)
            except Exception as e:
                print(f"进度更新出错: {str(e)}")
                time.sleep(0.5)
    
    def update_progress_bar(self, percent):
        """更新进度条UI"""
        self.progress_bar["value"] = percent
        self.progress_label.config(text=f"{percent}%")
    
    def process_dataset_thread(self, images_dir, labels_dir, classes_file, output_dir):
        """在单独的线程中处理数据集"""
        try:
            # 首先获取图片总数
            image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
            image_files = []
            for file in os.listdir(images_dir):
                file_path = os.path.join(images_dir, file)
                if os.path.isfile(file_path) and os.path.splitext(file)[1].lower() in image_extensions:
                    image_files.append(file_path)
            
            total_images = len(image_files)
            
            if total_images == 0:
                print("未找到图片文件！")
                self.root.after(0, self.processing_completed, False, "未找到图片文件")
                return
            
            # 创建一个进度回调函数
            def progress_callback(current, total):
                self.update_progress(current, total)
            
            # 调用修改后的处理函数
            self.process_with_progress(
                images_dir=images_dir,
                labels_dir=labels_dir,
                classes_file=classes_file,
                output_dir=output_dir,
                box_color=(0, 0, 255),  # 红色边界框
                generate_csv=self.generate_csv_var.get(),
                generate_kml_file=self.generate_kml_var.get(),
                progress_callback=progress_callback
            )
            
            # 处理完成后在GUI线程中更新UI
            self.root.after(0, self.processing_completed, True)
        except Exception as e:
            print(f"处理过程中发生错误: {str(e)}")
            # 处理出错后在GUI线程中更新UI
            self.root.after(0, self.processing_completed, False, str(e))
    
    def process_with_progress(self, images_dir, labels_dir, classes_file, output_dir, 
                             box_color, generate_csv, generate_kml_file, progress_callback):
        """带进度回调的数据集处理函数"""
        # 这个函数基本上是process_dataset的修改版，但会在处理每张图片后更新进度
        from draw_yolo_boxes import read_class_names, draw_boxes_on_image, generate_gps_csv, generate_kml
        
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
        
        # 更新初始进度
        progress_callback(0, total_count)
        
        for image_file in image_files:
            # 构造对应的标注文件路径
            label_file = labels_dir / f"{image_file.stem}.txt"
            
            # 构造输出路径
            if output_dir:
                output_file = output_dir / image_file.name
            else:
                output_file = None
            
            # 处理图片
            success = draw_boxes_on_image(
                str(image_file), 
                str(label_file), 
                classes_file, 
                str(output_file) if output_file else None, 
                box_color
            )
            
            if success:
                processed_count += 1
                print(f"进度: {processed_count}/{total_count} - {image_file.name}")
            else:
                print(f"处理失败: {image_file.name}")
                
            # 更新进度
            progress_callback(processed_count, total_count)
        
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
    
    def processing_completed(self, success, error_message=None):
        """处理完成后的回调函数"""
        # 停止进度更新
        self.stop_progress_update = True
        
        # 设置进度条为100%（如果成功）
        if success:
            self.progress_bar["value"] = 100
            self.progress_label.config(text="100%")
        
        # 恢复UI组件
        self.process_button.configure(state="normal")
        self.browse_button.configure(state="normal")
        self.folder_entry.configure(state="normal")
        if not self.overwrite_var.get():
            self.output_entry.configure(state="normal")
        self.csv_check.configure(state="normal")
        self.kml_check.configure(state="normal")
        self.overwrite_check.configure(state="normal")
        
        self.processing = False
        
        # 显示处理结果
        if success:
            messagebox.showinfo("处理完成", "YOLO标注数据处理已完成！")
        else:
            messagebox.showerror("处理失败", f"处理过程中发生错误:\n{error_message}")
    
    def on_closing(self):
        """窗口关闭事件处理"""
        if self.processing:
            result = messagebox.askyesno("警告", "处理正在进行中，确定要退出吗？")
            if not result:
                return
        
        # 停止进度更新
        self.stop_progress_update = True
        
        # 恢复标准输出
        sys.stdout = sys.__stdout__
        
        # 停止文本重定向更新
        if hasattr(self, 'text_redirector'):
            self.text_redirector.stop_update()
        
        self.root.destroy()


def main():
    root = tk.Tk()
    app = YOLOVisualizerGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
