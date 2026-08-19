import cv2
import numpy as np
from abc import ABC, abstractmethod
from pathlib import Path
import math
import sys
import importlib
from pathlib import Path

def _load_corridorkey_engine(device="auto", screen_color="auto"):
    """加载 CorridorKey 引擎（带缓存）"""
    if not hasattr(_load_corridorkey_engine, "cache"):
        _load_corridorkey_engine.cache = {}

    import torch
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    elif device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA 被请求但不可用")

    if screen_color == "auto":
        screen_color = "green"   # 默认绿色，后续可扩展

    cache_key = (device, screen_color)
    if cache_key in _load_corridorkey_engine.cache:
        return _load_corridorkey_engine.cache[cache_key]

    # 导入 CorridorKey 引擎
    root = Path(__file__).resolve().parent.parent / "models" / "CorridorKey"
    module_dir = root / "CorridorKeyModule"
    if not module_dir.exists():
        raise RuntimeError(f"CorridorKey 未找到于 {root}")

    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    try:
        from CorridorKeyModule.inference_engine import CorridorKeyEngine
    except Exception as e:
        raise RuntimeError(f"导入 CorridorKeyEngine 失败: {e}")

    # 查找 checkpoint 文件
    checkpoint_dir = module_dir / "checkpoints"
    safetensors = checkpoint_dir / "CorridorKey_v1.0.safetensors"
    pth = checkpoint_dir / "CorridorKey_v1.0.pth"
    if safetensors.exists():
        checkpoint_path = str(safetensors)
    elif pth.exists():
        checkpoint_path = str(pth)
    else:
        raise RuntimeError("未找到 CorridorKey 模型权重")

    # 使用较小分辨率避免显存不足
    # 你的 RTX 4050 6GB，2048 可能 OOM，先试 1024
    img_size = 1024 if torch.cuda.is_available() and torch.cuda.get_device_properties(0).total_memory < 8 * 1024**3 else 2048

    try:
        engine = CorridorKeyEngine(
            checkpoint_path=checkpoint_path,
            device=device,
            img_size=img_size,
        )
    except TypeError:
        # 如果新版 API 参数不同，尝试旧版
        engine = CorridorKeyEngine(
            checkpoint_path=checkpoint_path,
            device=device,
        )

    _load_corridorkey_engine.cache[cache_key] = engine
    return engine


def corridorkey_refine(image, rgba, device="auto", screen_color="auto", despill_strength=0.85):
    """
    使用 CorridorKey 对抠图结果进行边缘精修。
    image: BGR 图像 (numpy uint8)
    rgba: BGRA 图像 (alpha 0~255)
    返回: 精修后的 BGRA
    """
    import numpy as np
    import torch
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    elif device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA 被请求但不可用")
    engine = _load_corridorkey_engine(device, screen_color)

    # 转换为 RGB 和灰度 alpha
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.uint8, copy=True)
    alpha = rgba[:, :, 3].astype(np.uint8, copy=True)

    # 调用引擎
    result = engine.process_frame(
        rgb,
        alpha,
        input_is_linear=False,
        fg_is_straight=True,
        despill_strength=max(0.0, min(1.0, float(despill_strength))),
        auto_despeckle=True,
        despeckle_size=400,
        generate_comp=False,
        post_process_on_gpu=device.startswith("cuda"),
        screen_channel=2 if screen_color == "blue" else 1,
    )

    # 提取 alpha
    processed = result['processed']
    if processed.ndim == 4:
        processed = processed[0]
    alpha_new = (np.clip(processed[..., 3:4], 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8).squeeze(-1)

    rgba_out = rgba.copy()
    rgba_out[:, :, 3] = alpha_new
    return rgba_out


class MatteMethod(ABC):
    @abstractmethod
    def process(self, image: np.ndarray) -> np.ndarray:
        pass


class ChromaKeyMethod(MatteMethod):
    def __init__(self, color_hex="#00FF00", tolerance=30, regions=None, use_corridor=False):
        self.color_hex = color_hex
        self.tolerance = tolerance
        self.regions = regions  # 多区域列表，元素为 CleanupRegion 对象
        self.use_corridor = use_corridor

    def process(self, image):
        h, w = image.shape[:2]
        # 初始化为完全不透明
        alpha = np.full((h, w), 255, dtype=np.uint8)

        if self.regions is None:
            # 传统单区域：全图
            alpha = self._chroma_key_region(image, self.color_hex, self.tolerance)
        else:
            # 多区域：遍历每个区域，取并集（所有区域中任意一个判定为背景，则透明）
            for region in self.regions:
                x, y, rw, rh = region.rect.getRect()
                x = max(0, x); y = max(0, y)
                rw = min(rw, w - x); rh = min(rh, h - y)
                if rw <= 0 or rh <= 0:
                    continue
                roi = image[y:y+rh, x:x+rw]
                local_alpha = self._chroma_key_region(roi, region.color_hex, region.tolerance)
                # 取最小值：只要某个区域认为透明，最终就透明
                alpha[y:y+rh, x:x+rw] = np.minimum(alpha[y:y+rh, x:x+rw], local_alpha)

        rgba = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
        rgba[:, :, 3] = alpha

        if self.use_corridor:
            rgba = corridorkey_refine(image, rgba)

        return rgba

    def _chroma_key_region(self, roi, color_hex, tolerance):
        """对单个 ROI 执行色度抠图，返回 alpha 通道（0-255）"""
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # 将十六进制颜色转为 HSV
        hex_stripped = color_hex.lstrip('#')
        r, g, b = tuple(int(hex_stripped[i:i+2], 16) for i in (0, 2, 4))
        target_bgr = np.uint8([[[b, g, r]]])
        target_hsv = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2HSV)[0][0]
        h_target, s_target, v_target = int(target_hsv[0]), int(target_hsv[1]), int(target_hsv[2])

        half_tol = tolerance // 2
        lower_h = (h_target - half_tol) % 180
        upper_h = (h_target + half_tol) % 180
        lower_s = max(0, s_target - tolerance * 2)
        upper_s = min(255, s_target + tolerance * 2)
        lower_v = max(0, v_target - tolerance * 2)
        upper_v = min(255, v_target + tolerance * 2)

        if lower_h < upper_h:
            mask = cv2.inRange(hsv, (lower_h, lower_s, lower_v), (upper_h, upper_s, upper_v))
        else:
            mask1 = cv2.inRange(hsv, (lower_h, lower_s, lower_v), (180, upper_s, upper_v))
            mask2 = cv2.inRange(hsv, (0, lower_s, lower_v), (upper_h, upper_s, upper_v))
            mask = cv2.bitwise_or(mask1, mask2)

        # 背景色为255，前景为0；alpha应为前景255，背景0
        return cv2.bitwise_not(mask)

