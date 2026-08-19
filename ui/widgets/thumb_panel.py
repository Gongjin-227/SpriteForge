# ui/widgets/thumb_panel.py

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QAbstractItemView, QStyledItemDelegate, QStyle
)
from PySide6.QtCore import Qt, QSize, Signal, QRect
from PySide6.QtGui import QPixmap, QColor, QIcon


class ThumbDelegate(QStyledItemDelegate):
    """自定义缩略图绘制：右上角标记 + 选中外边框"""

    def __init__(self, thumb_panel, parent=None):
        super().__init__(parent)
        self.tp = thumb_panel  # 保存 ThumbPanel 引用，方便获取数据

    def sizeHint(self, option, index):
        icon_size = self.tp.thumb_grid.iconSize()
        return QSize(icon_size.width() + 16, icon_size.height() + 19)

    def paint(self, painter, option, index):
        frame_idx = index.data(Qt.UserRole)
        icon = index.data(Qt.DecorationRole)
        text = index.data(Qt.DisplayRole)

        item = self.tp.thumb_grid.itemFromIndex(index)
        is_selected = (frame_idx is not None) and (frame_idx in self.tp.selected_indices)

        order_mode = self.tp.order_mode
        click_order = self.tp.click_order

        rect = option.rect
        painter.save()

        # 1. 背景
        if is_selected:
            border_color = QColor("#1976D2")
            fill_color = QColor("#E3F2FD")
        else:
            border_color = QColor("#c0c8d0")
            fill_color = QColor("#ffffff")

        painter.setBrush(fill_color)
        pen = painter.pen()
        pen.setColor(border_color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRect(rect.adjusted(1, 1, -1, -1))

        # 2. 缩略图
        icon_size = self.tp.thumb_grid.iconSize()
        if icon is not None and not icon.isNull():
            pixmap = icon.pixmap(icon_size)
        else:
            pixmap = QPixmap(icon_size)
            pixmap.fill(Qt.gray)

        icon_x = rect.left() + (rect.width() - pixmap.width()) // 2
        icon_y = rect.top() + 4
        icon_rect = QRect(icon_x, icon_y, pixmap.width(), pixmap.height())
        painter.drawPixmap(icon_rect.topLeft(), pixmap)

        # 3. 文本（帧编号）
        painter.setPen(QColor("#2c3e50"))
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        text_rect = QRect(rect.left(), icon_rect.bottom() + 2, rect.width(), rect.bottom() - icon_rect.bottom() - 2)
        painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, text)

        # 4. 右上角标记
        mark_size = 16
        mark_rect = QRect(icon_rect.right() - mark_size + 2, icon_rect.top() + 2, mark_size, mark_size)

        if order_mode == "number":
            painter.setPen(QColor("#1976D2"))
            painter.setBrush(QColor("#ffffff"))
            painter.drawRect(mark_rect)
            if is_selected:
                painter.setPen(QColor("#1976D2"))
                font = painter.font()
                font.setPointSize(10)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(mark_rect, Qt.AlignCenter, "✔")
        else:  # 点击顺序模式
            if is_selected and frame_idx is not None:
                try:
                    order_num = click_order.index(frame_idx) + 1
                except ValueError:
                    order_num = -1
                painter.setPen(QColor("#1976D2"))
                painter.setBrush(QColor("#ffffff"))
                painter.drawRect(mark_rect)
                font = painter.font()
                font.setPointSize(8)
                painter.setFont(font)
                painter.drawText(mark_rect, Qt.AlignCenter, str(order_num))

        painter.restore()


