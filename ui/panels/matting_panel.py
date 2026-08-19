from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSlider, QCheckBox, QComboBox, QStackedWidget, QWidget, QColorDialog,
    QListWidget, QListWidgetItem, QAbstractItemView,QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from core.matting import ChromaKeyMethod, LumaKeyMethod, RMBGMethod, BiRefNetMethod
from core.models import CleanupRegion

class MattingPanel(QGroupBox):
    preview_requested = Signal()
    batch_requested = Signal()
    region_select_requested = Signal()
    region_add_requested = Signal()
    global_region_color_requested = Signal()
    corridorkey_toggled = Signal(bool)
    regions_changed = Signal()  # 区域数据变化（增删改）

    def __init__(self, parent=None):
        super().__init__("🎨 抠图设置", parent)
        self.chroma_color = QColor("#7acf73")
        self._rmbg_residual_color = QColor("#7acf73")
        self._default_global_region_color = "#7acf71"
        self._setup_ui()
        self._connect_signals()
        self.regions = []  # 存储 CleanupRegion 对象
        self.selected_region_idx = -1  # 当前选中索引
        self.default_region_color = "#7acf71"
        self._region_counter = 0  # 用于生成唯一区域名称


    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ---- 模式选择 ----
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("模式:"))
        self.matting_mode_combo = QComboBox()
        self.matting_mode_combo.addItems([
            "快速：色度抠图",
            "快速：亮度抠图",
            "标准：RMBG-2",
            "精细：BiRefNet",
        ])
        mode_layout.addWidget(self.matting_mode_combo)
        layout.addLayout(mode_layout)

        self.matting_params_stack = QStackedWidget()
        self.matting_params_stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.matting_params_stack.setMinimumHeight(0)

        # 色度抠图参数
        chroma_widget = QWidget()
        chroma_layout = QHBoxLayout(chroma_widget)
        chroma_layout.addWidget(QLabel("颜色:"))
        self.chroma_color_btn = QPushButton()
        self.chroma_color_btn.setFixedSize(30, 30)
        self.chroma_color_btn.setStyleSheet("background-color:#7acf73;")
        chroma_layout.addWidget(self.chroma_color_btn)
        chroma_layout.addWidget(QLabel("容差:"))
        self.chroma_tol_slider = QSlider(Qt.Horizontal)
        self.chroma_tol_slider.setRange(0, 100)
        self.chroma_tol_slider.setValue(60)
        self.chroma_tol_label = QLabel("60")
        self.chroma_tol_slider.valueChanged.connect(
            lambda v: self.chroma_tol_label.setText(str(v))
        )
        chroma_layout.addWidget(self.chroma_tol_slider)
        chroma_layout.addWidget(self.chroma_tol_label)
        self.matting_params_stack.addWidget(chroma_widget)

        # 亮度抠图参数
        luma_widget = QWidget()
        luma_layout = QHBoxLayout(luma_widget)
        luma_layout.addWidget(QLabel("阈值:"))
        self.luma_thresh_slider = QSlider(Qt.Horizontal)
        self.luma_thresh_slider.setRange(0, 255)
        self.luma_thresh_slider.setValue(128)
        self.luma_thresh_label = QLabel("128")
        self.luma_thresh_slider.valueChanged.connect(
            lambda v: self.luma_thresh_label.setText(str(v))
        )
        luma_layout.addWidget(self.luma_thresh_slider)
        luma_layout.addWidget(self.luma_thresh_label)
        self.luma_invert_cb = QCheckBox("反转")
        luma_layout.addWidget(self.luma_invert_cb)
        self.matting_params_stack.addWidget(luma_widget)

        # RMBG-2 参数页
        rmbg_widget = QWidget()
        rmbg_layout = QVBoxLayout(rmbg_widget)
        rmbg_layout.setContentsMargins(0, 0, 0, 0)
        rmbg_layout.setSpacing(0)
        rmbg_widget.setFixedHeight(0)  # 强制高度为 0
        self.matting_params_stack.addWidget(rmbg_widget)

        # BiRefNet 参数页（暂无参数，保持高度 0 避免空白）
        birefnet_plus = QWidget()
        birefnet_layout = QVBoxLayout(birefnet_plus)
        birefnet_layout.setContentsMargins(0, 0, 0, 0)
        birefnet_layout.setSpacing(0)
        birefnet_plus.setFixedHeight(0)
        self.matting_params_stack.addWidget(birefnet_plus)

        layout.addWidget(self.matting_params_stack)

        common_options_layout = QHBoxLayout()
        self.enable_region_cleanup_cb = QCheckBox("区域清理")
        self.enable_region_cleanup_cb.setChecked(False)
        self.enable_corridorkey_cb = QCheckBox("线条增强")
        self.enable_corridorkey_cb.setChecked(False)

        # 残边处理：勾选启用 + 下拉选择方式
        self.enable_residual_cb = QCheckBox("")
        self.enable_residual_cb.setChecked(False)
        self.residual_mode_combo = QComboBox()
        self.residual_mode_combo.addItems([
            "绿色/背景残边转黑",
            "绿色/背景残边去饱和",
            "半透明像素转黑",
            "半透明像素转不透明",
        ])
        self.residual_mode_combo.setCurrentIndex(0)
        # 未启用时下拉框禁用
        self.residual_mode_combo.setEnabled(False)
        self.enable_residual_cb.toggled.connect(self.residual_mode_combo.setEnabled)

        common_options_layout.addWidget(self.enable_region_cleanup_cb)
        common_options_layout.addWidget(self.enable_corridorkey_cb)
        common_options_layout.addWidget(self.enable_residual_cb)
        common_options_layout.addWidget(self.residual_mode_combo)
        common_options_layout.addStretch()
        layout.addLayout(common_options_layout)

        region_btn_layout = QHBoxLayout()
        self.btn_add_region = QPushButton("添加区域")
        self.btn_add_region.clicked.connect(self.region_add_requested)
        region_btn_layout.addWidget(self.btn_add_region)

        self.chk_show_regions = QCheckBox("显示区域")
        self.chk_show_regions.setChecked(True)
        region_btn_layout.addWidget(self.chk_show_regions)

        label_global_color = QLabel("统一颜色")
        region_btn_layout.addWidget(label_global_color)

        self.btn_global_region_color = QPushButton()
        self.btn_global_region_color.setFixedSize(30, 30)
        self.btn_global_region_color.setStyleSheet(f"background-color:{self._default_global_region_color};")
        region_btn_layout.addWidget(self.btn_global_region_color)
        layout.addLayout(region_btn_layout)


        self.region_list = QListWidget()
        self.region_list.setMinimumHeight(50)
        self.region_list.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.region_list)

        # 输出选项
        self.transparent_png_cb = QCheckBox("输出透明 PNG")
        self.transparent_png_cb.setChecked(True)
        layout.addWidget(self.transparent_png_cb)

        self.export_mask_cb = QCheckBox("同时导出遮罩")
        layout.addWidget(self.export_mask_cb)

        # 操作按钮
        self.btn_preview_matte = QPushButton("👁 预览抠图(当前帧)")
        layout.addWidget(self.btn_preview_matte)

        self.btn_batch_matte = QPushButton("🎯 批量抠图 (工作区帧)")
        layout.addWidget(self.btn_batch_matte)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #1976D2; font-style: italic;")
        layout.addWidget(self.status_label)

        self._update_region_list_height()
        if self.matting_params_stack.currentWidget():
            self.matting_params_stack.setFixedHeight(self.matting_params_stack.currentWidget().sizeHint().height())

    def is_residual_enabled(self):
        return self.enable_residual_cb.isChecked()

    def get_residual_mode(self):
        """返回当前选择的残边处理方式字符串"""
        index = self.residual_mode_combo.currentIndex()
        modes = [
            "green_to_black",
            "green_desaturate",
            "semitransparent_to_black",
            "semitransparent_to_opaque",
        ]
        return modes[index] if 0 <= index < len(modes) else "green_to_black"

    def get_regions(self):
        return self.regions



    def set_regions(self, regions):
        self.regions = list(regions)
        self.selected_region_idx = -1
        self.refresh_region_list()
        self.regions_changed.emit()

    def clear_regions(self):
        self.regions.clear()
        self.selected_region_idx = -1
        self.refresh_region_list()
        self.regions_changed.emit()
        self.status_label.setText("")

    def add_region(self, rect, color_hex=None, tolerance=30):
        if color_hex is None:
            color_hex = self.default_region_color
        self._region_counter += 1
        region = CleanupRegion(
            name=f"区域{self._region_counter}",
            rect=rect,
            color_hex=color_hex,
            tolerance=tolerance
        )
        self.regions.append(region)
        self.selected_region_idx = len(self.regions) - 1
        self.refresh_region_list()
        self.regions_changed.emit()
        return region

    def delete_region(self, idx):
        if 0 <= idx < len(self.regions):
            removed_region = self.regions[idx]
            del self.regions[idx]
            if self.selected_region_idx == idx:
                self.selected_region_idx = -1
            elif self.selected_region_idx > idx:
                self.selected_region_idx -= 1
            self.refresh_region_list()
            self.regions_changed.emit()

            # 使用实际区域名称显示提示
            if self.regions:
                self.status_label.setText(f"已删除区域：{removed_region.name}")
            else:
                self.status_label.setText("")

    def update_region_color(self, idx, color_hex):
        if 0 <= idx < len(self.regions):
            self.regions[idx].color_hex = color_hex
            self.refresh_region_list()
            self.regions_changed.emit()

    def update_region_tolerance(self, idx, value):
        if 0 <= idx < len(self.regions):
            self.regions[idx].tolerance = value

    def set_default_region_color(self, color_hex):
        self.default_region_color = color_hex
        # 如果用户选择统一颜色，则更新所有区域
        for region in self.regions:
            region.color_hex = color_hex
        self.refresh_region_list()
        self.btn_global_region_color.setStyleSheet(f"background-color:{color_hex};")
        self.regions_changed.emit()

    def is_corridorkey_enabled(self):
        return self.enable_corridorkey_cb.isChecked()

    def refresh_region_list(self):
        self.region_list.clear()
        for i, region in enumerate(self.regions):
            self.add_region_item(region, i)
        if 0 <= self.selected_region_idx < self.region_list.count():
            item = self.region_list.item(self.selected_region_idx)
            self.region_list.setCurrentItem(item)
            item.setSelected(True)
        self._update_region_list_height()

    def _connect_signals(self):
        self.matting_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.btn_preview_matte.clicked.connect(self.preview_requested)
        self.btn_batch_matte.clicked.connect(self.batch_requested)
        self.btn_add_region.clicked.connect(self.region_add_requested)
        self.chroma_color_btn.clicked.connect(self._pick_color)  # 注意这里
        self.region_list.itemClicked.connect(self._on_region_item_clicked)
        self.btn_global_region_color.clicked.connect(self.global_region_color_requested.emit)
        self.enable_corridorkey_cb.toggled.connect(self.corridorkey_toggled)

    def _on_region_item_clicked(self, item):
        idx = item.data(Qt.UserRole)
        if 0 <= idx < len(self.regions):
            if self.selected_region_idx == idx:
                self.selected_region_idx = -1
            else:
                self.selected_region_idx = idx
            self.refresh_region_list()
            self.regions_changed.emit()

    def _on_mode_changed(self, idx):
        self.matting_params_stack.setCurrentIndex(idx)
        # 根据当前页动态设置高度
        current_widget = self.matting_params_stack.currentWidget()
        if current_widget:
            self.matting_params_stack.setFixedHeight(current_widget.sizeHint().height())

    def _pick_color(self):
        dlg = QColorDialog(self.window())
        dlg.setWindowTitle("选择色度键颜色")
        dlg.setCurrentColor(self.chroma_color)

        # 定位到屏幕右侧（保留你已设置的弹出位置）
        screen = self.window().screen().availableGeometry()
        dlg.move(screen.right() - 560, screen.top() + 150)

        if dlg.exec() == QColorDialog.Accepted:
            self.chroma_color = dlg.currentColor()
            self.chroma_color_btn.setStyleSheet(f"background-color:{self.chroma_color.name()};")

    def add_region_item(self, region, index):
        widget = QWidget()
        h_layout = QHBoxLayout(widget)
        h_layout.setContentsMargins(4, 2, 4, 2)
        h_layout.setSpacing(4)

        name_label = QLabel(region.name)
        name_label.setMinimumWidth(40)
        color_btn = QPushButton()
        color_btn.setFixedSize(24, 24)
        color_btn.setStyleSheet(f"background-color:{region.color_hex};")
        color_btn.clicked.connect(lambda checked, idx=index: self._on_region_color_clicked(idx))

        tol_slider = QSlider(Qt.Horizontal)
        tol_slider.setRange(0, 100)
        tol_slider.setValue(region.tolerance)
        tol_slider.setMinimumWidth(60)

        tol_label = QLabel(str(region.tolerance))
        tol_label.setFixedWidth(30)
        tol_slider.valueChanged.connect(lambda value, idx=index: self._on_region_tolerance_changed(idx, value))

        delete_btn = QPushButton("✖")
        delete_btn.setFixedSize(24, 24)
        delete_btn.clicked.connect(lambda checked, idx=index: self.delete_region(idx))

        # 固定名称宽度，消除多余空隙
        name_label.setFixedWidth(30)  # 可根据实际调整
        h_layout.addWidget(name_label, 0)
        h_layout.addWidget(color_btn, 0)
        h_layout.addWidget(tol_slider, 1)  # 滑动条拉伸占满中间空间
        h_layout.addWidget(tol_label, 0)
        h_layout.addWidget(delete_btn, 0)

        item = QListWidgetItem()
        item.setData(Qt.UserRole, index)
        self.region_list.addItem(item)
        self.region_list.setItemWidget(item, widget)
        item.setSizeHint(widget.sizeHint())
        self._update_region_list_height()

    def _update_region_list_height(self):
        item_count = self.region_list.count()
        item_height = 50  # 每个区域项大约高度，根据实际调整
        visible_count = min(item_count, 3)  # 最多显示3个
        self.region_list.setFixedHeight(visible_count * item_height + 2)  # 加边框

    def _on_region_color_clicked(self, idx):
        dlg = QColorDialog(self.window())
        dlg.setWindowTitle(f"选择区域 {idx + 1} 清理颜色")
        dlg.setCurrentColor(QColor(self.regions[idx].color_hex))

        # 设置对话框位置（与色度颜色对话框保持一致）
        screen = self.window().screen().availableGeometry()
        dlg.move(screen.right() - 560, screen.top() + 150)

        if dlg.exec() == QColorDialog.Accepted:
            self.update_region_color(idx, dlg.currentColor().name())

    def _on_region_tolerance_changed(self, idx, value):
        if 0 <= idx < len(self.regions):
            self.regions[idx].tolerance = value