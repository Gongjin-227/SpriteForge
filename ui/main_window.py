# ui/main_window.py
import os, shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox, QApplication,
    QComboBox, QColorDialog, QScrollArea,
    QSplitter
)
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QRect,QPoint
from PySide6.QtGui import (
    QPixmap, QDragEnterEvent, QDropEvent, QColor, QImage,
)
import numpy as np
import cv2
from core.extractor import FrameExtractor
from ui.crop_overlay import CropOverlay
from ui.styles import apply_style
from ui.widgets.thumb_panel import ThumbPanel
from ui.utils import compose_alpha_over_background
from ui.panels.frame_control_panel import FrameControlPanel
from ui.panels.matting_panel import MattingPanel
from ui.panels.export_panel import ExportPanel
from ui.preview_widget import FramePreviewWidget
from core.matting import ChromaKeyMethod, LumaKeyMethod, RMBGMethod, BiRefNetMethod
from dataclasses import dataclass
from PySide6.QtCore import QRect
from ui.utils import compose_alpha_over_background, imread_unicode
from core.models import CleanupRegion
from ui.utils import (
    residual_to_black,
    residual_desaturate,
    semitransparent_to_black,
    semitransparent_to_opaque,
)

# ==================== 主窗口 ====================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpriteForge - 帧提取与抠图")
        self.setMinimumSize(1200, 800)
        self.setAcceptDrops(True)

        self.extractor = FrameExtractor()
        self.crop_rect = QRect()  # 空矩形表示不裁剪
        self.frame_paths = []
        self.fps = 24.0
        self.playback_fps = 24.0
        self.interval = 1
        # 使用 ThumbPanel 管理缩略图和选择
        self.thumb_panel = ThumbPanel()

        self.setup_menubar()
        self.setup_ui()
        apply_style(self)
        self.showMaximized()

        self.orig_width = 0
        self.orig_height = 0
        self._old_crop_for_matted = QRect()  # 进入抠图裁剪前的裁剪区域
        self.show_regions_flag = True


    def setup_menubar(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件")
        file_menu.addAction("导入视频/GIF...", self.import_media)
        file_menu.addAction("导入图片序列文件夹...", self.import_image_sequence_folder)
        file_menu.addSeparator()


    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)

        # ---------- 预览与设置 ----------
        content_layout = QHBoxLayout()
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar = QHBoxLayout()
        self.btn_view_orig = QPushButton("原图")
        self.btn_view_matted = QPushButton("抠图")
        self.btn_view_orig.setCheckable(True)
        self.btn_view_matted.setCheckable(True)
        self.btn_view_orig.setChecked(True)
        for btn in (self.btn_view_orig, self.btn_view_matted):
            btn.clicked.connect(self.on_view_mode_changed)
        toolbar.addWidget(self.btn_view_orig)
        toolbar.addWidget(self.btn_view_matted)

        toolbar.addSpacing(20)
        toolbar.addWidget(QLabel("背景:"))
        self.bg_combo = QComboBox()
        self.bg_combo.addItems(["透明网格", "白色", "黑色", "自定义"])
        self.bg_combo.currentIndexChanged.connect(self.on_bg_changed)
        toolbar.addWidget(self.bg_combo)

        self.btn_crop = QPushButton("✂️ 裁剪")
        self.btn_crop.setCheckable(True)
        self.btn_crop.clicked.connect(self.toggle_crop_mode)
        toolbar.addWidget(self.btn_crop)

        toolbar.addStretch()
        self.btn_fit_window = QPushButton("🔍 适配窗口")
        self.btn_fit_window.setToolTip("将图片缩放到最适合窗口的大小")
        self.btn_fit_window.clicked.connect(self.fit_preview_to_window)
        toolbar.addWidget(self.btn_fit_window)
        preview_layout.addLayout(toolbar)

        self.preview = FramePreviewWidget(main_window=self)

        # 缩略图面板（使用独立的 ThumbPanel 控件）
        thumb_container = QVBoxLayout()
        thumb_container.setContentsMargins(0, 0, 0, 0)
        thumb_container.addWidget(self.thumb_panel)
        thumb_widget = QWidget()
        thumb_widget.setLayout(thumb_container)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.preview)
        splitter.addWidget(thumb_widget)
        splitter.setSizes([600, 450])  # 调整这里改变预览区初始高度
        preview_layout.addWidget(splitter, 1)

        content_layout.addWidget(preview_container, 3)
        self.preview.frame_changed.connect(self.on_preview_frame_changed)
        self.thumb_panel.selection_changed.connect(self.on_thumb_selection_changed)
        self.thumb_panel.thumb_clicked_with_index.connect(self.on_thumb_clicked_jump)

        # ---------- 右侧面板（可滚动）----------
        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.right_scroll.setStyleSheet("QScrollArea { border: none; }")

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(12)
        right_layout.setContentsMargins(0, 0, 4, 0)

        self.frame_ctrl_panel = FrameControlPanel(self.thumb_panel)
        right_layout.addWidget(self.frame_ctrl_panel)

        self.frame_ctrl_panel.step_changed.connect(self.on_step_changed)
        self.frame_ctrl_panel.playback_fps_changed.connect(self.on_playback_fps_changed)

        # 抠图设置面板
        self.matting_panel = MattingPanel()
        right_layout.addWidget(self.matting_panel)

        # 连接抠图信号到主窗口的处理方法
        self.matting_panel.preview_requested.connect(self.preview_matte_current)
        self.matting_panel.batch_requested.connect(self.batch_matte)

        # 导出面板
        self.export_panel = ExportPanel()
        right_layout.addWidget(self.export_panel)

        # 连接导出信号
        self.export_panel.export_orig_clicked.connect(lambda: self.export_frames(matted=False))
        self.export_panel.export_matted_clicked.connect(lambda: self.export_frames(matted=True))



        self.right_scroll.setWidget(right_panel)
        content_layout.addWidget(self.right_scroll, 1)
        main_layout.addLayout(content_layout)

        self.matting_panel.region_add_requested.connect(self.on_region_add_requested)

        self.matting_panel.regions_changed.connect(self.on_regions_changed)
        self.matting_panel.chk_show_regions.toggled.connect(self.on_show_regions_toggled)
        self.matting_panel.global_region_color_requested.connect(self.on_global_region_color_requested)

    def on_global_region_color_requested(self):
        dlg = QColorDialog(self)
        dlg.setWindowTitle("选择统一区域颜色")
        dlg.setCurrentColor(QColor(self.matting_panel.default_region_color))
        if dlg.exec() == QColorDialog.Accepted:
            color = dlg.currentColor()
            self.matting_panel.set_default_region_color(color.name())

    def on_regions_changed(self):
        regions = self.matting_panel.get_regions()
        rects = [r.rect for r in regions]
        self.preview.show_region_highlight(rects, self.matting_panel.selected_region_idx)

    def on_show_regions_toggled(self, checked):
        if checked:
            regions = self.matting_panel.get_regions()
            rects = [r.rect for r in regions]
            self.preview.show_region_highlight(rects, self.matting_panel.selected_region_idx)
        else:
            self.preview.hide_region_overlay()

    def on_region_add_requested(self):
        self.preview.enter_region_add_mode()

    def on_region_selected(self, rect):
        region = self.matting_panel.add_region(rect)
        self.matting_panel.status_label.setText(f"已添加区域：{region.name} ({rect.width()}x{rect.height()})")

    def on_region_cancelled(self):
        self.matting_panel.status_label.setText("区域选择已取消")
        if self.matting_panel.chk_show_regions.isChecked():
            regions = self.matting_panel.get_regions()
            rects = [r.rect for r in regions]
            self.preview.show_region_highlight(rects, self.matting_panel.selected_region_idx)
        else:
            self.preview.hide_region_overlay()

    def get_rmbg_method(self):
        if not hasattr(self, '_rmbg_method'):
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.matting_panel.status_label.setText("正在加载 RMBG-2 模型，请稍候...")
            QApplication.processEvents()
            try:
                self._rmbg_method = RMBGMethod()
            finally:
                QApplication.restoreOverrideCursor()
                self.matting_panel.status_label.setText("")  # 清空提示
                self.frame_ctrl_panel.set_current_frame_info(self.preview.current_idx, len(self.preview.frame_list))
        return self._rmbg_method

    def get_birefnet_method(self, use_corridor=False):
        attr_name = '_birefnet_method_enhanced' if use_corridor else '_birefnet_method_plain'
        if not hasattr(self, attr_name):
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.matting_panel.status_label.setText("正在加载 BiRefNet 模型，请稍候...")
            QApplication.processEvents()
            try:
                method = BiRefNetMethod(use_corridor=use_corridor)
                setattr(self, attr_name, method)
            finally:
                QApplication.restoreOverrideCursor()
                self.matting_panel.status_label.setText("")
        return getattr(self, attr_name)

    def on_thumb_selection_changed(self):
        """缩略图选择变化 → 更新预览与时长"""
        self.sync_workarea_to_preview()
        self.update_duration_display()

    def on_thumb_clicked_jump(self, frame_idx):
        """点击缩略图时，将预览跳转到该帧（如果该帧在工作区内）"""
        workarea = self.thumb_panel.get_workarea_paths()
        path = self.frame_paths[frame_idx]
        if path in workarea:
            target = workarea.index(path)
            self.preview.show_frame(target)

    def toggle_crop_mode(self, checked):
        if checked:
            if self.preview.view_mode == "matted":
                # 保存当前裁剪区域（可能为空）
                self._old_crop_for_matted = QRect(self.crop_rect) if self.crop_rect.isValid() else QRect(0, 0,
                                                                                                         self.orig_width,
                                                                                                         self.orig_height)
                # 临时将裁剪区域设为全图，这样原图读取函数也会读取全图（但实际上我们不会用原图，抠图模式会合成全图）
                self.crop_rect = QRect(0, 0, self.orig_width, self.orig_height)
            self.preview.enter_crop_mode()
        else:
            # 按钮直接取消时（非 Enter/Esc），恢复旧裁剪
            if self.preview.view_mode == "matted" and self._old_crop_for_matted.isValid():
                self.crop_rect = self._old_crop_for_matted
            self.preview.exit_crop_mode()

    def on_crop_applied(self, rect):
        if self.preview.view_mode == "matted":
            # 传入旧裁剪区域进行映射
            self._apply_crop_to_matted(rect, self._old_crop_for_matted)
            self._old_crop_for_matted = QRect()
        else:
            self.crop_rect = QRect(rect)
            self.preview.matted_cache.clear()
            self.preview._composed_pixmap_cache.clear()

        self.preview.exit_crop_mode()
        self.btn_crop.blockSignals(True)
        self.btn_crop.setChecked(False)
        self.btn_crop.blockSignals(False)
        self.sync_workarea_to_preview()

    def _apply_crop_to_matted(self, rect, old_crop):
        r = QRect(rect).normalized()
        new_w = r.width()
        new_h = r.height()
        offset_x = old_crop.x() if old_crop.isValid() else 0
        offset_y = old_crop.y() if old_crop.isValid() else 0

        for path, rgba in self.preview.matted_cache.items():
            h_old, w_old = rgba.shape[:2]
            new_rgba = np.zeros((new_h, new_w, 4), dtype=rgba.dtype)
            # 新裁剪框在旧图像坐标系中的位置
            crop_in_old_x = r.x() - offset_x
            crop_in_old_y = r.y() - offset_y
            src_x1 = max(0, crop_in_old_x)
            src_y1 = max(0, crop_in_old_y)
            src_x2 = min(w_old, crop_in_old_x + new_w)
            src_y2 = min(h_old, crop_in_old_y + new_h)
            if src_x2 > src_x1 and src_y2 > src_y1:
                dst_x1 = src_x1 - crop_in_old_x
                dst_y1 = src_y1 - crop_in_old_y
                new_rgba[dst_y1:dst_y1 + (src_y2 - src_y1), dst_x1:dst_x1 + (src_x2 - src_x1)] = rgba[
                    src_y1:src_y2, src_x1:src_x2]
            self.preview.matted_cache[path] = new_rgba

        self.crop_rect = QRect(r)  # 更新全局裁剪
        self.preview._composed_pixmap_cache.clear()

    def on_crop_cancelled(self):
        if self.preview.view_mode == "matted" and self._old_crop_for_matted.isValid():
            self.crop_rect = self._old_crop_for_matted
        self._old_crop_for_matted = QRect()
        self.preview.exit_crop_mode()
        self.btn_crop.blockSignals(True)
        self.btn_crop.setChecked(False)
        self.btn_crop.blockSignals(False)

    def get_cropped_image(self, path):
        """读取图像，如果设置了裁剪则返回裁剪后的 BGR 图像"""
        img = imread_unicode(path)
        if img is not None and self.crop_rect.isValid() and self.crop_rect.width() > 0:
            r = self.crop_rect
            # 确保裁剪区域不越界
            h, w = img.shape[:2]
            x = max(0, r.x())
            y = max(0, r.y())
            rw = min(r.width(), w - x)
            rh = min(r.height(), h - y)
            if rw > 0 and rh > 0:
                img = img[y:y + rh, x:x + rw]
        return img

    def on_playback_fps_changed(self, value):
        self.playback_fps = value
        if self.preview.frame_list:
            self.preview.fps = value
            if self.preview.is_playing:
                self.preview.timer.stop()
                interval = int(1000 / value) if value > 0 else 41
                self.preview.timer.start(interval)
        self.update_duration_display()

    def update_duration_display(self):
        workarea = self.thumb_panel.get_workarea_paths()
        frame_count = len(workarea)
        if frame_count == 0 or self.playback_fps <= 0:
            self.frame_ctrl_panel.set_duration_text("总时长: 0:00.000")
            return
        total_seconds = frame_count / self.playback_fps
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int((total_seconds - int(total_seconds)) * 1000)
        text = f"总时长: {minutes}:{seconds:02d}.{milliseconds:03d}"
        self.frame_ctrl_panel.set_duration_text(text)


    # ==================== 拖拽 ====================
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path):
                self.load_source(path)
            else:
                ext = Path(path).suffix.lower()
                if ext in FrameExtractor.VIDEO_EXTS or ext in FrameExtractor.GIF_EXTS:
                    self.load_source(path)
                else:
                    QMessageBox.warning(self, "格式不支持", "请拖入图片序列文件夹、视频或GIF文件。")

    # ==================== 导入 ====================
    def import_media(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频或GIF文件", "",
            "媒体文件 (*.mp4 *.mov *.mkv *.webm *.avi *.gif);;所有文件 (*.*)"
        )
        if file_path:
            self.load_source(file_path)

    def import_image_sequence_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择包含图片序列的文件夹")
        if folder:
            self.load_source(folder)

    def load_source(self, path):
        if not os.path.exists(path):
            QMessageBox.warning(self, "错误", "路径不存在")
            return
        try:
            # 修改点1：更新状态文字
            self.frame_ctrl_panel.info_label.setText("正在提取帧，请稍候...")
            QApplication.processEvents()

            # 修改点2：获取步长
            frames, fps = self.extractor.extract(path, step=self.frame_ctrl_panel.get_step())
            if not frames:
                QMessageBox.warning(self, "错误", "未能提取到任何帧")
                return

            self.frame_paths = frames
            # 清空旧区域
            self.matting_panel.clear_regions()
            self.matting_panel.status_label.setText("")  # 清空状态提示

            # 根据“显示区域”勾选状态更新预览 overlay
            if self.matting_panel.chk_show_regions.isChecked():
                self.preview.show_region_highlight([], -1)
            else:
                self.preview.hide_region_overlay()
            if self.frame_paths:
                first_img = imread_unicode(self.frame_paths[0])
                if first_img is not None:
                    self.orig_height, self.orig_width = first_img.shape[:2]

            self.thumb_panel.set_frame_paths(self.frame_paths)
            self.thumb_panel.set_all_selected()

            self.fps = fps
            self.playback_fps = fps
            # 修改点3：设置播放帧率（面板方法会阻塞信号）
            self.frame_ctrl_panel.set_playback_fps(fps)

            self.update_duration_display()
            self.crop_rect = QRect()
            self.preview.matted_cache.clear()
            self.preview._composed_pixmap_cache.clear()
            self.interval = self.frame_ctrl_panel.get_step()

            self.sync_workarea_to_preview()
            self.export_panel.set_export_buttons_enabled(True)

            source_type = "视频" if os.path.isfile(path) else "图片序列"
            self.setWindowTitle(f"SpriteForge - {Path(path).name} ({len(frames)}帧)")
            # 修改点4：设置当前帧信息
            self.frame_ctrl_panel.set_current_frame_info(0, len(frames))

            # 修改点5：更新区间选择器范围（已封装在面板方法中）
            self.frame_ctrl_panel.set_frame_count(len(frames))

        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

        # 导入新素材后自动切换到原图模式
        self.btn_view_orig.setChecked(True)
        self.btn_view_matted.setChecked(False)
        self.preview.view_mode = "original"
        if self.preview.frame_list:
            self.preview.show_frame(self.preview.current_idx)



    def sync_workarea_to_preview(self):
        paths = self.thumb_panel.get_workarea_paths()
        if paths:
            if self.preview.is_playing:
                # 播放中，只更新列表，不重置位置
                self.preview.update_frame_list(paths, self.fps)
            else:
                self.preview.load_frames(paths, self.fps)
        else:
            self.preview.frame_list = []
            self.preview.image_label.clear()
        self.update_duration_display()


    # ==================== 快速选择 ====================


    def fit_preview_to_window(self):
        self.preview.fit_to_view()
        self.preview.update_display()

    def on_step_changed(self, value):
        if self.frame_paths:
            self.setWindowTitle("SpriteForge - 抽帧步长已更改，请重新导入素材")
            self.export_panel.set_export_buttons_enabled(False)


    def on_view_mode_changed(self):
        sender = self.sender()
        btn_map = {
            self.btn_view_orig: "original",
            self.btn_view_matted: "matted",
        }
        for btn, mode in btn_map.items():
            btn.setChecked(btn is sender)
        if sender in btn_map:
            self.preview.view_mode = btn_map[sender]
            self.preview.show_frame(self.preview.current_idx)

    def on_bg_changed(self, idx):
        bg_map = {0: "checker", 1: "white", 2: "black", 3: "custom"}
        self.preview.bg_mode = bg_map.get(idx, "checker")
        if idx == 3:
            color = QColorDialog.getColor(self.preview.custom_bg_color, self, "选择背景颜色")
            if color.isValid():
                self.preview.custom_bg_color = color
        self.preview._composed_pixmap_cache.clear()
        self.preview.show_frame(self.preview.current_idx)
        # 强制立即重绘
        self.preview.image_label.update()

    def get_current_matte_method(self):
        idx = self.matting_panel.matting_mode_combo.currentIndex()
        use_corridor = self.matting_panel.is_corridorkey_enabled()
        enable_region = self.matting_panel.enable_region_cleanup_cb.isChecked()
        regions = self.matting_panel.get_regions()

        if idx == 0:
            color_hex = self.matting_panel.chroma_color.name()
            tol = self.matting_panel.chroma_tol_slider.value()
            if enable_region and regions:
                full_rect = QRect(0, 0, self.orig_width, self.orig_height)
                full_region = CleanupRegion("全域", full_rect, color_hex, tol)
                all_regions = [full_region] + regions
                return ChromaKeyMethod(regions=all_regions, use_corridor=use_corridor)
            else:
                return ChromaKeyMethod(color_hex, tol, use_corridor=use_corridor)
        elif idx == 1:
            thresh = self.matting_panel.luma_thresh_slider.value()
            invert = self.matting_panel.luma_invert_cb.isChecked()
            return LumaKeyMethod(thresh, invert, use_corridor=use_corridor)
        elif idx == 2:
            method = self.get_rmbg_method()
            method.enable_region_cleanup = enable_region
            method.cleanup_regions = regions if enable_region else []
            method.use_corridor = use_corridor
            return method
        elif idx == 3:
            method = self.get_birefnet_method(use_corridor=use_corridor)
            method.enable_region_cleanup = enable_region
            method.cleanup_regions = regions if enable_region else []
            return method

    def preview_matte_current(self):
        if not self.preview.frame_list:
            return
        path = self.preview.frame_list[self.preview.current_idx]
        img_bgr = self.get_cropped_image(path)
        if img_bgr is None:
            QMessageBox.warning(self, "错误", "无法读取当前帧")
            return
        method = self.get_current_matte_method()
        if getattr(method, 'use_corridor', False):
            self._preload_corridorkey_if_needed()
        rgba = method.process(img_bgr)
        rgba = self.apply_residual_postprocess(rgba)
        self.preview.matted_cache[path] = rgba
        self.preview._composed_pixmap_cache.pop(path, None)

        if self.preview.view_mode != "matted":
            self.preview.view_mode = "matted"
            self.btn_view_orig.setChecked(False)
            self.btn_view_matted.setChecked(True)

        self.preview.show_frame(self.preview.current_idx)

    def batch_matte(self):
        workarea = self.thumb_panel.get_workarea_paths()
        if not workarea:
            QMessageBox.warning(self, "无工作区帧", "请先在缩略图中选取要抠图的帧。")
            return
        method = self.get_current_matte_method()
        if getattr(method, 'use_corridor', False):
            self._preload_corridorkey_if_needed()
        # 显示进度条并设置范围
        self.export_panel.progress_bar.setVisible(True)
        self.export_panel.progress_bar.setMaximum(len(workarea))
        QApplication.processEvents()
        if hasattr(self, 'right_scroll'):
            vbar = self.right_scroll.verticalScrollBar()
            vbar.setValue(vbar.maximum())


        for i, path in enumerate(workarea):
            img_bgr = self.get_cropped_image(path)
            if img_bgr is not None:
                rgba = method.process(img_bgr)
                rgba = self.apply_residual_postprocess(rgba)
                self.preview.matted_cache[path] = rgba
                # 立即为这一帧生成合成缓存（避免播放时卡顿）
                composed = self.preview.compose_matted(rgba)
                self.preview._composed_pixmap_cache[path] = composed
            self.export_panel.progress_bar.setValue(i + 1)
            QApplication.processEvents()
        self.export_panel.progress_bar.setVisible(False)
        # 自动切换到抠图预览模式
        if self.preview.view_mode != "matted":
            self.preview.view_mode = "matted"
            self.btn_view_orig.setChecked(False)
            self.btn_view_matted.setChecked(True)
        self.preview.show_frame(self.preview.current_idx)
        QMessageBox.information(self, "完成", f"已抠图 {len(workarea)} 帧。")

    def export_frames(self, matted=False):
        workarea = self.thumb_panel.get_workarea_paths()
        if not workarea:
            print("Workarea is empty! No frames selected.")
            QMessageBox.warning(self, "无工作区帧", "请先在缩略图中选取要导出的帧。")
            return
        out_dir = self.export_panel.get_output_dir()
        if not out_dir:
            QMessageBox.warning(self, "提示", "请先选择输出目录")
            return

        if matted:
            # 导出抠图帧
            export_list = list(workarea)   # 抠图导出也使用 export_list
            missing = [p for p in export_list if p not in self.preview.matted_cache]
            if missing:
                reply = QMessageBox.question(self, "未抠图", f"{len(missing)} 帧尚未抠图，是否立即抠图？",
                                             QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.batch_matte()
                else:
                    return
            os.makedirs(out_dir, exist_ok=True)
            self.export_panel.progress_bar.setVisible(True)
            self.export_panel.progress_bar.setMaximum(len(export_list))
            for i, path in enumerate(export_list):
                rgba = self.preview.matted_cache.get(path)
                if rgba is not None:
                    save_path = os.path.join(out_dir, Path(path).name)
                    if self.matting_panel.transparent_png_cb.isChecked():
                        success, encoded = cv2.imencode('.png', rgba)  # 直接使用 BGRA
                        if success:
                            with open(save_path, 'wb') as f:
                                f.write(encoded.tobytes())
                    else:
                        composed = compose_alpha_over_background(rgba, bg_color=QColor(255, 255, 255))
                        composed.save(save_path)

                    if self.matting_panel.export_mask_cb.isChecked():
                        mask = rgba[:, :, 3]
                        mask_path = os.path.join(out_dir, f"mask_{Path(path).stem}.png")
                        success_mask, encoded_mask = cv2.imencode('.png', mask)
                        if success_mask:
                            with open(mask_path, 'wb') as f:
                                f.write(encoded_mask.tobytes())
                self.export_panel.progress_bar.setValue(i + 1)
                QApplication.processEvents()
            self.export_panel.progress_bar.setVisible(False)

            # 抠图导出成功提示（带打开文件夹）
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("导出完成")
            msg_box.setText(f"已导出抠图帧到:\n{out_dir}")
            msg_box.setIcon(QMessageBox.Information)
            btn_ok = msg_box.addButton("确定", QMessageBox.AcceptRole)
            btn_open = msg_box.addButton("打开文件夹", QMessageBox.ActionRole)
            msg_box.exec()
            if msg_box.clickedButton() == btn_open:
                os.startfile(out_dir)

        else:
            # 导出原始帧
            export_list = list(workarea)
            os.makedirs(out_dir, exist_ok=True)
            self.export_panel.progress_bar.setVisible(True)
            self.export_panel.progress_bar.setMaximum(len(export_list))
            for i, src in enumerate(export_list):
                dst = os.path.join(out_dir, os.path.basename(src))
                img = self.get_cropped_image(src)
                if img is not None:
                    success, encoded = cv2.imencode('.png', img)
                    if success:
                        with open(dst, 'wb') as f:
                            f.write(encoded.tobytes())
                else:
                    shutil.copy2(src, dst)  # shutil.copy2 支持中文路径，无需修改
                self.export_panel.progress_bar.setValue(i + 1)
                QApplication.processEvents()
            self.export_panel.progress_bar.setVisible(False)

            # 原始帧导出成功提示（带打开文件夹）
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("导出完成")
            msg_box.setText(f"已导出 {len(export_list)} 帧到:\n{out_dir}")
            msg_box.setIcon(QMessageBox.Information)
            btn_ok = msg_box.addButton("确定", QMessageBox.AcceptRole)
            btn_open = msg_box.addButton("打开文件夹", QMessageBox.ActionRole)
            msg_box.exec()
            if msg_box.clickedButton() == btn_open:
                os.startfile(out_dir)

    def on_preview_frame_changed(self, idx, total):
        self.frame_ctrl_panel.set_current_frame_info(idx, total)

    def closeEvent(self, event):
        # 停止播放和定时器
        self.preview.stop()
        self.preview.timer.stop()
        # 清空帧列表，防止后续 update_display 再尝试读取文件
        self.preview.frame_list = []
        self.preview.image_label.clear()
        # 现在可以安全删除临时文件
        self.extractor.cleanup()
        event.accept()

    def _preload_corridorkey_if_needed(self):
        """如果 CorridorKey 引擎尚未加载，显示提示并加载一次"""
        from core.matting import _load_corridorkey_engine

        # 检查缓存（函数属性缓存，直接导入后调用即可判断）
        if getattr(_load_corridorkey_engine, "cache", {}):
            # 已加载过，直接返回
            return

        self.matting_panel.status_label.setText("正在加载 CorridorKey 模型，请稍候...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            # 使用默认设备/颜色加载（后续可扩展传递参数）
            _load_corridorkey_engine()
        finally:
            QApplication.restoreOverrideCursor()
            self.matting_panel.status_label.setText("")

    def apply_residual_postprocess(self, rgba):
        """根据面板设置应用残边处理"""
        if not self.matting_panel.is_residual_enabled():
            return rgba

        mode = self.matting_panel.get_residual_mode()
        if mode == "green_to_black":
            return residual_to_black(rgba)
        elif mode == "green_desaturate":
            return residual_desaturate(rgba)
        elif mode == "semitransparent_to_black":
            return semitransparent_to_black(rgba)
        elif mode == "semitransparent_to_opaque":
            return semitransparent_to_opaque(rgba)
        else:
            return rgba