class ThumbPanel(QWidget):
    """缩略图网格面板，管理帧选择与播放顺序"""
    selection_changed = Signal()   # 选择发生变化时发出，主窗口可据此更新预览
    thumb_clicked_with_index = Signal(int)  # 点击缩略图时发出帧在总列表中的索引

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_indices = set()   # 当前选中的帧索引（在全部帧中的索引）
        self.click_order = []           # 记录加入工作区的顺序
        self.order_mode = "number"      # "number" 或 "click"
        self.frame_paths = []           # 全部帧路径（外部设置）

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.thumb_grid = QListWidget()
        self.thumb_grid.setFlow(QListWidget.LeftToRight)
        self.thumb_grid.setViewMode(QListWidget.IconMode)
        self.thumb_grid.setIconSize(QSize(120, 80))
        self.thumb_grid.setResizeMode(QListWidget.Adjust)
        self.thumb_grid.setSelectionMode(QAbstractItemView.NoSelection)  # 禁用原生选择
        self.thumb_grid.setWrapping(True)
        self.thumb_grid.setItemDelegate(ThumbDelegate(self))

        self.thumb_grid.itemPressed.connect(self._on_thumb_clicked)

        layout.addWidget(self.thumb_grid)

    # ---------- 外部调用接口 ----------
    def set_frame_paths(self, frame_paths: list):
        """设置全部帧路径列表，并清空选择状态"""
        self.frame_paths = frame_paths
        # 清空旧的选择，避免索引越界
        self.selected_indices.clear()
        self.click_order.clear()
        self.populate_thumbnails()  # 内部会触发 _update_view，此时选择为空，不会报错

    def get_workarea_indices(self):
        """返回工作区索引列表（按 order_mode 排序）"""
        if self.order_mode == "click":
            indices = [i for i in self.click_order if i in self.selected_indices and i < len(self.frame_paths)]
        else:
            indices = [i for i in sorted(self.selected_indices) if i < len(self.frame_paths)]
        return indices

    def get_workarea_paths(self):
        """返回工作区帧的完整路径列表"""
        return [self.frame_paths[i] for i in self.get_workarea_indices()]

    def set_all_selected(self):
        """全选"""
        self.selected_indices = set(range(len(self.frame_paths)))
        self.click_order = list(range(len(self.frame_paths)))
        self._update_view()

    def clear_selection(self):
        """清除选择"""
        self.selected_indices.clear()
        self.click_order.clear()
        self._update_view()

    def invert_selection(self):
        """反选"""
        new_selected = set(i for i in range(len(self.frame_paths)) if i not in self.selected_indices)
        self.selected_indices = new_selected
        # 反选后重置 click_order 为编号顺序
        self.click_order = sorted(new_selected)
        self._update_view()

    def toggle_order_mode(self):
        """切换播放顺序模式"""
        if self.order_mode == "number":
            self.order_mode = "click"
        else:
            self.order_mode = "number"
        self._update_view()

    def select_range(self, start_idx, end_idx):
        """根据起始、结束索引选择帧（闭区间）"""
        self.selected_indices.clear()
        self.click_order.clear()
        for i in range(start_idx, end_idx + 1):
            if 0 <= i < len(self.frame_paths):
                self.selected_indices.add(i)
                self.click_order.append(i)
        self._update_view()

    def jump_to_index(self, target_idx):
        """根据全局索引尝试在工作区中找到对应位置，发出信号让预览跳转"""
        # 这里仅提供一个接口，实际跳转逻辑由主窗口的预览处理
        pass  # 保留，可通过自定义信号传递 target_idx

    # ---------- 内部方法 ----------
    def populate_thumbnails(self):
        self.thumb_grid.clear()
        icon_size = self.thumb_grid.iconSize()
        for i, path in enumerate(self.frame_paths):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            else:
                pixmap = QPixmap(icon_size)
                pixmap.fill(Qt.gray)
            item = QListWidgetItem(QIcon(pixmap), f"{i + 1}")
            item.setData(Qt.UserRole, i)
            self.thumb_grid.addItem(item)
        self._update_view()

    def _on_thumb_clicked(self, item):
        idx = item.data(Qt.UserRole)
        if idx in self.selected_indices:
            self.selected_indices.remove(idx)
            if idx in self.click_order:
                self.click_order.remove(idx)
        else:
            self.selected_indices.add(idx)
            if idx not in self.click_order:
                self.click_order.append(idx)

        self.thumb_grid.viewport().update()
        self.selection_changed.emit()
        self.thumb_clicked_with_index.emit(idx)

    def _update_view(self):
        """强制重绘缩略图并发出选择改变信号"""
        self.thumb_grid.viewport().update()
        self.selection_changed.emit()