# core/extractor.py
import os
import tempfile
import shutil
from pathlib import Path
import re
import cv2
from PIL import Image
import numpy as np

class FrameExtractor:
    VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.wmv', '.flv'}
    IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff', '.tif'}
    GIF_EXTS = {'.gif'}

    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="spriteforge_frames_")

    def _clear_temp(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def extract(self, source_path: str, output_dir: str = None, step: int = 1):
        """
        统一入口：
        - 视频/GIF：解码帧到临时目录（或指定输出目录）
        - 图片序列文件夹：直接扫描图片文件，返回原始路径
        返回 (帧路径列表, 帧率)
        """
        ext = Path(source_path).suffix.lower()
        if os.path.isfile(source_path) and ext in self.VIDEO_EXTS:
            return self._extract_video(source_path, output_dir, step)
        elif os.path.isfile(source_path) and ext in self.GIF_EXTS:
            return self._extract_gif(source_path, output_dir, step)
        elif os.path.isdir(source_path):
            return self._extract_image_sequence(source_path, step)
        else:
            raise ValueError(f"不支持的路径或格式：{source_path}")

    def _extract_video(self, video_path: str, output_dir: str, step: int):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError(f"无法打开视频：{video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 24.0

        out_dir = output_dir or os.path.join(self.temp_dir, "video_frames")
        os.makedirs(out_dir, exist_ok=True)

        frames = []
        idx = 0
        saved_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if idx % step == 0:
                saved_idx += 1
                out_path = os.path.join(out_dir, f"frame_{saved_idx:05d}.png")
                cv2.imwrite(out_path, frame)
                frames.append(out_path)
            idx += 1
        cap.release()
        return frames, fps

    def _extract_gif(self, gif_path: str, output_dir: str, step: int):
        gif = Image.open(gif_path)
        out_dir = output_dir or os.path.join(self.temp_dir, "gif_frames")
        os.makedirs(out_dir, exist_ok=True)

        # 获取帧率
        durations = []
        try:
            while True:
                durations.append(gif.info['duration'])
                gif.seek(gif.tell() + 1)
        except EOFError:
            pass
        avg_duration = sum(durations) / len(durations) if durations else 100
        fps = 1000.0 / avg_duration if avg_duration else 10.0

        frames = []
        frame_idx = 0
        saved_idx = 0
        gif.seek(0)
        while True:
            if frame_idx % step == 0:
                saved_idx += 1
                out_path = os.path.join(out_dir, f"frame_{saved_idx:05d}.png")
                gif.save(out_path, 'PNG')
                frames.append(out_path)
            frame_idx += 1
            try:
                gif.seek(frame_idx)
            except EOFError:
                break
        return frames, fps

    def _extract_image_sequence(self, folder: str, step: int):
        """直接返回图片文件路径，不复制"""
        all_files = os.listdir(folder)
        pattern = re.compile(r'\d+')
        image_files = []
        for f in all_files:
            if Path(f).suffix.lower() in self.IMAGE_EXTS:
                image_files.append(f)

        # 自然排序（按最后出现的数字）
        def sort_key(fname):
            numbers = pattern.findall(fname)
            return int(numbers[-1]) if numbers else 0

        image_files.sort(key=sort_key)

        frames = []
        for i, fname in enumerate(image_files):
            if i % step == 0:
                frames.append(os.path.join(folder, fname))
        return frames, 24.0

    def cleanup(self):
        self._clear_temp()