from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath

class CropOverlay(QWidget):
    cropApplied = Signal(QRect)
    cropCancelled = Signal()
    cropRectChanged = Signal(QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.scale_factor = 1.0

        self._image_rect = QRect()
        self._crop_rect = QRect()
        self._dragging = False
        self._resizing = False
        self._resize_edge = None
        self._drag_start = QPoint()
        self._rect_start = QRect()

        self.crop_mode = False
        self.allow_out_of_bounds = False

    def set_image_rect(self, rect: QRect):
        self._image_rect = rect
        if self._crop_rect.isNull() and self.crop_mode:
            # 注意：此时 _crop_rect 为图像坐标，所以要用原图尺寸
            self._crop_rect = QRect(0, 0, rect.width() / self.scale_factor,
                                    rect.height() / self.scale_factor)
        self.update()

    def set_scale_factor(self, factor):
        self.scale_factor = factor

    def enter_crop_mode(self, rect: QRect = QRect(), allow_out_of_bounds=False):
        """进入裁剪模式，rect 为初始裁剪框（图像坐标）"""
        self.allow_out_of_bounds = allow_out_of_bounds
        self.crop_mode = True
        if rect.isValid():
            self._crop_rect = rect
        elif self._crop_rect.isNull() and self._image_rect.isValid():
            # 默认全图
            self._crop_rect = QRect(0, 0,
                                    self._image_rect.width() / self.scale_factor,
                                    self._image_rect.height() / self.scale_factor)
        self.setCursor(Qt.CrossCursor)
        self.setFocus()
        self.show()
        self.update()

    def exit_crop_mode(self):
        self.crop_mode = False
        self.hide()
        self.setCursor(Qt.ArrowCursor)
        self.update()

    # ---------- 鼠标事件 ----------
    def mousePressEvent(self, event):
        if not self.crop_mode or not self._image_rect.isValid():
            return
        pos = event.pos()
        if self._crop_rect.isValid():
            widget_rect = self._crop_rect_widget()
            edge = self._hit_test(pos, widget_rect)
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._drag_start = pos
                self._rect_start = QRect(self._crop_rect)
                self.setCursor(self._cursor_for_edge(edge))
                return
            if widget_rect.contains(pos):
                self._dragging = True
                self._drag_start = pos
                self._rect_start = QRect(self._crop_rect)
                self.setCursor(Qt.SizeAllCursor)
                return
        # 开始新矩形
        self._dragging = True
        self._resizing = False
        self._drag_start = pos
        self._rect_start = QRect()  # 标记从头开始
        self.setCursor(Qt.CrossCursor)

    def mouseMoveEvent(self, event):
        if not self.crop_mode or not self._image_rect.isValid():
            return
        pos = event.pos()
        if self._dragging and self._rect_start.isValid():
            delta = pos - self._drag_start
            # 将 overlay 坐标的移动量转换为图像坐标的移动量
            dx = delta.x() / self.scale_factor
            dy = delta.y() / self.scale_factor
            new_rect = self._rect_start.translated(int(dx), int(dy))
            self._crop_rect = self._clamp_to_image(new_rect).normalized()
            self.cropRectChanged.emit(self._crop_rect)
            self.update()
            return
        elif self._resizing:
            delta = pos - self._drag_start
            dx = delta.x() / self.scale_factor
            dy = delta.y() / self.scale_factor
            # 将移动量构造成 QPoint，保持与原接口一致
            new_rect = self._resize_rect(self._rect_start, self._resize_edge, QPoint(int(dx), int(dy)))
            self._crop_rect = self._clamp_to_image(new_rect).normalized()
            self.cropRectChanged.emit(self._crop_rect)
            self.update()
            return
        elif self._dragging and not self._rect_start.isValid():
            # 绘制新矩形：坐标已经是 overlay 坐标，需转图像坐标
            end = pos
            img_r = self._image_rect
            # 限制在图片区域内
            x1 = max(img_r.x(), min(self._drag_start.x(), end.x()))
            y1 = max(img_r.y(), min(self._drag_start.y(), end.y()))
            x2 = min(img_r.right(), max(self._drag_start.x(), end.x()))
            y2 = min(img_r.bottom(), max(self._drag_start.y(), end.y()))
            if x2 > x1 and y2 > y1:
                # 转换为图像坐标
                ix1 = int((x1 - img_r.x()) / self.scale_factor)
                iy1 = int((y1 - img_r.y()) / self.scale_factor)
                ix2 = int((x2 - img_r.x()) / self.scale_factor)
                iy2 = int((y2 - img_r.y()) / self.scale_factor)
                self._crop_rect = QRect(ix1, iy1, ix2 - ix1, iy2 - iy1).normalized()
                self.cropRectChanged.emit(self._crop_rect)
                self.update()
            return
        else:
            if self._crop_rect.isValid():
                widget_rect = self._crop_rect_widget()
                edge = self._hit_test(pos, widget_rect)
                if edge:
                    self.setCursor(self._cursor_for_edge(edge))
                elif widget_rect.contains(pos):
                    self.setCursor(Qt.SizeAllCursor)
                else:
                    self.setCursor(Qt.CrossCursor)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._resizing = False
        self._resize_edge = None

    def keyPressEvent(self, event):
        if self.crop_mode:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if self._crop_rect.isValid() and self._crop_rect.width() > 0 and self._crop_rect.height() > 0:
                    self.cropApplied.emit(self._crop_rect)
                else:
                    self.cropCancelled.emit()
                return
            elif event.key() == Qt.Key_Escape:
                self.cropCancelled.emit()
                return
        super().keyPressEvent(event)

    # ---------- 坐标转换 ----------
    def _crop_rect_widget(self):
        img = self._image_rect
        if img.isEmpty():
            return QRect()
        return QRect(
            int(img.x() + self._crop_rect.x() * self.scale_factor),
            int(img.y() + self._crop_rect.y() * self.scale_factor),
            int(self._crop_rect.width() * self.scale_factor),
            int(self._crop_rect.height() * self.scale_factor)
        )

    def _clamp_to_image(self, rect):
        """限制矩形不超出原图范围（图像坐标）"""
        if not self.allow_out_of_bounds:
            # 保持原有边界限制逻辑
            r = QRect(rect)
            img_w = self._image_rect.width() / self.scale_factor
            img_h = self._image_rect.height() / self.scale_factor
            if r.left() < 0: r.setLeft(0)
            if r.top() < 0: r.setTop(0)
            if r.right() > img_w: r.setRight(int(img_w))
            if r.bottom() > img_h: r.setBottom(int(img_h))
            if r.width() < 10: r.setWidth(10)
            if r.height() < 10: r.setHeight(10)
            return r
        else:
            # 仅限制最小尺寸，不限制位置
            r = QRect(rect)
            if r.width() < 10: r.setWidth(10)
            if r.height() < 10: r.setHeight(10)
            return r

    def _hit_test(self, pos, widget_rect):
        margin = 8
        corners = {
            'topleft': widget_rect.topLeft(),
            'topright': widget_rect.topRight(),
            'bottomleft': widget_rect.bottomLeft(),
            'bottomright': widget_rect.bottomRight()
        }
        for name, pt in corners.items():
            if (pos - pt).manhattanLength() < margin:
                return name
        inner_rect = widget_rect.adjusted(margin, margin, -margin, -margin)
        if widget_rect.contains(pos) and not inner_rect.contains(pos):
            if pos.x() < inner_rect.left(): return 'left'
            if pos.x() > inner_rect.right(): return 'right'
            if pos.y() < inner_rect.top(): return 'top'
            if pos.y() > inner_rect.bottom(): return 'bottom'
        return None

    def _cursor_for_edge(self, edge):
        cursors = {
            'left': Qt.SizeHorCursor, 'right': Qt.SizeHorCursor,
            'top': Qt.SizeVerCursor, 'bottom': Qt.SizeVerCursor,
            'topleft': Qt.SizeFDiagCursor, 'bottomright': Qt.SizeFDiagCursor,
            'topright': Qt.SizeBDiagCursor, 'bottomleft': Qt.SizeBDiagCursor,
        }
        return cursors.get(edge, Qt.CrossCursor)

    def _resize_rect(self, start_rect, edge, delta):
        r = QRect(start_rect)
        dx = delta.x()
        dy = delta.y()
        if 'left' in edge: r.setLeft(r.left() + dx)
        if 'right' in edge: r.setRight(r.right() + dx)
        if 'top' in edge: r.setTop(r.top() + dy)
        if 'bottom' in edge: r.setBottom(r.bottom() + dy)
        return r

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        if not self.crop_mode or not self._crop_rect.isValid() or not self._image_rect.isValid():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        widget_rect = self._crop_rect_widget()

        # 半透明遮罩
        overlay_color = QColor(0, 0, 0, 160)
        full_path = QPainterPath()
        full_path.addRect(self.rect())
        crop_path = QPainterPath()
        crop_path.addRect(widget_rect)
        full_path = full_path.subtracted(crop_path)
        painter.fillPath(full_path, overlay_color)

        # 白色虚线框
        pen = QPen(QColor(255, 255, 255), 2, Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(widget_rect)

        # 四角手柄
        painter.setBrush(Qt.white)
        painter.setPen(Qt.NoPen)
        handle_size = 4
        for pt in [widget_rect.topLeft(), widget_rect.topRight(),
                   widget_rect.bottomLeft(), widget_rect.bottomRight()]:
            painter.drawRect(pt.x() - handle_size, pt.y() - handle_size,
                             handle_size * 2, handle_size * 2)
        painter.end()