# ui/panels/export_panel.py
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QProgressBar, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, Signal


class ExportPanel(QGroupBox):
    """导出面板，负责输出目录选择、导出按钮和进度条"""
    export_orig_clicked = Signal()
    export_matted_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__("💾 导出", parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 输出目录选择行
        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("输出目录:"))
        self.out_path_edit = QLineEdit()
        self.out_path_edit.setPlaceholderText("选择输出文件夹...")
        self.out_path_edit.setReadOnly(True)
        self.btn_out_dir = QPushButton("浏览")
        out_layout.addWidget(self.out_path_edit)
        out_layout.addWidget(self.btn_out_dir)
        layout.addLayout(out_layout)

        # 导出按钮
        self.export_btn_orig = QPushButton("导出原始帧")
        self.export_btn_matted = QPushButton("导出抠图帧")
        layout.addWidget(self.export_btn_orig)
        layout.addWidget(self.export_btn_matted)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def _connect_signals(self):
        self.btn_out_dir.clicked.connect(self._select_output_dir)
        self.export_btn_orig.clicked.connect(self.export_orig_clicked)
        self.export_btn_matted.clicked.connect(self.export_matted_clicked)

    def _select_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.out_path_edit.setText(folder)

    # ---------- 外部接口 ----------
    def get_output_dir(self):
        return self.out_path_edit.text().strip()

    def set_output_dir(self, path):
        self.out_path_edit.setText(path)

    def set_export_buttons_enabled(self, enabled):
        self.export_btn_orig.setEnabled(enabled)
        self.export_btn_matted.setEnabled(enabled)

    def set_progress_visible(self, visible):
        self.progress_bar.setVisible(visible)

    def set_progress_range(self, maximum):
        self.progress_bar.setMaximum(maximum)

    def set_progress_value(self, value):
        self.progress_bar.setValue(value)