# ui/preview_widget.py
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QScrollArea
)
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QRect, QPoint
from PySide6.QtGui import QPixmap, QColor, QImage
from ui.crop_overlay import CropOverlay
from ui.utils import compose_alpha_over_background, imread_unicode
from ui.region_select_overlay import RegionSelectOverlay


# ==================== 预览组件 ====================
class FramePreviewWidget(QWidget):
    frame_changed = Signal(int, int)

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.mw = main_window  # 引用主窗口
        self.frame_list = []
        self.current_idx = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
        self.is_playing = False
        self.fps = 24.0
        self.playback_fps = 24.0

        self.matted_cache = {}
        self.view_mode = "original"
        self.bg_mode = "checker"
        self.custom_bg_color = QColor(128, 128, 128)
        self.scale_factor = 1.0
        self._composed_pixmap_cache = {}  # path -> QPixmap

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: transparent; border: none;")
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area)

        # ---- 右下角播放控制按钮（父控件为 self） ----
        self.btn_play = QPushButton("▶", self)  # 播放
        self.btn_stop = QPushButton("■", self)  # 停止
        self.btn_prev = QPushButton("←", self)  # 上一帧
        self.btn_next = QPushButton("→", self)  # 下一帧

        for btn in (self.btn_play, self.btn_stop, self.btn_prev, self.btn_next):
            btn.setFixedSize(32, 32)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255,255,255,220);
                    border: 1px solid #999;
                    border-radius: 4px;
                    font-size: 14px;
                    color: #000000;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: rgba(255,255,255,255);
                    border: 1px solid #4CAF50;
                }
            """)

        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_prev.clicked.connect(self.prev_frame)
        self.btn_next.clicked.connect(self.next_frame)



        # 提升按钮层级
        self.btn_play.raise_()
        self.btn_stop.raise_()
        self.btn_prev.raise_()
        self.btn_next.raise_()

        # 裁剪覆盖层
        self.crop_overlay = CropOverlay(self.scroll_area.viewport())
        self.crop_overlay.hide()
        self.crop_overlay.cropApplied.connect(self._on_crop_applied)
        self.crop_overlay.cropCancelled.connect(self._on_crop_cancelled)

        self.region_overlay = RegionSelectOverlay(self.scroll_area.viewport())
        self.region_overlay.hide()
        self.region_overlay.regionSelected.connect(self._on_region_selected)
        self.region_overlay.regionCancelled.connect(self._on_region_cancelled)

        # 在所有组件创建完成后，再安装事件过滤器
        self.scroll_area.viewport().installEventFilter(self)



    def update_frame_list(self, frame_paths, fps=None):
        """更新帧列表，但尽量保持当前播放位置不变"""
        # 记录当前帧路径（如果存在）
        current_path = None
        if self.frame_list and 0 <= self.current_idx < len(self.frame_list):
            current_path = self.frame_list[self.current_idx]

        self.frame_list = frame_paths
        if fps is not None:
            self.fps = fps

        # 尝试恢复当前帧位置
        if current_path and current_path in self.frame_list:
            self.current_idx = self.frame_list.index(current_path)
        else:
            self.current_idx = 0

        # 确保不越界
        if self.current_idx >= len(self.frame_list):
            self.current_idx = 0

        # 如果没有帧，清空显示
        if not self.frame_list:
            self.image_label.clear()
            return

        self.update_display()
        self.frame_changed.emit(self.current_idx, len(self.frame_list))

    def clear_composed_cache(self):
        self._composed_pixmap_cache.clear()

    def enter_crop_mode(self):
        self._pre_crop_view_mode = self.view_mode
        self.crop_overlay.show()
        self.update_display()
        self.crop_overlay.set_scale_factor(self.scale_factor)
        # 任何模式下都不允许拖出边界
        self.crop_overlay.enter_crop_mode(QRect(), allow_out_of_bounds=False)
        self.crop_overlay.setFocus()

    def exit_crop_mode(self):
        self.crop_overlay.exit_crop_mode()
        # 恢复之前的视图模式
        if hasattr(self, '_pre_crop_view_mode'):
            self.view_mode = self._pre_crop_view_mode
        # 恢复后需要刷新显示（外部会调用 sync_workarea_to_preview）

    def _sync_crop_overlay_rect(self):
        pos_in_viewport = self.image_label.mapTo(self.scroll_area.viewport(), QPoint(0, 0))
        image_rect = QRect(pos_in_viewport, self.image_label.size())
        self.crop_overlay.setGeometry(self.scroll_area.viewport().rect())
        self.crop_overlay.set_image_rect(image_rect)
        self.crop_overlay.set_scale_factor(self.scale_factor)  # 确保缩放同步

    def _on_crop_applied(self, rect):
        if self.mw:
            self.mw.on_crop_applied(rect)

    def _on_crop_cancelled(self):
        if self.mw:
            self.mw.on_crop_cancelled()

    def resizeEvent(self, event):
        # 先让基类处理（更新内部布局等）
        super().resizeEvent(event)

        # 移动右下角播放控制按钮（此时 self.width()/height() 已更新）
        buttons = [self.btn_play, self.btn_stop, self.btn_prev, self.btn_next]
        x = self.width() - 8
        y = self.height() - 40
        for btn in reversed(buttons):
            x -= btn.width() + 4
            btn.move(x, y)

        # 同步裁剪和区域 overlay 的几何与缩放
        if hasattr(self, 'crop_overlay') and self.crop_overlay.isVisible():
            self._sync_crop_overlay_rect()
        if hasattr(self, 'region_overlay') and self.region_overlay.isVisible():
            self._sync_region_overlay_rect()


    def eventFilter(self, obj, event):
        if obj is self.scroll_area.viewport() and event.type() == QEvent.Wheel:
            modifiers = event.modifiers()
            if modifiers & Qt.ControlModifier:
                delta = event.angleDelta().y()
                factor = 1.15 if delta > 0 else 0.85
                self.scale_factor *= factor
                self.scale_factor = max(0.1, min(10.0, self.scale_factor))
                self.update_display()
                if hasattr(self, 'region_overlay') and self.region_overlay.isVisible():
                    self._sync_region_overlay_rect()
                return True
            elif modifiers & Qt.ShiftModifier:
                h_bar = self.scroll_area.horizontalScrollBar()
                if h_bar:
                    delta = event.angleDelta().y()
                    new_val = h_bar.value() - (delta // 8)
                    h_bar.setValue(max(0, min(h_bar.maximum(), new_val)))
                return True
            return False
        if self.region_overlay.isVisible():
            self._sync_region_overlay_rect()
        return super().eventFilter(obj, event)

    def fit_to_view(self):
        if not self.frame_list:
            self.scale_factor = 1.0
            return
        path = self.frame_list[0]
        pix = QPixmap(path)
        if pix.isNull():
            self.scale_factor = 1.0
            return
        pw = pix.width()
        ph = pix.height()
        # 如果设置了裁剪，则使用裁剪后的有效尺寸
        if self.mw and self.mw.crop_rect.isValid():
            r = self.mw.crop_rect
            x = max(0, r.x())
            y = max(0, r.y())
            rw = min(r.width(), pw - x)
            rh = min(r.height(), ph - y)
            if rw > 0 and rh > 0:
                pw, ph = rw, rh
        if pw <= 0 or ph <= 0:
            self.scale_factor = 1.0
            return
        view_size = self.scroll_area.viewport().size()
        if view_size.width() > 0 and view_size.height() > 0:
            scale_w = view_size.width() / pw
            scale_h = view_size.height() / ph
            self.scale_factor = min(scale_w, scale_h) * 0.95
        else:
            self.scale_factor = 1.0

    def reset_zoom(self):
        self.scale_factor = 1.0
        self.update_display()

    def load_frames(self, frame_paths, fps=24.0):
        self.frame_list = frame_paths
        self.fps = fps
        self.current_idx = 0
        if frame_paths:
            self.fit_to_view()
            self.show_frame(0)
        else:
            self.image_label.clear()

    def show_frame(self, idx):
        if not self.frame_list:
            return
        self.current_idx = idx % len(self.frame_list)
        self.update_display()
        self.frame_changed.emit(self.current_idx, len(self.frame_list))

    def update_display(self):
        if not self.frame_list:
            return
        path = self.frame_list[self.current_idx]
        pixmap = None

        if self.view_mode == "original":
            img = imread_unicode(path)
            if img is not None:
                # 裁剪模式下忽略裁剪，显示完整原图
                if not self.crop_overlay.isVisible() and self.mw and self.mw.crop_rect.isValid():
                    r = self.mw.crop_rect
                    h, w = img.shape[:2]
                    x = max(0, r.x());
                    y = max(0, r.y())
                    rw = min(r.width(), w - x);
                    rh = min(r.height(), h - y)
                    if rw > 0 and rh > 0:
                        img = img[y:y + rh, x:x + rw]
                # 将 numpy 转为 QPixmap
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                bytes_per_line = ch * w
                qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg.copy())
            else:
                pixmap = QPixmap(path)
        elif self.view_mode == "matted":
            if self.crop_overlay.isVisible():
                # 裁剪模式：创建全尺寸抠图合成
                full_w = self.mw.orig_width
                full_h = self.mw.orig_height
                # 全透明画布
                full_rgba = np.zeros((full_h, full_w, 4), dtype=np.uint8)
                # 将当前帧的抠图缓存放入正确位置（基于旧裁剪区域）
                old_crop = self.mw._old_crop_for_matted
                rgba = self.matted_cache.get(path)
                if rgba is not None:
                    h, w = rgba.shape[:2]
                    # 计算放置位置（旧裁剪区域左上角在全图中的坐标）
                    px = old_crop.x() if old_crop.isValid() else 0
                    py = old_crop.y() if old_crop.isValid() else 0
                    # 放置区域裁剪
                    x1 = max(0, px)
                    y1 = max(0, py)
                    x2 = min(full_w, px + w)
                    y2 = min(full_h, py + h)
                    if x2 > x1 and y2 > y1:
                        src_x1 = x1 - px
                        src_y1 = y1 - py
                        full_rgba[y1:y2, x1:x2] = rgba[src_y1:src_y1 + (y2 - y1), src_x1:src_x1 + (x2 - x1)]
                # 合成背景显示
                composed = self.compose_matted(full_rgba)
                pixmap = composed
            else:
                matted = self.matted_cache.get(path)
                if matted is not None:
                    composed = self._composed_pixmap_cache.get(path)
                    if composed is None:
                        composed = self.compose_matted(matted)
                        self._composed_pixmap_cache[path] = composed
                    pixmap = composed
                else:
                    self.image_label.setText("未抠图")
                    self.image_label.resize(self.scroll_area.viewport().size())
                    return

        if pixmap is None or pixmap.isNull():
            return

        if self.scale_factor != 1.0:
            scaled_size = pixmap.size() * self.scale_factor
            pixmap = pixmap.scaled(scaled_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.image_label.setPixmap(pixmap)
        self.image_label.resize(pixmap.size())
        # 如果裁剪覆盖层可见，同步图片区域
        if hasattr(self, 'crop_overlay') and self.crop_overlay.isVisible():
            self._sync_crop_overlay_rect()
        if self.region_overlay.isVisible():
            self._sync_region_overlay_rect()

    def compose_matted(self, rgba):
        if self.bg_mode == "checker":
            return compose_alpha_over_background(rgba, checker=True)
        elif self.bg_mode == "white":
            return compose_alpha_over_background(rgba, bg_color=QColor(255, 255, 255))
        elif self.bg_mode == "black":
            return compose_alpha_over_background(rgba, bg_color=QColor(0, 0, 0))
        else:
            return compose_alpha_over_background(rgba, bg_color=self.custom_bg_color)

    def next_frame(self):
        if not self.frame_list: return
        next_idx = self.current_idx + 1
        if next_idx >= len(self.frame_list):
            next_idx = 0
        self.show_frame(next_idx)

    def prev_frame(self):
        if not self.frame_list: return
        prev_idx = self.current_idx - 1
        if prev_idx < 0:
            prev_idx = len(self.frame_list) - 1
        self.show_frame(prev_idx)

    def toggle_play(self):
        if not self.frame_list: return
        if not self.is_playing:
            self.play()
        else:
            self.pause()

    def play(self):
        interval = int(1000 / self.fps) if self.fps > 0 else 41
        self.timer.start(interval)
        self.is_playing = True
        self.btn_play.setText("⏸")

    def pause(self):
        self.timer.stop()
        self.is_playing = False
        self.btn_play.setText("▶")

    def stop(self):
        self.timer.stop()
        self.is_playing = False
        self.btn_play.setText("▶")
        if self.frame_list:
            self.show_frame(0)


    def enter_region_select_mode(self):
        if self.crop_overlay.isVisible():
            self.crop_overlay.hide()
        self.region_overlay.set_scale_factor(self.scale_factor)
        self.region_overlay.enter_region_mode()
        self._sync_region_overlay_rect()

    def _sync_region_overlay_rect(self):
        pos = self.image_label.mapTo(self.scroll_area.viewport(), QPoint(0, 0))
        image_rect = QRect(pos, self.image_label.size())
        self.region_overlay.setGeometry(self.scroll_area.viewport().rect())
        self.region_overlay.set_image_rect(image_rect)
        self.region_overlay.set_scale_factor(self.scale_factor)  # 关键！必须加上

    def _on_region_selected(self, rect):
        # 先退出添加模式（隐藏 overlay），然后主窗口会重新显示带高亮的 overlay
        self.region_overlay.exit_region_mode()
        if self.mw:
            self.mw.on_region_selected(rect)

    def _on_region_cancelled(self):
        self.region_overlay.exit_region_mode()
        if self.mw:
            self.mw.on_region_cancelled()

    def enter_region_add_mode(self):
        if self.crop_overlay.isVisible():
            self.crop_overlay.hide()
        # 获取主窗口的现有区域矩形列表（用于添加模式下继续显示）
        if self.mw and hasattr(self.mw, 'matting_panel'):
            regions = self.mw.matting_panel.get_regions()
            existing_rects = [r.rect for r in regions]
        else:
            existing_rects = []
        self.region_overlay.set_regions(existing_rects, -1)  # 显示所有现有区域（无高亮）
        self.region_overlay.set_scale_factor(self.scale_factor)
        self.region_overlay.enter_add_mode()
        self._sync_region_overlay_rect()

    def show_region_highlight(self, regions, selected_index):
        if self.crop_overlay.isVisible():
            self.crop_overlay.hide()
        self.region_overlay.set_scale_factor(self.scale_factor)
        self.region_overlay.set_regions(regions, selected_index)
        self.region_overlay.enter_highlight_mode()
        self._sync_region_overlay_rect()

    def hide_region_overlay(self):
        self.region_overlay.exit_region_mode()

    def update_region_overlay_regions(self, regions, selected_idx=-1):
        self.region_overlay.set_regions(regions, selected_idx)
