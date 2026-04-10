# 洛克王国自动捕捉 — 实现计划

> 本文档定义开发的完整架构与模块计划。已完成的模块保留为参考，不再作为待办。

**最后更新**: 2026-04-10

---

## 架构总览

### 分层设计

```
src/
├── main.py                          # 主入口 — 组装 + 启动循环 + AppContext
├── logger.py                        # 日志
├── config.py                        # 配置管理
│
├── core/                            # 能力层 — 底层工具库
│   ├── context.py                  # AppContext — 共享运行时上下文（黑板模式）
│   ├── state_machine.py            # 状态机 — 状态跳转 + 调用策略
│   ├── game_logic.py               # 游戏逻辑计算
│   └── capabilities/               # 核心能力
│       ├── detection.py            # YOLO 推理
│       ├── screen_cap.py           # DX12 截屏
│       ├── window_mgr.py           # 窗口管理
│       ├── sendinput_sim.py        # SendInput 键鼠模拟
│       ├── input_sim.py            # 输入模拟
│       ├── target_scoring.py       # 目标评分
│       ├── target_verifier.py      # 目标验证（多周期确认）
│       ├── layered_overlay.py      # DWM 透明覆盖层
│       ├── gdi_overlay.py          # GDI 覆盖层（备用）
│       └── template_loader.py      # 模板配置加载
│
├── detectors/                       # CV 模板检测器
│   ├── capture_mode_detector.py    # 精灵球捕捉界面检测（Canny 边缘）
│   ├── battle_mode_detector.py     # 战斗界面检测（Canny 边缘）
│   └── battle_exit_confirm_detector.py  # 战斗逃跑确认框检测（灰度匹配）
│
├── actions/                         # 行动层 — 高级动作组合
│   ├── move_controller.py          # WASD 移动执行
│   ├── aim_and_throw.py            # 瞄准 + 投掷执行
│   └── battle_exit.py              # ESC 退出战斗
│
├── strategies/                      # 策略层
│   ├── base.py                     # 策略基类 + Action 枚举
│   ├── search_strategy.py          # 搜索策略 — 屏幕怎么移、怎么找精灵
│   ├── navigation_strategy.py      # 导航策略 — WASD 怎么靠近
│   └── aim_strategy.py             # 瞄准策略 — 鼠标怎么瞄准
│
├── utils/                           # 工具函数
│   └── math_utils.py               # 纯数学计算（距离、角度、缩放）
│
├── tools/                           # 工具模块（GUI / 调试）
│   ├── template_captor.py          # 模板截取工具
│   └── annotate_roi.py             # ROI 标注工具
│
└── components/                      # ★ UI 组件层
    └── coordinate_picker.py        # 相对坐标选择器 GUI
```

### 调用关系

```
main.py
  │ 创建 AppContext(config, logger, window_info, ...)
  │ 组装所有组件，注入 context
  │ 主循环: capture → detect → score → state_machine.step()
  │ 渲染 overlay
  ▼
state_machine.py          ← 只管"当前是什么状态，切换到哪个策略"
  │
  ├── 读取 context 中的共享数据（目标、检测结果、游戏状态）
  ├── 调用 current_strategy.execute(context)  → 返回 Action
  │
  └── 根据 Action 调用执行模块
       ├── actions/move_controller   (WASD)
       ├── actions/aim_and_throw     (鼠标 + 投掷)
       ├── actions/battle_exit       (ESC)
       └── capabilities/detection    (YOLO)
```

### 核心原则

> **半自动定位** — 用户走到精灵刷新点，工具自动完成小范围内的识别、靠近、瞄准、投掷。不做自动寻路，不做大范围移动。
> **按 E 进入捕捉** — 只有在精灵球界面下才能执行捕捉。没有精灵球界面时绝不按鼠标。
> **暴力捕捉** — 不判定是否抓到精灵。投掷后持续检测，直到精灵不再被识别为止。
> **策略无状态** — 策略本身不保存状态，状态由 StateMachine 管理。
> **坐标基于客户区** — 所有鼠标/键盘操作的坐标都是相对于窗口客户区的。
> **Blackboard 模式** — 各模块通过 AppContext 读写共享数据，避免函数参数过长。

---

## AppContext（黑板模式）

### 设计目的

