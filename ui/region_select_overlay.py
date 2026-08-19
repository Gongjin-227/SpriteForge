from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPainter, QPen, QColor

class RegionSelectOverlay(QWidget):
    regionSelected = Signal(QRect)
    regionCancelled = Signal()
    regionClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.scale_factor = 1.0
        self._image_rect = QRect()
        self._region_rect = QRect()
        self._dragging = False
        self._drag_start = QPoint()
        self._active = False
        self.regions = []
        self.selected_index = -1
        self._interactive = True

        # 新增状态
        self._moving = False
        self._resizing = False
        self._resize_edge = None
        self._rect_start = QRect()

    def set_image_rect(self, rect):
        self._image_rect = rect
        self.update()

    def set_scale_factor(self, factor):
        self.scale_factor = factor

    def set_regions(self, regions, selected_index=-1):
        self.regions = regions
        self.selected_index = selected_index
        self.update()

    def enter_add_mode(self):
        self._interactive = True
        self._region_rect = QRect()
        self._active = True
        self.setCursor(Qt.CrossCursor)
        self.show()
        self.setFocus()
        self.update()

    def enter_highlight_mode(self):
        self._interactive = False
        self._active = True
        self.setCursor(Qt.ArrowCursor)  # 关键：高亮模式光标必须为箭头
        self.show()
        self.setFocus()
        self.update()

    def exit_region_mode(self):
        self._active = False
        self._interactive = False  # 添加这行
        self.hide()
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def enter_region_mode(self):
        self.enter_add_mode()

    # ---------- 鼠标事件 ----------
    def mousePressEvent(self, event):
        if not self._active or not self._image_rect.isValid():
            return
        pos = event.pos()

        if not self._interactive:
            # 高亮模式：点击已有区域发出信号
            for i, rect in enumerate(self.regions):
                widget_rect = self._to_widget_rect(rect)
                if widget_rect.contains(pos):
                    self.regionClicked.emit(i)
                    return
            return

        # 添加模式
        # 如果已有矩形且点击在矩形内部/边缘，进入移动/拉伸
        if self._region_rect.isValid():
            widget_rect = self._to_widget_rect(self._region_rect)
            edge = self._hit_test(pos, widget_rect)
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._drag_start = pos
                self._rect_start = QRect(self._region_rect)
                self.setCursor(self._cursor_for_edge(edge))
                return
            if widget_rect.contains(pos):
                self._moving = True
                self._drag_start = pos
                self._rect_start = QRect(self._region_rect)
                self.setCursor(Qt.SizeAllCursor)
                return

        # 否则开始绘制新矩形
        if self._image_rect.contains(pos):
            self._dragging = True
            self._drag_start = pos
            self._region_rect = QRect()
            self.setCursor(Qt.CrossCursor)
            self.update()

    def mouseMoveEvent(self, event):
        if not self._active:
            return
        if not self._interactive:
            # 高亮模式：不改变光标
            return
        pos = event.pos()
        if not (self._dragging or self._moving or self._resizing):
            # 仅更新光标
            if self._region_rect.isValid():
                widget_rect = self._to_widget_rect(self._region_rect)
                edge = self._hit_test(pos, widget_rect)
                if edge:
                    self.setCursor(self._cursor_for_edge(edge))
                elif widget_rect.contains(pos):
                    self.setCursor(Qt.SizeAllCursor)
                else:
                    self.setCursor(Qt.CrossCursor)
            else:
                self.setCursor(Qt.CrossCursor)
            return
        img = self._image_rect

        # 绘制新矩形
        if self._dragging:
            x1 = max(img.x(), min(self._drag_start.x(), pos.x()))
            y1 = max(img.y(), min(self._drag_start.y(), pos.y()))
            x2 = min(img.right(), max(self._drag_start.x(), pos.x()))
            y2 = min(img.bottom(), max(self._drag_start.y(), pos.y()))
            if x2 > x1 and y2 > y1:
                ix1 = int((x1 - img.x()) / self.scale_factor)
                iy1 = int((y1 - img.y()) / self.scale_factor)
                ix2 = int((x2 - img.x()) / self.scale_factor)
                iy2 = int((y2 - img.y()) / self.scale_factor)
                self._region_rect = QRect(ix1, iy1, ix2 - ix1, iy2 - iy1).normalized()
                self.update()
            return

        # 移动矩形
        if self._moving:
            delta = pos - self._drag_start
            dx = int(delta.x() / self.scale_factor)
            dy = int(delta.y() / self.scale_factor)
            new_rect = self._rect_start.translated(dx, dy)
            # 限制在图像内
            new_rect = self._clamp_to_image(new_rect)
            self._region_rect = new_rect
            self.update()
            return

        # 拉伸矩形
        if self._resizing:
            delta = pos - self._drag_start
            dx = int(delta.x() / self.scale_factor)
            dy = int(delta.y() / self.scale_factor)
            new_rect = self._resize_rect(self._rect_start, self._resize_edge, dx, dy)
            new_rect = self._clamp_to_image(new_rect)
            self._region_rect = new_rect
            self.update()
            return

    def mouseReleaseEvent(self, event):
        if not self._interactive:
            return
        self._dragging = False
        self._moving = False
        self._resizing = False
        self._resize_edge = None
        self.setCursor(Qt.CrossCursor)
        self.update()

    def keyPressEvent(self, event):
        if not self._active:
            return

        if event.key() == Qt.Key_Escape:
            # 只有在添加模式且存在正在绘制的矩形时才取消绘制
            if self._interactive and (self._dragging or self._region_rect.isValid()):
                self.regionCancelled.emit()
            # 高亮模式或没有绘制矩形时，ESC 什么都不做
            return

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._interactive and self._region_rect.isValid() and self._region_rect.width() > 0 and self._region_rect.height() > 0:
                self.regionSelected.emit(self._region_rect)
            # 非添加模式或矩形无效时，回车无效果
            return

        super().keyPressEvent(event)

    # ---------- 辅助方法 ----------
    def _to_widget_rect(self, rect):
        return QRect(
            int(self._image_rect.x() + rect.x() * self.scale_factor),
            int(self._image_rect.y() + rect.y() * self.scale_factor),
            int(rect.width() * self.scale_factor),
            int(rect.height() * self.scale_factor)
        )

    def _clamp_to_image(self, rect):
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

    def _resize_rect(self, start_rect, edge, dx, dy):
        r = QRect(start_rect)
        if 'left' in edge: r.setLeft(r.left() + dx)
        if 'right' in edge: r.setRight(r.right() + dx)
        if 'top' in edge: r.setTop(r.top() + dy)
        if 'bottom' in edge: r.setBottom(r.bottom() + dy)
        return r

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        if not self._active or not self._image_rect.isValid():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 绘制已有区域
        for i, rect in enumerate(self.regions):
            widget_rect = self._to_widget_rect(rect)
            if i == self.selected_index:
                pen = QPen(QColor(0, 120, 255), 2, Qt.SolidLine)
            else:
                pen = QPen(QColor(255, 255, 255), 1, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(widget_rect)

        # 绘制当前正在编辑的矩形（如果存在）
        if self._interactive and self._region_rect.isValid():
            widget_rect = self._to_widget_rect(self._region_rect)
            pen = QPen(QColor(255, 255, 255), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(widget_rect)

        painter.end()