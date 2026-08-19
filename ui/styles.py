# ui/styles.py

MAIN_STYLE = """
QMainWindow { background-color: #f5f7fa; color: #2c3e50; }
QGroupBox { font-weight: bold; border: 1px solid #c0c8d0; border-radius: 6px; margin-top: 12px; padding-top: 15px; color: #2c3e50; background-color: #ffffff; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #2c3e50; }
QLabel { color: #2c3e50; }
QPushButton { background-color: #e9edf2; color: #2c3e50; border: 1px solid #b0bec5; border-radius: 4px; font-size: 13px; }
QPushButton:hover { background-color: #cfd8dc; }
QPushButton:pressed { background-color: #b0bec5; }
QPushButton:disabled { background-color: #f0f0f0; color: #999999; border: 1px solid #d0d0d0; }
QSlider::groove:horizontal { border: 1px solid #b0bec5; height: 6px; border-radius: 3px; background: #e0e0e0; }
QSlider::handle:horizontal { background: #1976D2; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: #1565C0; }
QLineEdit { background-color: #ffffff; color: #2c3e50; border: 1px solid #b0bec5; padding: 4px; }
QComboBox { background-color: #ffffff; color: #2c3e50; border: 1px solid #b0bec5; padding: 4px; }
QCheckBox { color: #2c3e50; }
QProgressBar { border: 1px solid #b0bec5; border-radius: 4px; background-color: #ffffff; text-align: center; color: #2c3e50; }
QProgressBar::chunk { background-color: #1976D2; border-radius: 3px; }
QListWidget { background-color: #ffffff; border: 1px solid #c0c8d0; }
QListWidget::item:selected { background-color: #1976D2; color: white; }
QMenuBar { font-size: 14px; padding: 4px; background-color: #e9edf2; border-bottom: 1px solid #b0bec5; }
QMenuBar::item { padding: 6px 16px; background-color: transparent; }
QMenuBar::item:selected { background-color: #cfd8dc; }
QMenu { font-size: 14px; padding: 4px; }
QMenu::item { padding: 6px 24px; }
"""

def apply_style(widget):
    """为指定 widget 应用全局样式"""
    widget.setStyleSheet(MAIN_STYLE)