# core/models.py
from dataclasses import dataclass
from PySide6.QtCore import QRect

@dataclass
class CleanupRegion:
    name: str
    rect: QRect
    color_hex: str
    tolerance: int