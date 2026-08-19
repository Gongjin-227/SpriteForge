# SpriteForge

SpriteForge 是一款基于 PySide6 和深度学习模型的桌面图像/视频抠图工具，支持多种抠图方式，包括色度抠图、亮度抠图、RMBG-2、BiRefNet，并可选集成 CorridorKey 进行边缘精修。适用于绿幕/蓝幕素材、真实背景主体分割以及序列帧批量处理。

## 功能特点

- **多种抠图模式**：
  - 快速：色度抠图（Chroma Key），支持多区域颜色清理
  - 快速：亮度抠图（Luma Key）
  - 标准：RMBG-2（通用主体分割）
  - 精细：BiRefNet（高精度分割，支持线条增强）
- **通用区域清理**：用户可框选多个矩形区域，独立设置背景色和容差，作为后处理附加到任意模式
- **可选 CorridorKey 边缘精修**：针对绿幕/蓝幕素材，修复发丝细节、去除颜色溢出（需单独安装）
- **批处理后处理**：
  - 绿色/背景残边转黑
  - 绿色/背景残边去饱和
  - 半透明像素转黑
  - 半透明像素转不透明
- **导入与导出**：
  - 支持视频、GIF、图片序列文件夹、单张图片
  - 帧提取、播放、区间选择、缩略图网格
  - 导出透明 PNG 序列、遮罩、原始帧
- **友好的 GUI 界面**：原图/抠图对比预览、缩放、裁剪、背景切换、进度条

## 环境要求

- Windows / Linux / macOS
- Python 3.10+
- NVIDIA GPU（推荐，显存 >= 6GB 可运行大部分模型，CorridorKey 需 6-8GB）

## 安装依赖

建议使用 Anaconda 创建独立环境：

```bash
conda create -n spriteforge python=3.10
conda activate spriteforge
pip install -r requirements.txt
```

如果使用 GPU，请根据你的 CUDA 版本安装 PyTorch，例如 CUDA 12.1：

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

## 模型下载

### RMBG-2

```bash
hf download briaai/RMBG-2.0 --local-dir models/rmbg2
```

注意：该模型需要同意许可协议（免费非商业使用）。

### BiRefNet（标准版）

```bash
hf download ZhengPeng7/BiRefNet --local-dir models/birefnet
```

### BiRefNet HR-matting（抠图优化版）

```bash
hf download ZhengPeng7/BiRefNet_HR-matting --local-dir models/birefnet_hr_matting
```

### CorridorKey

CorridorKey 为外部仓库，不包含在本项目中。请执行：

```bash
git clone https://github.com/nikopueringer/CorridorKey.git models/CorridorKey
```

然后下载其模型权重：

```bash
hf download nikopueringer/CorridorKey_v1.0 --local-dir models/CorridorKey/CorridorKeyModule/checkpoints
```

如果之后需要蓝色幕布模型：

```bash
hf download nikopueringer/CorridorKeyBlue_1.0 --local-dir models/CorridorKey/CorridorKeyModule/checkpoints
```

## 使用说明

1. 运行 `python main.py`
2. 导入素材（视频/GIF/图片序列/单图）
3. 在右侧面板选择抠图模式，调整对应参数
4. 可选：勾选“启用区域清理”，点击“添加区域”在预览中框选多个区域，每个区域可独立设置颜色和容差
5. 可选：勾选“启用线条增强 (CorridorKey)”进行边缘精修（仅绿幕/蓝幕，黑/白幕请使用亮度抠图）
6. 可选：勾选“启用残边处理”并选择处理方式
7. 点击“预览抠图”查看当前帧效果，或点击“批量抠图”处理工作区所有帧
8. 在导出面板设置输出目录，导出原始帧或透明 PNG

## 项目结构

```
SpriteForge/
├── main.py                 # 入口文件
├── requirements.txt        # Python 依赖
├── README.md
├── LICENSE
├── core/
│   ├── extractor.py        # 帧提取
│   ├── matting.py          # 抠图算法
│   └── models.py           # 数据模型
├── ui/
│   ├── main_window.py      # 主窗口
│   ├── preview_widget.py   # 预览组件
│   ├── panels/             # 右侧设置面板
│   └── widgets/            # 缩略图等控件
└── models/                 # 模型权重（不提交到 Git，需自行下载）
```

## 第三方许可证

本项目代码采用 MIT 许可证，详见 `LICENSE` 文件。

**使用的模型和库**：

| 组件 | 许可证 | 说明 |
|------|--------|------|
| BiRefNet | MIT | 论文/代码/权重均开源 |
| RMBG-2 | BRIA 自定义 | 非商业免费使用 |
| CorridorKey | CC BY-NC-SA 4.0 | 非商业使用，需保留名称 |
| PySide6 | LGPL/GPL/Commercial | 见 Qt 官方 |
| OpenCV | Apache 2.0 | |
| PyTorch | BSD-3 | |

使用本项目时，请确保遵守上述许可证。若用于商业目的，请与相应作者/公司联系获取授权。

## 致谢

- [BiRefNet](https://github.com/ZhengPeng7/BiRefNet)
- [RMBG-2](https://huggingface.co/briaai/RMBG-2.0)
- [CorridorKey](https://github.com/nikopueringer/CorridorKey)
- [PySide6](https://wiki.qt.io/Qt_for_Python)