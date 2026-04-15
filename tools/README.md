# Tools 工具说明

本文档介绍 `tools/` 目录下的数据准备与训练脚本。

## 目录结构

```
tools/
├── train.py                   # 训练脚本
├── prepare_dataset.py         # 数据集准备工具
├── extract_frames.py          # 视频帧提取工具
├── convert_labelme_to_yolo.py # LabelMe 格式转换工具
└── README.md                  # 本文档
```

## 训练脚本

### train.py — YOLO 模型训练

训练 YOLOv8 模型，支持 CPU/GPU。

```bash
# 基本用法（默认 GPU + 1280 分辨率）
uv run python tools/train.py

# 指定参数
uv run python tools/train.py --epochs 100 --batch 16 --device 0

# 完整参数
uv run python tools/train.py \
    --data data/dataset.yaml \
    --epochs 100 \
    --imgsz 1280 \
    --batch 16 \
    --name luoke_pet \
    --device 0
```

### 一键训练命令

```bash
uv run python tools/train.py --epochs 100
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--data` | `data/dataset.yaml` | 数据集配置文件路径 |
| `--epochs` | 100 | 训练轮数 |
| `--imgsz` | 1280 | 输入图像尺寸（长边，YOLO 等比缩放） |
| `--batch` | 16 | 批次大小 |
| `--name` | `luoke_pet` | 训练任务名称 |
| `--device` | `0` | 训练设备 (`cpu` 或 `0`，默认 GPU) |

### 模型指定

训练脚本使用本地预训练模型 `models/base/yolov8n.pt` 作为基座：

```python
model = YOLO('models/base/yolov8n.pt')  # 使用本地基座模型
```

### 训练输出

训练完成后，模型保存在 `runs/detect/{name}/weights/` 目录：

```
runs/detect/luoke_pet/weights/
├── best.pt   # 最佳模型
└── last.pt   # 最后一轮模型
```

### 训练前提

1. 确保数据集已准备好，详见 [data/README.md](../data/README.md)
2. 确保 `data/dataset.yaml` 配置正确
3. GPU 训练需要 NVIDIA 显卡 + CUDA 环境

---

## 数据集准备工具

### prepare_dataset.py — 数据集结构准备

将原始数据整理成 YOLO 训练所需的目录结构。

```bash
# 基本用法（交互式）
uv run python tools/prepare_dataset.py

# 指定路径
uv run python tools/prepare_dataset.py --dataset ./raw_data --output data.yaml
```

### extract_frames.py — 视频帧提取

从视频中按固定间隔提取帧，用于收集训练数据。

```bash
# 每 2 秒提取一帧
uv run python tools/extract_frames.py --video input.mp4 --output dataset/images --interval 2

# 每 5 秒提取一帧
uv run python tools/extract_frames.py --video input.mp4 --output dataset/images --interval 5

# 指定起始和结束时间（秒）
uv run python tools/extract_frames.py --video input.mp4 --output dataset/images --interval 2 --start 10 --end 60
```

### convert_labelme_to_yolo.py — 格式转换

将 LabelMe 标注格式转换为 YOLO 格式。

```bash
# 基本用法（交互式）
uv run python tools/convert_labelme_to_yolo.py

# 指定路径
uv run python tools/convert_labelme_to_yolo.py \
    --input labelme_export/ \
    --output yolo_dataset/ \
    --classes classes.txt
```

### xanylabeling_organizer.py — 数据集管理工具

X-AnyLabeling 导出数据的管理工具，支持智能导入、类别管理等。

```bash
uv run python data/xanylabeling_organizer.py
```

详细说明见 [data/README.md](../data/README.md)。

---

## 数据集格式

YOLO 格式数据集需要以下文件：

```
data/
├── dataset.yaml     # 训练配置文件
├── classes.txt      # 类别名称列表
├── images/          # 图片目录
│   └── [精灵文件夹]/
│       ├── img_001.jpg
│       └── ...
└── labels/          # 标注目录（与 images 同结构）
    └── [精灵文件夹]/
        ├── img_001.txt
        └── ...
```

详见 [data/README.md](../data/README.md)。

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [README.md](../README.md) | 项目整体说明 |
| [data/README.md](../data/README.md) | 数据集格式与标注规范 |
