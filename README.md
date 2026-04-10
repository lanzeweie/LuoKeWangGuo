# 洛克王国自动宠物捕捉脚本

基于纯计算机视觉的洛克王国自动宠物捕捉工具。

## 目录结构

```
LuokeWangguo/
├── src/                    # 源代码
│   ├── main.py             # 程序入口
│   ├── config.py           # 配置管理
│   ├── logger.py           # 日志模块
│   └── core/               # 核心业务模块
│       ├── window_mgr.py   # 窗口管理
│       ├── screen_cap.py   # 屏幕捕获
│       ├── detection.py    # YOLO 检测
│       ├── input_sim.py    # 输入模拟
│       ├── game_logic.py   # 游戏逻辑
│       └── state_machine.py # 状态机控制
├── tools/                  # 工具脚本
│   ├── train.py            # 训练脚本
│   ├── extract_frames.py   # 抽帧工具
│   └── prepare_dataset.py  # 数据集准备
├── data/                   # 数据目录
│   ├── images/             # 图片文件
│   ├── labels/             # 标注文件
│   └── dataset.yaml        # YOLO 数据集配置
├── models/                 # 模型文件
│   └── trained/
│       └── luoke_pet.pt    # 训练好的模型
├── docs/                   # 文档
├── tests/                  # 测试
├── pyproject.toml          # 项目配置
└── README.md               # 本文件
```

## 环境要求

- Windows 10/11
- Python 3.9+
- DirectX 12 兼容显卡
- uv 包管理器

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 训练模型

```bash
uv run python tools/train.py --data data/dataset.yaml --name luoke_pet
```

### 3. 测试模型

```bash
# 批量预测测试
uv run yolo predict model=models/trained/luoke_pet.pt source=data/images/ save=True

# 单张图片测试
uv run yolo predict model=models/trained/luoke_pet.pt source="data/images/PixPin_2026-04-08_20-19-32.png" save_dir=data/demo
```

### 4. 运行主程序

> **重要：必须以管理员身份运行终端**，否则 SendInput 键鼠操作会被 Windows UAC 拦截，游戏无任何反应。

```bash
# 以管理员身份打开 PowerShell/终端，然后执行：
uv run python -m src.main --model models/trained/luoke_pet.pt --target-class 0
```

### 键鼠操作测试

验证 SendInput 是否能正常发送（同样需要管理员权限）：

```bash
uv run python -m src.core.sendinput_sim --real-test
```

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--model` | YOLO 模型路径 (.pt 文件) | 必填 |
| `--target-class` | 目标宠物类别 ID | 0 |
| `--confidence` | 置信度阈值 | 0.5 |
| `--process-name` | 游戏进程名 | NRC-Win64-Shipping.exe |
| `--resolution` | 游戏分辨率 | 1280x720 |
| `--fps` | 目标帧率 | 60 |
| `--device` | 推理设备 (cpu 或 0) | cpu |
| `--debug` | 调试模式（显示检测框） | False |
| `--dry-run` | 试运行（不执行实际操作） | False |

## 功能特性

- 纯外部视觉方案（不注入游戏内存）
- 自动识别指定宠物（YOLOv8n）
- 60FPS 实时运行
- 自动移动和投掷
- 命令行配置

## 开发进度

| 阶段 | 状态 | 详情 |
|------|------|------|
| 1. 环境搭建 | 完成 | uv、依赖、数据集准备 |
| 2. 数据训练 | 完成 | 模型训练，mAP50=99.5% |
| 3. 核心模块 | 完成 | 6 个模块已实现并集成 |
| 4. 集成测试 | 进行中 | 端到端测试 |
| 5. 项目交付 | 待开始 | 打包和文档 |

总体进度：████████░░░░░░░░░░░░░░░░░░ 60%

## 项目说明

### 状态机流程

```
SEARCH → MOVE_TO_TARGET → THROW → WAIT → COOLDOWN → (回到 SEARCH)
```

### 反作弊合规性

- 仅使用外部视觉方案
- 输入模拟加入随机延迟
- 无内存操作

### 运行权限要求

- **必须以管理员身份运行终端** — Windows UAC 完整性机制会阻止非管理员进程向高权限进程发送 SendInput 事件