class LumaKeyMethod(MatteMethod):
    def __init__(self, threshold=128, invert=False, use_corridor=False):
        self.threshold = threshold
        self.invert = invert
        self.use_corridor = use_corridor


    def process(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, self.threshold, 255, cv2.THRESH_BINARY)
        if self.invert:
            mask = cv2.bitwise_not(mask)
        rgba = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
        rgba[:, :, 3] = mask

        if self.use_corridor:
            rgba = corridorkey_refine(image, rgba)

        return rgba

class RMBGMethod(MatteMethod):
    def __init__(self, model_path=None, use_corridor=False):
        import torch
        from PIL import Image
        from transformers import AutoModelForImageSegmentation
        from torchvision import transforms

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.torch = torch
        self.Image = Image
        self.transforms = transforms

        self.enable_region_cleanup = False
        self.cleanup_regions = []   # 存储 CleanupRegion 对象

        if model_path is None:
            model_path = Path(__file__).resolve().parent.parent / "models" / "rmbg2"

        print(f"RMBG-2 使用设备: {self.device}")
        print(f"加载模型: {model_path}")
        self.model = AutoModelForImageSegmentation.from_pretrained(
            str(model_path), trust_remote_code=True
        ).to(self.device)
        self.model.eval()

        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[1.0, 1.0, 1.0])
        ])
        self.use_corridor = use_corridor


    def _hex_to_hsv(self, hex_color):
        hex_stripped = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_stripped[i:i+2], 16) for i in (0, 2, 4))
        bgr = np.uint8([[[b, g, r]]])
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[0][0]
        return int(hsv[0]), int(hsv[1]), int(hsv[2])

    def process(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]

        # 统一缩放到 1024x1024
        target_size = 1024
        img_resized = cv2.resize(image, (target_size, target_size), interpolation=cv2.INTER_LINEAR)
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        pil_img = self.Image.fromarray(img_rgb)
        input_tensor = self.transform(pil_img).unsqueeze(0).to(self.device)

        with self.torch.no_grad():
            preds = self.model(input_tensor)[-1].sigmoid().cpu().numpy()

        mask = preds.squeeze()
        if mask.ndim == 3:
            mask = mask[0]
        mask = (mask * 255).astype(np.uint8)
        mask_resized = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)

        if self.enable_region_cleanup and self.cleanup_regions:
            for region in self.cleanup_regions:
                # 获取区域坐标并限制在图像内
                x, y, rw, rh = region.rect.getRect()
                x = max(0, x)
                y = max(0, y)
                rw = min(rw, w - x)
                rh = min(rh, h - y)
                if rw <= 0 or rh <= 0:
                    continue

                # 提取 ROI 并转换为 HSV
                roi = image[y:y+rh, x:x+rw]
                hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

                # 颜色检测参数
                h_target, s_target, v_target = self._hex_to_hsv(region.color_hex)
                half_tol = region.tolerance // 2
                lower_h = (h_target - half_tol) % 180
                upper_h = (h_target + half_tol) % 180
                lower_s = max(0, s_target - region.tolerance * 2)
                upper_s = min(255, s_target + region.tolerance * 2)
                lower_v = max(0, v_target - region.tolerance * 2)
                upper_v = min(255, v_target + region.tolerance * 2)

                # 生成颜色掩码
                if lower_h < upper_h:
                    color_mask_roi = cv2.inRange(hsv_roi, (lower_h, lower_s, lower_v), (upper_h, upper_s, upper_v))
                else:
                    mask1 = cv2.inRange(hsv_roi, (lower_h, lower_s, lower_v), (180, upper_s, upper_v))
                    mask2 = cv2.inRange(hsv_roi, (0, lower_s, lower_v), (upper_h, upper_s, upper_v))
                    color_mask_roi = cv2.bitwise_or(mask1, mask2)

                # 将该区域内匹配颜色的像素 alpha 置 0
                mask_resized[y:y+rh, x:x+rw][color_mask_roi != 0] = 0

        rgba = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
        rgba[:, :, 3] = mask_resized
        if self.use_corridor:
            rgba = corridorkey_refine(image, rgba)
        return rgba