各模块（策略、检测、执行）需要共享实时数据，但互相不依赖。通过一个 `AppContext` 对象集中管理：

```python
@dataclass
class AppContext:
    # 配置与基础设施
    config: dict                    # 所有配置参数
    logger: logging.Logger          # 日志实例

    # 窗口与屏幕
    window_handle: int | None       # 游戏窗口句柄
    window_region: tuple            # 客户区 (x, y, w, h)

    # 实时检测数据（每帧更新）
    current_frame: np.ndarray | None  # 最新帧
    detections: list                 # YOLO 检测结果
    verified_target: object | None   # 已验证的目标
    throw_count: int                 # 当前投掷次数

    # 游戏状态（CV 判断）
    is_capture_mode: bool            # 精灵球界面
    is_battle_mode: bool             # 战斗界面

    # 状态机
    current_state: str               # 当前状态名
```

### 使用方式

- **main.py** 创建 context，每帧更新 `current_frame`、`detections` 等
- **state_machine** 读取 context 中的目标数据，调用策略
- **策略** 从 context 读取数据，返回 Action
- **执行模块** 从 context 读取窗口信息，执行操作并更新 context

### 优势

- 新增模块不需要修改已有函数的签名
- 避免 `func(a, b, c, d, e, f, g)` 式的超长参数
- 策略可以按需读取自己关心的字段

---

## 工具函数分层

### `utils/math_utils.py` — 纯数学计算

从 `game_logic.py` 中提取的纯数学函数，不依赖任何游戏逻辑：

```python
def distance(p1: tuple, p2: tuple) -> float
def center_offset(point: tuple, screen_w: int, screen_h: int) -> tuple
def bbox_area(x1: int, y1: int, x2: int, y2: int) -> float
def angle_between(p1: tuple, p2: tuple) -> float
```

### `game_logic.py` — 保留游戏业务判断

`game_logic.py` 中的游戏特定逻辑（如判断可投掷距离、选择精灵球类型）保留在 `core/` 下，或者未来迁移到策略层。

---

## 状态机总览

### 状态流转

```
用户走到精灵刷新点 → 启动工具
        │
        ▼
  SEARCH（搜索目标）
        │
        ├─ 检测到目标 → VERIFY
        │                  ↓ N 个周期连续确认
        │               通过 → 距离判断
        │                         │
        │                         ├─ FAR → NAVIGATE（WASD 靠近）→ SEARCH
        │                         └─ CLOSE → 【检测精灵球界面】
        │                                       │
        │                                       ├─ 没有 → 按 E → AIM_AND_THROW
        │                                       └─ 已有 → 直接 AIM_AND_THROW
        │                                              ↓ 投掷完成
        │                                          WAIT_RESULT
        │                                              │
        │                                              ├─ 精灵消失 → COOLDOWN → SEARCH
        │                                              ├─ 触发战斗 → BATTLE_STATE → COOLDOWN → SEARCH
        │                                              └─ 精灵还在 → 继续投掷（暴力策略）
        │
        └─ 画面没精灵 → SEARCH_PAN（小范围平移搜索）

  BATTLE_STATE（检测到进入战斗界面）
        ↓ 按 ESC → 点击确认按钮 → CV 确认战斗界面消失
  COOLDOWN → 回到 SEARCH
```

### 状态定义

| 状态 | 描述 | 进入条件 | 退出条件 |
|------|------|---------|---------|
| SEARCH | 搜索画面中的精灵 | 初始状态 / COOLDOWN 结束 | 画面检测到精灵 |
| VERIFY | 验证目标稳定性 | 检测到精灵 | N 个周期连续确认通过 |
| NAVIGATE | WASD 靠近目标 | 验证通过，距离较远 | 进入可投掷范围 |
| AIM_AND_THROW | 瞄准 + 按住 + 松开 | 精灵球界面已确认 | 投掷动作完成 |
| WAIT_RESULT | 等待投掷结果 | 投掷完成 | 精灵消失 / 战斗 / 继续投掷 |
| BATTLE_STATE | 处理战斗 | 检测到战斗界面 | ESC + 点击确认 → 退出成功 |
| COOLDOWN | 冷却 | 捕捉成功 / 战斗退出 | 冷却结束 → SEARCH |
| ERROR | 异常恢复 | 超时 / 连续失败 | 恢复 SEARCH |

