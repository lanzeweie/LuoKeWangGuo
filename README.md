# 洛克王国 — 半自动精灵捕捉工具

专注于一件事：用户走到精灵刷新点，工具自动完成小范围内的精灵识别、靠近、瞄准、投掷。

## 核心定位

> **半自动** — 用户负责"走到哪只精灵面前"，工具负责"在精灵旁边完成靠近、瞄准、投掷"。
> 不做自动寻路，不做大范围移动，不做批量捕捉。

## 架构设计

```
src/
├── main.py                          # 主入口 — 组装 AppContext + 启动循环
├── logger.py                        # 日志
├── config.py                        # 配置管理
│
├── core/                            # 能力层 — 底层工具库
│   ├── context.py                  # AppContext — 黑板模式，共享运行时上下文
│   ├── state_machine.py            # 状态机 — 状态跳转 + 策略调度
│   ├── game_logic.py               # 游戏逻辑计算
│   └── capabilities/               # 核心能力
│       ├── detection.py            # YOLO 推理
│       ├── screen_cap.py           # DX12 截屏
│       ├── window_mgr.py           # 窗口管理
│       ├── sendinput_sim.py        # SendInput 键鼠模拟（反检测）
│       ├── input_sim.py            # 输入模拟
│       ├── target_scoring.py       # 目标评分
│       ├── target_verifier.py      # 目标验证（多周期确认）
│       ├── capture_mode_detector.py # CV: 精灵球界面识别
│       ├── battle_mode_detector.py  # CV: 战斗界面识别
│       ├── layered_overlay.py      # DWM 透明覆盖层
│       ├── gdi_overlay.py          # GDI 覆盖层（备用）
│       └── template_loader.py      # 模板配置加载
│
├── actions/                         # 行动层 — 高级动作组合
│   ├── move_controller.py          # WASD 移动执行
│   ├── aim_and_throw.py            # 瞄准 + 投掷执行
│   └── battle_exit.py              # ESC 退出战斗
│
├── strategies/                      # 策略层 — 业务决策
│   ├── base.py                     # Action 枚举 + BaseStrategy 抽象类
│   ├── search_strategy.py          # 搜索策略 — 屏幕怎么移、怎么找精灵
│   ├── navigation_strategy.py      # 导航策略 — WASD 怎么靠近
│   └── aim_strategy.py             # 瞄准策略 — 鼠标怎么瞄准
│
├── utils/                           # 工具函数 — 纯数学计算
│   └── math_utils.py               # 距离、角度、面积
│
├── tools/                           # 工具模块（GUI / 调试）
│   ├── template_captor.py          # 模板截取工具
│   └── annotate_roi.py             # ROI 标注工具
│
└── components/                      # UI 组件层
    └── coordinate_picker.py        # 相对坐标选择器 GUI
```

### 分层职责

| 层 | 职责 | 示例 |
|----|------|------|
| **策略层** `strategies/` | 业务决策 —"怎么做" | WASD 走哪边、鼠标怎么瞄、屏幕怎么扫 |
| **行动层** `actions/` | 高级动作 —"执行什么" | WASD 移动、瞄准投掷、ESC 退出 |
| **能力层** `core/capabilities/` | 底层能力 —"能做什么" | 检测、截屏、CV 识别、目标评分 |
| **工具层** `utils/` | 纯函数 — 数学计算 | 距离、角度、面积 |
| **主入口** `main.py` | 组装 + 循环 + 渲染 | 创建 AppContext，驱动主循环 |

### 调用关系

```
main.py (AppContext + 主循环)
  ▼
state_machine.py (状态跳转 + 策略调度)
  ├── strategies/*.py (返回 Action)
  └── actions/*.py (执行 Action)
       ↓
  core/capabilities/*.py (底层能力)
```

## 状态流转

```
SEARCH → VERIFY → NAVIGATE(可选) → AIM_AND_THROW → WAIT_RESULT
                                                    ├── 精灵消失 → COOLDOWN → SEARCH
                                                    ├── 触发战斗 → BATTLE_STATE → COOLDOWN → SEARCH
                                                    └── 精灵还在 → 继续投掷
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.9+ |
| 检测 | Ultralytics YOLOv8n |
| 截屏 | dxcam (DirectX12) |
| 输入 | Windows SendInput API |
| CV | OpenCV 模板匹配 |
| 包管理 | uv |
| 平台 | Windows 10/11 |

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 运行主程序

> **必须以管理员身份运行终端**，否则 SendInput 操作会被 UAC 拦截。

```bash
uv run python -m src.main --model models/trained/luoke_pet.pt
```

### 3. 常用命令

```bash
# 模型验证
uv run yolo val model=models/trained/luoke_pet.pt data=data/dataset.yaml

# 窗口诊断（排查窗口和截图问题）
uv run python -m src.tools.diagnose_window

# 模板截取（获取 CV 模板）
uv run python -m src.tools.template_captor --capture
uv run python -m src.tools.template_captor --battle

# SendInput 测试
uv run python -m src.core.capabilities.sendinput_sim --real-test
```

## 模型性能

- **训练数据**: 64 张标注图片
- **mAP50**: 99.5% | **mAP50-95**: 92%
- **推理速度**: ~2.6ms/frame (RTX 3060 Ti)
- **模型路径**: `models/trained/luoke_pet.pt`

## 核心原则

1. **纯视觉方案** — 不注入游戏内存，反作弊优先
2. **客户区坐标** — 所有操作坐标相对于窗口客户区
3. **SendInput 反检测** — 分段轨迹 + 随机抖动 + 80-150ms 随机延迟
4. **暴力捕捉** — 不判断捕捉成功/失败，精灵消失即结束
5. **禁止硬编码坐标** — 所有坐标通过 `RelativeCoordinatePicker` 获取，存为相对坐标

## 开发进度

| 阶段 | 状态 | 详情 |
|------|------|------|
| 1. 环境搭建 | ✅ 完成 | uv、依赖、数据集 |
| 2. 模型训练 | ✅ 完成 | mAP50=99.5% |
| 3. 核心模块 | ✅ 完成 | 检测/截屏/移动/投掷/CV/战斗退出 |
| 4. 架构重构 | ✅ 完成 | 三层架构：能力层/行动层/策略层 |
| 5. 策略层 | ✅ 完成 | AppContext + 搜索/导航/瞄准策略 (590 行) |
| 6. 整合测试 | ⏳ 待开始 | 状态机整合 + 端到端流程验证 |

详细计划见 [docs/implementation_plan.md](docs/implementation_plan.md)

## 重要文件

| 文件 | 路径 |
|------|------|
| 训练模型 | `models/trained/luoke_pet.pt` |
| 实现计划 | `docs/implementation_plan.md` |
| 项目上下文 | `.claude/CLAUDE.md` |
| CV 模板目录 | `data/templates/` |
| 统一配置文件 | `data/templates/templates_config.json` |
