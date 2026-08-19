# ui/panels/frame_control_panel.py
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QSpinBox, QDoubleSpinBox
)
from PySide6.QtCore import Qt, Signal


class FrameControlPanel(QGroupBox):
    """帧控制与选择面板，管理范围滑块、全选/反选、顺序切换等"""

    # 主窗口需要处理的信号
    step_changed = Signal(int)  # 抽帧步长变化
    playback_fps_changed = Signal(float)  # 播放帧率变化

    def __init__(self, thumb_panel, parent=None):
        super().__init__("🎯 帧控制与选择", parent)
        self.thumb_panel = thumb_panel
        self.frame_count = 0
        self._playback_fps = 24.0

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ---------- 第1行：抽帧步长 + 播放帧率 ----------
        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("抽帧步长:"))
        self.step_spin = QSpinBox()
        self.step_spin.setRange(1, 100)
        self.step_spin.setValue(1)
        self.step_spin.setFixedWidth(60)
        step_layout.addWidget(self.step_spin)
        step_layout.addSpacing(10)

        step_layout.addWidget(QLabel("播放帧率:"))
        self.playback_fps_spin = QDoubleSpinBox()
        self.playback_fps_spin.setRange(1.0, 120.0)
        self.playback_fps_spin.setValue(24.0)
        self.playback_fps_spin.setDecimals(1)
        self.playback_fps_spin.setSuffix(" fps")
        self.playback_fps_spin.setFixedWidth(80)
        step_layout.addWidget(self.playback_fps_spin)
        step_layout.addStretch()
        layout.addLayout(step_layout)

        # ---------- 第2行：当前帧 + 总时长 ----------
        info_layout = QHBoxLayout()
        self.info_label = QLabel("当前帧: - / -")
        info_layout.addWidget(self.info_label)
        info_layout.addSpacing(10)
        self.duration_label = QLabel("总时长: 0:00.000")
        info_layout.addWidget(self.duration_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)

        # ---------- 第3行：起始帧 ----------
        start_layout = QHBoxLayout()
        start_layout.addWidget(QLabel("起始帧:"))
        self.start_slider = QSlider(Qt.Horizontal)
        self.start_slider.setRange(1, 1)
        self.start_slider.setValue(1)
        start_layout.addWidget(self.start_slider)
        self.range_start = QSpinBox()
        self.range_start.setRange(1, 1)
        self.range_start.setValue(1)
        self.range_start.setFixedWidth(70)
        start_layout.addWidget(self.range_start)
        layout.addLayout(start_layout)

        # ---------- 第4行：结束帧 ----------
        end_layout = QHBoxLayout()
        end_layout.addWidget(QLabel("结束帧:"))
        self.end_slider = QSlider(Qt.Horizontal)
        self.end_slider.setRange(1, 1)
        self.end_slider.setValue(1)
        end_layout.addWidget(self.end_slider)
        self.range_end = QSpinBox()
        self.range_end.setRange(1, 1)
        self.range_end.setValue(1)
        self.range_end.setFixedWidth(70)
        end_layout.addWidget(self.range_end)
        layout.addLayout(end_layout)

        # ---------- 第5行：全选、清除、反选 ----------
        row_btns = QHBoxLayout()
        self.btn_all = QPushButton("全选")
        self.btn_none = QPushButton("清除")
        self.btn_invert = QPushButton("反选")
        row_btns.addWidget(self.btn_all)
        row_btns.addWidget(self.btn_none)
        row_btns.addWidget(self.btn_invert)
        layout.addLayout(row_btns)

        # ---------- 第6行：顺序切换 ----------
        self.btn_order = QPushButton("🔢 编号顺序 (当前)")
        layout.addWidget(self.btn_order)

    def _connect_signals(self):
        # 步长与播放帧率变化 -> 发射信号给主窗口
        self.step_spin.valueChanged.connect(
            lambda v: self.step_changed.emit(v)
        )
        self.playback_fps_spin.valueChanged.connect(
            lambda v: self.playback_fps_changed.emit(v)
        )

        # 全选/清除/反选 -> 直接操作 thumb_panel（thumb_panel 会自己触发 selection_changed）
        self.btn_all.clicked.connect(self.thumb_panel.set_all_selected)
        self.btn_none.clicked.connect(self.thumb_panel.clear_selection)
        self.btn_invert.clicked.connect(self.thumb_panel.invert_selection)

        # 顺序切换 -> 直接操作 thumb_panel 并更新按钮文字
        self.btn_order.clicked.connect(self._toggle_order_mode)

        # 滑块联动
        self.start_slider.valueChanged.connect(self._on_start_slider_changed)
        self.end_slider.valueChanged.connect(self._on_end_slider_changed)
        self.range_start.valueChanged.connect(self._on_start_spin_changed)
        self.range_end.valueChanged.connect(self._on_end_spin_changed)

    # ---------- 外部接口 ----------
    def set_frame_count(self, count):
        """设置总帧数，更新滑块和数值框的范围"""
        self.frame_count = count
        self.start_slider.setRange(1, count)
        self.end_slider.setRange(1, count)
        self.range_start.setRange(1, count)
        self.range_end.setRange(1, count)
        # 默认全选
        self.start_slider.setValue(1)
        self.end_slider.setValue(count)
        self.range_start.setValue(1)
        self.range_end.setValue(count)

    def set_playback_fps(self, fps):
        """从外部设置播放帧率（不触发信号）"""
        self._playback_fps = fps
        self.playback_fps_spin.blockSignals(True)
        self.playback_fps_spin.setValue(fps)
        self.playback_fps_spin.blockSignals(False)

    def set_current_frame_info(self, idx, total):
        """更新当前帧显示"""
        self.info_label.setText(f"当前帧: {idx + 1} / {total}")

    def set_duration_text(self, text):
        """更新总时长显示"""
        self.duration_label.setText(text)

    def get_step(self):
        return self.step_spin.value()

    # ---------- 内部槽 ----------
    def _toggle_order_mode(self):
        self.thumb_panel.toggle_order_mode()
        if self.thumb_panel.order_mode == "click":
            self.btn_order.setText("🖱 选取顺序 (当前)")
        else:
            self.btn_order.setText("🔢 编号顺序 (当前)")

    def _apply_range_selection(self):
        """根据当前滑块/数值框选中的范围调用 thumb_panel.select_range"""
        if self.frame_count == 0:
            return
        start = self.range_start.value() - 1
        end = self.range_end.value() - 1
        if start > end:
            start, end = end, start
        self.thumb_panel.select_range(start, end)

    def _on_start_slider_changed(self, v):
        self.range_start.blockSignals(True)
        self.range_start.setValue(v)
        self.range_start.blockSignals(False)
        if v > self.range_end.value():
            v = self.range_end.value()
            self.start_slider.blockSignals(True)
            self.start_slider.setValue(v)
            self.start_slider.blockSignals(False)
            self.range_start.blockSignals(True)
            self.range_start.setValue(v)
            self.range_start.blockSignals(False)
        self._apply_range_selection()

    def _on_end_slider_changed(self, v):
        self.range_end.blockSignals(True)
        self.range_end.setValue(v)
        self.range_end.blockSignals(False)
        if v < self.range_start.value():
            v = self.range_start.value()
            self.end_slider.blockSignals(True)
            self.end_slider.setValue(v)
            self.end_slider.blockSignals(False)
            self.range_end.blockSignals(True)
            self.range_end.setValue(v)
            self.range_end.blockSignals(False)
        self._apply_range_selection()

    def _on_start_spin_changed(self, v):
        self.start_slider.blockSignals(True)
        self.start_slider.setValue(v)
        self.start_slider.blockSignals(False)
        if v > self.range_end.value():
            v = self.range_end.value()
            self.range_start.blockSignals(True)
            self.range_start.setValue(v)
            self.range_start.blockSignals(False)
            self.start_slider.blockSignals(True)
            self.start_slider.setValue(v)
            self.start_slider.blockSignals(False)
        self._apply_range_selection()

    def _on_end_spin_changed(self, v):
        self.end_slider.blockSignals(True)
        self.end_slider.setValue(v)
        self.end_slider.blockSignals(False)
        if v < self.range_start.value():
            v = self.range_start.value()
            self.range_end.blockSignals(True)
            self.range_end.setValue(v)
            self.range_end.blockSignals(False)
            self.end_slider.blockSignals(True)
            self.end_slider.setValue(v)
            self.end_slider.blockSignals(False)
        self._apply_range_selection()