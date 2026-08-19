from PySide6.QtGui import QPixmap, QPainter, QColor, QImage
from PySide6.QtCore import QRect
import numpy as np
import cv2

# ==================== 辅助函数 ====================
def make_checkerboard_pixmap(width, height, cell=10):
    pixmap = QPixmap(width, height)
    painter = QPainter(pixmap)
    color1 = QColor(180, 180, 180)
    color2 = QColor(220, 220, 220)
    for y in range(0, height, cell):
        for x in range(0, width, cell):
            color = color1 if ((x // cell) + (y // cell)) % 2 == 0 else color2
            painter.fillRect(QRect(x, y, cell, cell), color)
    painter.end()
    return pixmap

def compose_alpha_over_background(rgba_image, bg_color=None, checker=False):
    h, w = rgba_image.shape[:2]
    if checker:
        bg_pix = make_checkerboard_pixmap(w, h)
        bg_qimg = bg_pix.toImage()
        bg = np.frombuffer(bg_qimg.bits(), np.uint8).reshape(h, w, 4)[:, :, :3]
    else:
        bg = np.zeros((h, w, 3), dtype=np.uint8)
        if bg_color:
            bg[:] = (bg_color.blue(), bg_color.green(), bg_color.red())
    fg = rgba_image[:, :, :3]   # 保持 RGBA 的 RGB 部分（不做转换）
    alpha = rgba_image[:, :, 3] / 255.0
    composed = (fg * alpha[..., np.newaxis] + bg * (1 - alpha[..., np.newaxis])).astype(np.uint8)
    qimg = QImage(composed.data, w, h, 3 * w, QImage.Format_BGR888)
    return QPixmap.fromImage(qimg.copy())

def imread_unicode(path):
    try:
        # 尝试使用 numpy 读取以避免中文路径问题
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return cv2.imread(path)

def _detect_background_color(image_bgr):
    """从图像边缘检测背景主色（BGR）"""
    h, w = image_bgr.shape[:2]
    border_pixels = []
    border_pixels.append(image_bgr[0, :].reshape(-1, 3))
    border_pixels.append(image_bgr[h-1, :].reshape(-1, 3))
    border_pixels.append(image_bgr[:, 0].reshape(-1, 3))
    border_pixels.append(image_bgr[:, w-1].reshape(-1, 3))
    border_pixels = np.concatenate(border_pixels, axis=0).astype(np.float32)
    avg_color = border_pixels.mean(axis=0)
    return np.clip(avg_color, 0, 255).astype(np.uint8)

def _color_distance(pixel, bg_color):
    return np.sqrt(np.sum((pixel.astype(np.float32) - bg_color.astype(np.float32))**2, axis=-1))

def _is_residual_mask(rgba, bg_color, threshold=80, alpha_min=1, alpha_max=254):
    bgr = rgba[:, :, :3].astype(np.float32)
    alpha = rgba[:, :, 3].astype(np.float32)
    edge_mask = (alpha > alpha_min) & (alpha < alpha_max)
    dist = _color_distance(bgr, bg_color)
    alpha_safe = np.where(edge_mask, alpha / 255.0, 1.0)
    scaled_bgr = bgr / np.maximum(alpha_safe[..., np.newaxis], 1e-6)
    scaled_dist = _color_distance(scaled_bgr, bg_color)
    residual_mask = edge_mask & ((dist < threshold) | (scaled_dist < threshold))
    return residual_mask

def residual_to_black(rgba, threshold=80):
    bg_color = _detect_background_color(rgba[:, :, :3])
    mask = _is_residual_mask(rgba, bg_color, threshold)
    rgba_out = rgba.copy()
    rgba_out[:, :, :3][mask] = 0
    return rgba_out

def residual_desaturate(rgba, threshold=80):
    bg_color = _detect_background_color(rgba[:, :, :3])
    mask = _is_residual_mask(rgba, bg_color, threshold)
    rgba_out = rgba.copy()
    gray = cv2.cvtColor(rgba_out[:, :, :3], cv2.COLOR_BGR2GRAY)
    gray_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    rgba_out[:, :, :3][mask] = gray_bgr[mask]
    return rgba_out

def semitransparent_to_black(rgba, alpha_min=1, alpha_max=254):
    alpha = rgba[:, :, 3]
    mask = (alpha >= alpha_min) & (alpha <= alpha_max)
    rgba_out = rgba.copy()
    rgba_out[:, :, :3][mask] = 0
    return rgba_out

def semitransparent_to_opaque(rgba, alpha_min=1, alpha_max=254):
    alpha = rgba[:, :, 3]
    mask = (alpha >= alpha_min) & (alpha <= alpha_max)
    rgba_out = rgba.copy()
    rgba_out[:, :, 3][mask] = 255
    return rgba_out