> **ROTATE 状态已移除** — 改为小范围平移搜索（SEARCH_PAN），不做 360° 旋转。
> **PENDING_CAPTURE 状态已移除** — 合并到 WAIT_RESULT，暴力策略不区分中间状态。

---

## 策略层设计

### `strategies/base.py` — 协议定义

```python
from enum import Enum, auto
from abc import ABC, abstractmethod

class Action(Enum):
    NO_OP = auto()            # 什么都不做
    SEARCH_PAN = auto()       # 平移搜索（鼠标微调方向）
    MOVE_WASD = auto()        # WASD 移动（方向 + 时长）
    AIM = auto()              # 瞄准（目标位置）
    THROW = auto()            # 投掷（直接触发）
    ESCAPE = auto()           # ESC 退出战斗

class BaseStrategy(ABC):
    @abstractmethod
    def execute(self, ctx: AppContext) -> Action:
        """读取 ctx，返回要执行的 Action"""
        ...
```

### 策略接口标准

每个策略实现 `execute(ctx) -> Action`：
- 从 `ctx` 读取需要的数据
- 不做状态管理（那是 state_machine 的职责）
- 不直接执行操作（返回 Action，由 state_machine 调度）

### `strategies/search_strategy.py` — 搜索策略（~80 行）

**职责**：画面中没精灵时，决定屏幕怎么移动来寻找精灵。

**逻辑**：
- 当前帧没检测到精灵 → 决定小幅平移鼠标方向（左/右交替）
- 每次平移固定角度（如 5°），不做大范围移动
- 检测到精灵 → 返回 `Action.NO_OP`，交给验证层

### `strategies/navigation_strategy.py` — 导航策略（~100 行）

**职责**：WASD 怎么走近精灵。

**逻辑**：
- 根据目标在屏幕中的偏移量决定 WASD 方向
- 分两阶段：远距离快速靠近 → 近距离精细调整
- 目标在 `CENTER_TOLERANCE`（150px）范围内 → 返回 `Action.NO_OP`

### `strategies/aim_strategy.py` — 瞄准策略（~60 行）

**职责**：鼠标怎么瞄准精灵中心并投掷。

**逻辑**：
- 计算目标中心到屏幕中心的偏移量
- 返回 `Action.THROW`，由 state_machine 调用 `aim_and_throw()`

---

## 暴力捕捉逻辑

```python
# WAIT_RESULT 状态中的逻辑
def handle_wait_result(ctx):
    """暴力策略：投掷后持续检测，精灵消失就认为结束"""
    if no_pet_detected(ctx.detections):
        # 精灵消失了 = 抓到了或者跑了，不区分
        return State.COOLDOWN

    if ctx.is_battle_mode:
        return State.BATTLE_STATE

    # 精灵还在 + 没战斗 → 继续投掷
    if ctx.throw_count < MAX_THROWS:
        return State.AIM_AND_THROW

    return State.COOLDOWN
```

**不做**：判断精灵球动画、判断捕捉成功/失败、等待特定的 UI 变化。
**只做**：投掷 → 检测精灵是否还在 → 不在就停，在就继续投。

---

## 状态机与策略的关系

采用 **"状态机驱动策略"** 模式：

| 层级 | 职责 | 方法 |
|------|------|------|
| StateMachine | 状态跳转 | `step()` → 判断条件 → 切换 `current_strategy` |
| Strategy | 该状态下的行为序列 | `execute(ctx)` → 返回 Action |
| Core 模块 | 具体执行 | `move_controller.move()`, `aim_and_throw.execute()` |

```python
# 伪代码
class StateMachine:
    def step(self, ctx: AppContext):
        # 1. 检查是否需要切换状态
        if self._should_transition(ctx):
            self.current_state = self._next_state(ctx)
            self.current_strategy = self._get_strategy(self.current_state)

        # 2. 执行当前策略
        action = self.current_strategy.execute(ctx)

        # 3. 根据 Action 调度执行
        self._dispatch(action, ctx)
```

---

## 已完成模块（参考文档）

> 以下模块已实现，保留为设计参考，不再作为待办。

