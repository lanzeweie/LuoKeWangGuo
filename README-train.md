# YOLO 训练指南

本文档介绍如何使用 X-AnyLabeling 标注数据并训练 YOLOv8 模型。

## 1. 数据标注流程

### 1.1 使用 X-AnyLabeling 打标

[X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) 是一个支持多种标注格式的工具，可以导出 YOLO 格式。

**步骤**：
1. 打开 X-AnyLabeling，导入游戏截图
2. 使用矩形框 (Bounding Box) 标注精灵
3. 标注时选择对应的类别名称
4. 导出为 **YOLO 格式**

**导出结构**：
```
X-AnyLabeling-export/
├── classes.txt          # 类别列表
├── images/
│   ├── img_001.jpg
│   └── img_002.jpg
└── labels/
    ├── img_001.txt
    └── img_002.txt
```

### 1.2 导入到项目

使用项目提供的数据管理工具：

```bash
# 将导出的数据放到 data/X-AnyLabeling/ 目录
# 然后运行智能导入工具
uv run python data/xanylabeling_organizer.py
```

选择 `[3] 智能导入` 会自动处理数据并更新配置。

---

## 2. 文件说明

### 2.1 classes.txt — 类别名称列表

**作用**：定义所有精灵类别，按顺序编号（从 0 开始）。

**格式**：每行一个类别名，行号即 class_id。

**示例** (`data/classes.txt`)：
```
奇丽族群-奇丽草
奇丽族群-奇丽草-污染
恶魔狼家族-恶魔狼
电击小子家族
```

**说明**：
| class_id | 类别名 |
|----------|--------|
| 0 | 奇丽族群-奇丽草 |
| 1 | 奇丽族群-奇丽草-污染 |
| 2 | 恶魔狼家族-恶魔狼 |
| 3 | 电击小子家族 |

**注意事项**：
- 类别名可以使用中文
- 添加新类别时，在末尾追加即可，不要删除已有类别（否则会导致已有标注的 class_id 错位）
- 如果要删除类别，需要同步修改所有标注文件

### 2.2 标注文件 (.txt)

**作用**：每张图片对应一个 `.txt` 文件，记录标注框信息。

**格式**：每行一个目标，格式为：
```
class_id x_center y_center width height
```

- `class_id`：类别 ID（对应 classes.txt 的行号）
- `x_center, y_center`：框中心点坐标（归一化 0~1）
- `width, height`：框宽高（归一化 0~1）

**示例** (`img_001.txt`)：
```
0 0.512 0.387 0.123 0.098
1 0.750 0.600 0.100 0.080
```

表示：
- 第 1 个目标：class_id=0，中心 (51.2%, 38.7%)，尺寸 (12.3%, 9.8%)
- 第 2 个目标：class_id=1，中心 (75.0%, 60.0%)，尺寸 (10.0%, 8.0%)

---

## 3. dataset.yaml — 训练配置文件

**作用**：告诉 YOLO 训练脚本在哪里找数据、有哪些类别。

### 3.1 配置示例

```yaml
# YOLOv8 数据集配置
# train/val 按真实文件夹结构
# names 按 classes.txt 顺序，class_id 即索引

path: .

train:
  - images/奇丽家族
  - images/恶魔狼家族

val:
  - images/奇丽家族
  - images/恶魔狼家族

nc: 3

names:
  0: 奇丽族群-奇丽草
  1: 奇丽族群-奇丽草-污染
  2: 恶魔狼家族-恶魔狼
```

### 3.2 字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| `path` | 数据集根目录（相对于 yaml 文件位置） | `.` |
| `train` | 训练集图片路径列表 | `images/奇丽家族` |
| `val` | 验证集图片路径列表 | `images/奇丽家族` |
| `nc` | 类别总数（必须与 classes.txt 一致） | `3` |
| `names` | 类别名称映射（key 从 0 开始） | `0: 奇丽族群-奇丽草` |

### 3.3 关键规则

1. **路径相对性**：`train/val` 的路径相对于 `path` 字段
2. **自动划分**：YOLO 会自动从 `train` 路径中划分 10% 作为验证集，所以 `val` 可以与 `train` 相同
3. **names 必须对应**：`names` 中的 key 必须与 `classes.txt` 的行号一一对应
4. **nc 必须准确**：`nc` 必须等于 `classes.txt` 的行数

### 3.4 目录结构

```
data/
├── dataset.yaml          # 训练配置文件
├── classes.txt           # 类别名称列表
├── images/               # 图片目录
│   ├── 奇丽家族/         # 文件夹名任意，只用于组织图片
│   │   ├── img_001.jpg
│   │   └── img_002.jpg
│   └── 恶魔狼家族/
│       ├── img_001.jpg
│       └── img_002.jpg
└── labels/               # 标注目录（与 images 同结构）
    ├── 奇丽家族/
    │   ├── img_001.txt
    │   └── img_002.txt
    └── 恶魔狼家族/
        ├── img_001.txt
        └── img_002.txt
```

