# 项目概览

## 项目信息

| 属性 | 值 |
|------|-----|
| **项目名称** | LuokeWangGuo (洛克王国半自动精灵捕捉工具) |
| **项目类型** | 单体应用 (Monolith) |
| **编程语言** | Python 3.9+ |
| **许可证** | MIT |
| **版本** | 0.1.0 |

## 项目描述

洛克王国半自动指定精灵捕捉工具。专注于一件事：用户走到精灵刷新点，工具自动完成小范围内的精灵识别、靠近、瞄准、投掷。

> **核心定位**：半自动 — 用户负责"走到哪只精灵面前"，工具负责"在精灵旁边完成靠近、瞄准、投掷"。

**限制范围**：
- 不做自动寻路
- 不做大范围移动
- 不做批量捕捉

## 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | >=3.9 |
| AI/ML | Ultralytics YOLOv8n | >=8.2.0 |
| 截屏 | dxcam (DirectX12) | >=0.0.5 |
| CV | OpenCV | >=4.9.0 |
| 输入 | pywin32 (SendInput) | >=306 |
| 数值计算 | numpy | >=1.24.0 |
| 图像处理 | Pillow | >=10.0.0 |
| 配置 | pyyaml | >=6.0 |
| 包管理 | uv | - |

## 架构模式

### 分层架构

```
src/
├── main.py           # 主入口 + 主循环
├── config.py         # 配置管理
├── logger.py         # 日志
│
├── core/             # 核心能力层
│   ├── state_machine.py
│   ├── game_logic.py
│   └── capabilities/  # 底层能力
│       ├── detection.py        # YOLO 推理
│       ├── screen_cap.py       # DX12 截屏
│       ├── window_mgr.py       # 窗口管理
│       ├── sendinput_sim.py    # SendInput 键鼠模拟
│       ├── target_scoring.py   # 目标评分
│       ├── target_verifier.py  # 目标验证
│       ├── capture_mode_detector.py   # CV: 精灵球界面
│       ├── battle_mode_detector.py    # CV: 战斗界面
│       ├── layered_overlay.py # DWM 透明覆盖层
│       └── ...
│
├── actions/           # 行动层
│   ├── move_controller.py     # WASD 移动
│   ├── aim_and_throw.py       # 瞄准 + 投掷
│   └── battle_exit.py         # 退出战斗
│
├── strategies/        # 策略层 (待实现)
│
├── utils/            # 工具函数 (待实现)
│
├── tools/            # 调试工具
│   └── template_captor.py
│
└── components/       # UI 组件
    └── coordinate_picker.py
```

### 状态流转

```
SEARCH → VERIFY → NAVIGATE(可选) → AIM_AND_THROW → WAIT_RESULT
                                                    ├── 精灵消失 → COOLDOWN → SEARCH
                                                    ├── 触发战斗 → BATTLE_STATE → COOLDOWN → SEARCH
                                                    └── 精灵还在 → 继续投掷
```

## 开发进度

| 阶段 | 状态 | 详情 |
|------|------|------|
| 1. 环境搭建 | ✅ 完成 | uv、依赖、数据集 |
| 2. 模型训练 | ✅ 完成 | mAP50=99.5% |
| 3. 核心模块 | ✅ 完成 | 检测/截屏/移动/投掷/CV/战斗退出 |
| 4. 架构重构 | ✅ 完成 | 三层架构：能力层/行动层/策略层 |
| 5. 策略层 | ⏳ 进行中 | AppContext + 搜索/导航/瞄准策略 |
| 6. 整合测试 | ⏳ 待开始 | 端到端流程验证 |

**当前 Story**: Epic 1 Story 1 - Enhanced Capture Logic with Distance Judgment and Target Verification

## 模型性能

- **训练数据**: 64 张标注图片
- **mAP50**: 99.5%
- **mAP50-95**: 92%
- **精度**: 99.8%
- **召回率**: 100%
- **推理速度**: ~2.6ms/frame (RTX 3060 Ti)
- **模型路径**: `models/trained/luoke_pet.pt`

## 核心原则

1. **纯视觉方案** — 不注入游戏内存，反作弊优先
2. **客户区坐标** — 所有操作坐标相对于窗口客户区
3. **SendInput 反检测** — 分段轨迹 + 随机抖动 + 80-150ms 随机延迟
4. **禁止硬编码坐标** — 所有坐标通过 `RelativeCoordinatePicker` 获取

## 快速开始

```bash
# 安装依赖
uv sync

# 运行主程序 (需管理员权限)
uv run python -m src.main --model models/trained/luoke_pet.pt
```

## 重要文件

| 文件 | 路径 |
|------|------|
| 训练模型 | `models/trained/luoke_pet.pt` |
| 实现计划 | `docs/implementation_plan.md` |
| 项目上下文 | `.claude/CLAUDE.md` |
| CV 模板目录 | `data/templates/` |
| 统一配置文件 | `data/templates/templates_config.json` |

## 已知限制

- 需要 DirectX12 兼容 GPU 进行截屏
- 必须以管理员身份运行（SendInput 需要）
- 游戏窗口：`NRC-Win64-Shipping.exe`
- 客户区分辨率：1280x720