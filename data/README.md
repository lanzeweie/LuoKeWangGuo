# 洛克王国 YOLO 数据集格式说明

## 目录结构

```
data/
├── dataset.yaml                    # 主配置文件（核心）
├── classes.txt                     # 类别名称列表
│
├── images/                         # 图片目录
│   └── [精灵类型]/                 # 每个精灵类型一个文件夹
│       ├── img_001.jpg
│       ├── img_002.jpg
│       └── ... (3000+ 张)
│
├── labels/                         # 标注文件目录（与 images 同结构）
│   └── [精灵类型]/
│       ├── img_001.txt
│       ├── img_002.txt
│       └── ...
│
└── templates/                      # CV 模板匹配（独立体系，不与 YOLO 混用）
    └── templates_config.json
```

---

## 当前结构（奇丽草族群 - 奇丽草）

```
data/
├── dataset.yaml                    # 指向 images/奇丽草族群 - 奇丽草
├── images/
│   └── 奇丽草族群 - 奇丽草/        # ← 64 张图片
│       ├── PixPin_2026-04-08_20-19-32.png
│       └── ...
└── labels/
    └── 奇丽草族群 - 奇丽草/        # ← 64 个标注文件
        ├── PixPin_2026-04-08_20-19-32.txt
        └── ...
```

---

## `dataset.yaml` 配置说明

```yaml
# YOLOv8 数据集配置 - 按精灵类型分文件夹
# 新增精灵时：在 images/ 和 labels/ 下创建新文件夹，并更新此文件

path: .                       # 数据集根目录
train: images/奇丽草族群 - 奇丽草   # 训练集路径
val: images/奇丽草族群 - 奇丽草     # 验证集路径

nc: 1                         # 类别总数
names:
  0: 奇丽族群-奇丽草          # class_id → 类别名称
```

---

## 新增精灵类型的步骤

假设要添加"利牙鼠族群 - 利牙鼠"：

### 1. 收集数据
- 拍摄或截取 **3000+ 张图片**
- 使用 LabelMe 或其他工具标注为 **YOLO 格式**

### 2. 存放数据
```bash
# 创建文件夹结构
mkdir -p data/images/利牙鼠族群 - 利牙鼠
mkdir -p data/labels/利牙鼠族群 - 利牙鼠

# 复制图片和标注到对应文件夹
cp new_sprite_*.png data/images/利牙鼠族群 - 利牙鼠/
cp new_sprite_*.txt data/labels/利牙鼠族群 - 利牙鼠/
```

### 3. 更新 `dataset.yaml`

```yaml
path: .
train: 
  - images/奇丽草族群 - 奇丽草  # 原有精灵
  - images/利牙鼠族群 - 利牙鼠  # 新增精灵
val:
  - images/奇丽草族群 - 奇丽草
  - images/利牙鼠族群 - 利牙鼠

nc: 2                         # 更新类别总数
names:
  0: 奇丽族群-奇丽草
  1: 利牙族群 - 利牙鼠        # 新增类别
```

### 4. 重新训练
```bash
uv run yolo train model=models/base/yolov8n.pt data=data/dataset.yaml epochs=100
```

---

## YOLO 标注文件格式

每个 `.txt` 文件对应一张图片，格式为：

```
class_id x_center y_center width height
```

- **class_id**: 整数，从 0 开始（对应 `dataset.yaml` 中的 names）
- **x_center, y_center, width, height**: 均为 **归一化值 (0~1)**

### 示例

图片 `img_001.png` 的标注文件 `img_001.txt`：

```
0 0.512 0.387 0.123 0.098
```

表示：
- 类别 ID = 0（奇丽族群 - 奇丽草）
- 框中心点 = (51.2%, 38.7%)
- 框宽高 = (12.3%, 9.8%)

---

## 命名规范建议

| 元素 | 命名规则 | 示例 |
|------|---------|------|
| 精灵文件夹 | `[族群名]-[精灵名]` | `奇丽草族群 - 奇丽草` |
| 图片文件 | 任意（建议带日期/顺序号） | `20260415_img001.png` |
| 标注文件 | 与图片同名 `.txt` | `20260415_img001.txt` |
| 类别名称 | `族群 - 精灵` | `奇丽族群 - 奇丽草` |

---

## 已有工具脚本

| 脚本 | 用途 | 用法 |
|------|------|------|
| `update_dataset_config.py` | 自动生成 `dataset.yaml` | `python data/update_dataset_config.py` |
| `reorganize_data.py` | 旧数据结构迁移 | 已执行过，无需再次运行 |

---

## 常见问题

### Q1: 每个精灵需要多少图片？
**推荐**: 最少 1000 张，理想 3000+ 张。太少会导致欠拟合。

### Q2: 验证集需要单独准备吗？
不需要。YOLO 会自动从 `train` 路径中划分 10% 作为验证集。如需自定义划分比例，可修改训练命令：
```bash
uv run yolo train data=data/dataset.yaml epochs=100 val_split=0.15
```

### Q3: 不同精灵的图片尺寸可以不一致吗？
可以。YOLO 会在训练时自动 resize 到统一尺寸（默认 640x640）。

### Q4: 可以用 OBB（旋转框）格式吗？
当前项目使用 **HBB（横向矩形框）** 足够。精灵是自由移动的，不需要精确角度信息。如需旋转框，需修改标注脚本和训练配置。