### 目标验证（target_verifier.py）
- 检测间隔轮询（默认 2s/次）
- 多周期连续确认（默认 3 次）
- 多目标优先级排序（距屏幕中心最近优先）
- 基于 bbox 面积的距离判断（FAR/MEDIUM/CLOSE）

### WASD 移动（move_controller.py）
- 根据目标偏移决定 WASD 方向
- 按住 200-500ms（随机），间隔 300-800ms
- 停止条件：目标中心 ±150px 或超时 15s

### SendInput 输入（sendinput_sim.py）
- 键盘：SendInput 发送按键
- 鼠标：分段轨迹 + 随机抖动
- 反检测：80-150ms 随机延迟

### CV 模板检测（capture_mode_detector.py / battle_mode_detector.py）
- `cv2.matchTemplate` 模板匹配
- 动态 ROI 加载（相对坐标配置）

### 战斗退出（battle_exit.py）
- ESC → 等待 → 点击确认按钮 → CV 确认消失
- 最多重试 3 次

### 瞄准与投掷（aim_and_throw.py）
- 分段鼠标移动 + 按住微调 + 松开投掷
- 安全校验：精灵球界面存在时才执行

### 工具模块
- 相对坐标选择器 GUI
- 模板截取工具
- ROI 标注工具

---

## 实施进度

### ✅ 阶段一：基础设施（已完成）

| 步骤 | 模块 | 文件 | 实际行数 | 状态 |
|------|------|------|---------|------|
| 1 | AppContext | `src/core/context.py` | 70 | ✅ 完成 |
| 2 | 数学工具 | `src/utils/math_utils.py` | 95 | ✅ 完成 |

### ✅ 阶段二：策略层（已完成）

| 步骤 | 模块 | 文件 | 实际行数 | 状态 |
|------|------|------|---------|------|
| 3 | 策略协议 | `src/strategies/base.py` | 50 | ✅ 完成 |
| 4 | 搜索策略 | `src/strategies/search_strategy.py` | 95 | ✅ 完成 |
| 5 | 导航策略 | `src/strategies/navigation_strategy.py` | 165 | ✅ 完成 |
| 6 | 瞄准策略 | `src/strategies/aim_strategy.py` | 115 | ✅ 完成 |

**总计**: 590 行代码，所有模块已测试通过。详见 `docs/strategy_implementation_summary.md`

### ⏳ 阶段三：状态机整合（待开始）

| 步骤 | 模块 | 文件 | 说明 |
|------|------|------|------|
| 7 | 状态机重构 | `src/core/state_machine.py` | 改为"状态机驱动策略"模式 |
| 8 | 暴力捕捉 | `src/core/state_machine.py` | WAIT_RESULT 整合暴力策略 |
| 9 | main.py 注入 | `src/main.py` | 创建 AppContext，注入各组件 |

### 阶段四：测试验证

| 步骤 | 内容 | 说明 |
|------|------|------|
| 10 | 分块测试 | 搜索 / 导航 / 瞄准 各独立测试 |
| 11 | 端到端测试 | 完整半自动捕捉流程 |

---

## 已移除/废弃的内容

| 内容 | 原因 |
|------|------|
| ROTATE 状态（360° 旋转搜索） | 改为小范围平移搜索 |
| PENDING_CAPTURE 状态 | 合并到 WAIT_RESULT |
| ENTER_CAPTURE 状态 | 合并到 AIM_AND_THROW，按 E 和检测界面作为前置步骤 |
| 复杂的捕捉成功/失败判断 | 改为暴力策略：精灵消失即结束 |
| `game_logic.py` 中的纯数学函数 | 迁移到 `utils/math_utils.py` |

---

## 需要你提供

| 资源 | 用途 | 路径 | 获取方式 |
|------|------|------|----------|
| 精灵球捕捉界面截图 | CV 模板匹配 | `data/templates/capture_mode.png` | `uv run python -m src.tools.template_captor --capture` |
| 战斗界面截图 | CV 模板匹配 | `data/templates/battle_mode.png` | `uv run python -m src.tools.template_captor --battle` |
| 战斗逃跑同意框截图 | CV 模板匹配 | `data/templates/battle_exit_confirm.png` | `uv run python -m src.tools.template_captor --battle-exit` |
| 统一配置文件 | 存储所有模板 ROI 和点击坐标 | `data/templates/templates_config.json` | 由 template_captor 自动生成和更新 |