**重要**：`labels/` 目录结构必须与 `images/` 完全一致，且文件名对应。

---

## 4. 训练命令

### 4.1 一键训练（推荐）

```bash
# 使用默认参数训练（GPU + 1280 分辨率 + 100 轮）
uv run python tools/train.py --epochs 100
```

### 4.2 自定义参数训练

```bash
# 指定所有参数
uv run python tools/train.py \
    --data data/dataset.yaml \
    --model yolov8n.pt \
    --epochs 100 \
    --imgsz 1280 \
    --batch 16 \
    --name luoke_pet \
    --device 0
```

### 4.3 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--data` | `data/dataset.yaml` | 数据集配置文件路径 |
| `--model` | `yolov8n.pt` | 基础模型（位于 `models/base/`） |
| `--epochs` | `100` | 训练轮数 |
| `--imgsz` | `1280` | 输入图像尺寸（长边） |
| `--batch` | `16` | 批次大小（根据 GPU 显存调整） |
| `--name` | `luoke_pet` | 训练任务名称 |
| `--device` | `0` | 设备（`cpu` 或 `0` 使用 GPU） |

### 4.4 训练输出

训练完成后，模型保存在 `models/{name}/weights/` 目录：

```
models/luoke_pet/weights/
├── best.pt   # 最佳模型（推荐使用）
└── last.pt   # 最后一轮模型
```

---

## 5. 训练后验证

### 5.1 验证模型精度

```bash
# 在验证集上评估模型
uv run yolo val model=models/luoke_pet/weights/best.pt data=data/dataset.yaml
```

### 5.2 测试模型效果

```bash
# 使用模型进行预测（可视化输出）
uv run yolo predict model=models/luoke_pet/weights/best.pt source=data/images/
```

### 5.3 在项目中使用

```bash
# 启动主程序
uv run python -m src.main --model models/luoke_pet/weights/best.pt
```

---

## 6. 常见问题

### Q1: 训练时提示 "CUDA out of memory"

**解决方案**：减小 batch size
```bash
uv run python tools/train.py --batch 8
```

### Q2: 如何添加新的精灵类别？

1. 使用 X-AnyLabeling 标注新精灵
2. 导出时确保新类别在 classes.txt 中
3. 运行数据管理工具导入：
   ```bash
   uv run python data/xanylabeling_organizer.py
   ```
4. 选择 `[3] 智能导入` 或 `[4] 添加新精灵`
5. 工具会自动更新 `dataset.yaml` 和 `classes.txt`

### Q3: 训练多少轮合适？

- **快速测试**：50 轮
- **正常训练**：100-200 轮
- **精细调优**：300+ 轮

使用 `patience=50` 参数，如果 50 轮内精度不提升会自动停止。

### Q4: 如何继续训练（Fine-tune）？

```bash
# 使用上次训练的 best.pt 继续训练
uv run python tools/train.py --model models/luoke_pet/weights/best.pt --epochs 50
```

### Q5: 图片数量建议

| 类别 | 最少 | 推荐 | 理想 |
|------|------|------|------|
| 每个精灵 | 50 张 | 200 张 | 500+ 张 |

图片越多，模型泛化能力越强。

---

## 7. 完整训练流程示例

### 步骤 1：准备数据

```bash
# 1. 使用 X-AnyLabeling 标注游戏截图
# 2. 导出为 YOLO 格式
# 3. 将导出文件放到 data/X-AnyLabeling/
```

### 步骤 2：导入数据

```bash
uv run python data/xanylabeling_organizer.py
# 选择 [3] 智能导入
```

### 步骤 3：检查配置

```bash
# 查看当前配置
uv run python data/xanylabeling_organizer.py
# 选择 [8] 显示当前配置
```

### 步骤 4：开始训练

```bash
# 一键训练
uv run python tools/train.py --epochs 100
```

### 步骤 5：验证结果

```bash
# 验证精度
uv run yolo val model=models/luoke_pet/weights/best.pt data=data/dataset.yaml

# 可视化测试
uv run yolo predict model=models/luoke_pet/weights/best.pt source=data/images/
```

### 步骤 6：使用模型

```bash
# 启动主程序
uv run python -m src.main --model models/luoke_pet/weights/best.pt
```

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [README.md](README.md) | 项目整体说明 |
| [data/README.md](data/README.md) | 数据集格式与标注规范 |
| [tools/README.md](tools/README.md) | 工具脚本说明 |