class BiRefNetMethod(MatteMethod):
    def __init__(self, use_corridor=False, model_path=None, resolution=None, key_color_hex=None):
        import torch
        from PIL import Image
        from transformers import AutoModelForImageSegmentation
        from torchvision import transforms

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.torch = torch
        self.Image = Image
        self.transforms = transforms
        self.use_corridor = use_corridor
        self.resolution = resolution          # None 或 "auto" 自动，或指定整数
        self.key_color_hex = key_color_hex    # 手动指定背景色，如 "#00FF00"；None 则自动检测

        self.enable_region_cleanup = False
        self.cleanup_regions = []

        if model_path is None:
            model_path = Path(__file__).resolve().parent.parent / "models" / "birefnet_hr_matting"

        print(f"BiRefNet 使用设备: {self.device}")
        print(f"加载模型: {model_path}")

        self.model = AutoModelForImageSegmentation.from_pretrained(
            str(model_path),
            trust_remote_code=True
        ).to(self.device)
        self.model = self.model.float()
        self.model.eval()

        # 预处理基础变换（动态分辨率在 process 中处理）
        self.transform_base = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225])
        ])


    def _auto_resolution(self, h, w):
        """参考 auto_ai_resolution_for_image，限制在 1024~2048 之间"""
        area_edge = math.sqrt(max(1, h) * max(1, w))
        target = max(1024, area_edge)
        target = min(target, 2048)          # 避免显存不足，上限设为 2048
        aligned = int(round(target / 32) * 32)
        return max(1024, min(2048, aligned))

    def _auto_detect_key_color(self, image_bgr):
        """从图像边缘自动判断背景色（绿幕/蓝幕），返回 BGR tuple"""
        h, w = image_bgr.shape[:2]
        # 收集四边像素
        edge_pixels = []
        for y in range(h):
            edge_pixels.append(image_bgr[y, 0])
            edge_pixels.append(image_bgr[y, w - 1])
        for x in range(w):
            edge_pixels.append(image_bgr[0, x])
            edge_pixels.append(image_bgr[h - 1, x])

        edge_pixels = np.array(edge_pixels, dtype=np.float32)
        avg_color = edge_pixels.mean(axis=0)
        b, g, r = avg_color

        # 判断绿色或蓝色占优
        if g > r and g > b:
            return (int(b), int(g), int(r))  # 绿色背景
        elif b > r and b > g:
            return (int(b), int(g), int(r))  # 蓝色背景
        else:
            # 默认绿色
            return (0, 255, 0)

    def _despill_edges(self, rgba, key_bgr, strength=0.85):
        """去溢色：只处理半透明边缘，抑制与背景色相近的通道"""
        bgr = rgba[:, :, :3].astype(np.int16)
        alpha = rgba[:, :, 3].astype(np.float32) / 255.0

        # 边缘掩码：alpha 在 0 和 1 之间
        edge_mask = (alpha > 0.0) & (alpha < 1.0)

        # 背景色主通道
        key_b, key_g, key_r = key_bgr
        key_max = max(key_b, key_g, key_r)
        if key_max == key_g:
            spill_channel = 1  # 绿色
        elif key_max == key_b:
            spill_channel = 0  # 蓝色
        else:
            spill_channel = 2  # 红色（较少见）

        # 计算溢色强度：该通道值高于其他两个通道的部分
        other_channels = [i for i in range(3) if i != spill_channel]
        spill = bgr[:, :, spill_channel] - np.maximum(bgr[:, :, other_channels[0]], bgr[:, :, other_channels[1]])
        spill = np.clip(spill, 0, None)

        # 越靠近边缘，抑制越强
        edge_factor = 1.0 - alpha
        reduction = spill * strength * edge_factor

        # 应用抑制
        bgr_new = bgr.copy()
        bgr_new[:, :, spill_channel] = np.clip(bgr[:, :, spill_channel] - reduction, 0, 255)

        # 仅对边缘像素生效
        bgr_final = bgr.copy()
        bgr_final[edge_mask] = bgr_new[edge_mask]

        result = np.dstack([bgr_final.astype(np.uint8), rgba[:, :, 3]])
        return result

    def process(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]

        # 动态分辨率
        if self.resolution is None or str(self.resolution).lower() == "auto":
            target_res = self._auto_resolution(h, w)
        else:
            target_res = int(self.resolution)

        # 高质量缩放输入图像（LANCZOS4）
        img_resized = cv2.resize(image, (target_res, target_res), interpolation=cv2.INTER_LANCZOS4)
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        pil_img = self.Image.fromarray(img_rgb)
        input_tensor = self.transform_base(pil_img).unsqueeze(0).to(self.device)

        with self.torch.no_grad():
            preds = self.model(input_tensor)[-1].sigmoid().cpu().numpy()

        mask = preds.squeeze()
        if mask.ndim == 3:
            mask = mask[0]
        mask = (mask * 255).astype(np.uint8)

        # 使用 LANCZOS 缩放 mask 回原尺寸
        mask_resized = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LANCZOS4)


        # 区域清理（若启用）
        if self.enable_region_cleanup and self.cleanup_regions:
            for region in self.cleanup_regions:
                x, y, rw, rh = region.rect.getRect()
                x = max(0, x); y = max(0, y)
                rw = min(rw, w - x); rh = min(rh, h - y)
                if rw <= 0 or rh <= 0:
                    continue
                roi = image[y:y+rh, x:x+rw]
                hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                h_target, s_target, v_target = self._hex_to_hsv(region.color_hex)
                half_tol = region.tolerance // 2
                lower_h = (h_target - half_tol) % 180
                upper_h = (h_target + half_tol) % 180
                lower_s = max(0, s_target - region.tolerance * 2)
                upper_s = min(255, s_target + region.tolerance * 2)
                lower_v = max(0, v_target - region.tolerance * 2)
                upper_v = min(255, v_target + region.tolerance * 2)

                if lower_h < upper_h:
                    color_mask_roi = cv2.inRange(hsv_roi, (lower_h, lower_s, lower_v), (upper_h, upper_s, upper_v))
                else:
                    mask1 = cv2.inRange(hsv_roi, (lower_h, lower_s, lower_v), (180, upper_s, upper_v))
                    mask2 = cv2.inRange(hsv_roi, (0, lower_s, lower_v), (upper_h, upper_s, upper_v))
                    color_mask_roi = cv2.bitwise_or(mask1, mask2)
                mask_resized[y:y+rh, x:x+rw][color_mask_roi != 0] = 0

        # 合成 BGRA
        rgba = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
        rgba[:, :, 3] = mask_resized

        # Despill 去溢色
        if self.key_color_hex:
            key_bgr = self._hex_to_bgr(self.key_color_hex)
        else:
            key_bgr = self._auto_detect_key_color(image)
        rgba = self._despill_edges(rgba, key_bgr)
        if self.use_corridor:
            rgba = corridorkey_refine(image, rgba)
        return rgba

    def _hex_to_bgr(self, hex_color):
        hex_stripped = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_stripped[i:i+2], 16) for i in (0, 2, 4))
        return (b, g, r)  # OpenCV BGR


    def _hex_to_hsv(self, hex_color):
        hex_stripped = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_stripped[i:i+2], 16) for i in (0, 2, 4))
        bgr = np.uint8([[[b, g, r]]])
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[0][0]
        return int(hsv[0]), int(hsv[1]), int(hsv[2])

