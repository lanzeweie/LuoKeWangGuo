# 数据集说明

本文档介绍 YOLO 格式数据集的目录结构、标注规范，以及数据管理工具的使用方法。

## 相关文档

| 文档 | 说明 |
|------|------|
| [README.md](../README.md) | 项目整体说明 |
| [tools/README.md](../tools/README.md) | 训练脚本与数据准备工具 |

## 目录结构

```
data/
├── dataset.yaml                    # 主配置文件（YOLO 训练用）
├── classes.txt                     # 类别名称列表（class_id → 类别名）
│
├── images/                         # 图片目录
│   └── [精灵文件夹]/               # 文件夹名任意
│       ├── img_001.jpg
│       └── ...
│
├── labels/                         # 标注文件目录（与 images 同结构）
│   └── [精灵文件夹]/
│       ├── img_001.txt
│       └── ...
│
└── X-AnyLabeling/                 # X-AnyLabeling 导出目录（待导入）
    ├── img_001.jpg
    └── img_001.txt
```

---

## 核心概念：文件夹名 vs 类别名

| 项目 | 来源 | 作用 |
|------|------|------|
| **文件夹名** | 真实目录结构 | 组织图片，不影响模型训练 |
| **classes.txt** | 手动维护 | 定义所有类别名称，按顺序索引 |
| **class_id** | 标注文件 | 指向 classes.txt 的索引 |

**关键理解**：
- 文件夹名和类别名**可以完全不同**
- `dataset.yaml` 的 `train/val` 来源于**真实文件夹**
- `dataset.yaml` 的 `names` 来源于 **classes.txt**
- 标注文件里的 `class_id` 决定图片属于哪个类别

### 示例

```
classes.txt:
奇丽族群-奇丽草
奇丽族群-奇丽草-污染

images/奇丽家族/         ← 文件夹名是"奇丽家族"
  ├── img_001.jpg
  └── img_001.txt       ← 里面的 class_id=0 表示"奇丽族群-奇丽草"
```

---

## `dataset.yaml` 配置说明

```yaml
# YOLOv8 数据集配置
# train/val 按真实文件夹结构
# names 按 classes.txt 顺序，class_id 即索引

path: .

train:
  - images/奇丽家族        # 文件夹路径

val:
  - images/奇丽家族

nc: 2                      # classes.txt 中的类别总数

names:
  0: 奇丽族群-奇丽草       # class_id 0
  1: 奇丽族群-奇丽草-污染  # class_id 1
```

---

## 数据准备工具

详见 [tools/README.md](../tools/README.md)。

### 视频帧提取

使用 `extract_frames.py` 从游戏录像中提取训练图片：

```bash
uv run python tools/extract_frames.py --video input.mp4 --output data/images --interval 2
```

### 数据集管理工具

```bash
uv run python data/xanylabeling_organizer.py
```

### 菜单功能

| 选项 | 功能 |
|------|------|
| [1] 查看所有精灵状态 | 显示文件夹和类别状态 |
| [2] 从 X-AnyLabeling 导入 | 手动选择要导入的精灵 |
| [3] 智能导入 | 自动检测并导入所有数据 |
| [4] 添加新精灵 | 创建文件夹 + 添加类别 |
| [5] 删除精灵 | 删除文件夹 |
| [6] 重新生成 dataset.yaml | 从当前状态重建配置 |
| [7] 同步配置 | 同步 classes.txt 和文件夹 |
| [8] 显示当前配置 | 查看路径和配置详情 |

---

## 新增精灵类型（使用工具）

### 方式一：智能导入（推荐）

1. 把 X-AnyLabeling 导出的图片放到 `data/X-AnyLabeling/`
2. 运行工具，选择 `[3] 智能导入`
3. 工具会自动解析文件并导入

### 方式二：手动添加

1. 运行 `[4] 添加新精灵`
2. 输入文件夹名和类别名
3. 工具会创建目录并更新配置

---

## YOLO 标注文件格式

每个 `.txt` 文件对应一张图片，格式为：

```
class_id x_center y_center width height
```

- **class_id**: 整数，从 0 开始（对应 `classes.txt` 的索引）
- **x_center, y_center, width, height**: 均为 **归一化值 (0~1)**

### 示例

图片 `img_001.png` 的标注文件 `img_001.txt`：

```
0 0.512 0.387 0.123 0.098
```

表示：
- 类别 ID = 0（奇丽族群-奇丽草）
- 框中心点 = (51.2%, 38.7%)
- 框宽高 = (12.3%, 9.8%)

---

## 常见问题

### Q1: 每个精灵需要多少图片？
**推荐**: 最少 1000 张，理想 3000+ 张。太少会导致欠拟合。

### Q2: 验证集需要单独准备吗？
不需要。YOLO 会自动从 `train` 路径中划分 10% 作为验证集。

### Q3: 不同精灵的图片尺寸可以不一致吗？
可以。YOLO 会在训练时自动 resize 到统一尺寸（默认 640x640）。

### Q4: class_id 0 和 class_id 1 的区别？
看 `classes.txt`：
```
0: 奇丽族群-奇丽草
1: 奇丽族群-奇丽草-污染
```
标注文件里写 `0` 就是正常精灵，写 `1` 就是被污染的精灵。

### Q5: 为什么有 747 张图片但显示 class_id 有 0 和 1？
说明这批数据里同时包含了：
- 正常精灵（class_id=0）
- 污染精灵（class_id=1）

---

## 模型训练

准备好数据集后，训练模型：

```bash
# 一键训练（默认 GPU + 1280 分辨率）
uv run python tools/train.py --epochs 100

# 指定训练参数
uv run python tools/train.py --epochs 100 --batch 16 --device 0 --imgsz 1280
```

详见 [tools/README.md](../tools/README.md)。

### 模型文件

| 阶段 | 路径 | 说明 |
|------|------|------|
| 预训练基座 | `models/base/yolov8n.pt` | YOLO 官方提供 |
| 训练后模型 | `models/trained/luoke_pet.pt` | 当前项目训练好的模型 |
| 训练输出 | `runs/detect/luoke_pet/weights/best.pt` | 训练产生的最佳模型 |
