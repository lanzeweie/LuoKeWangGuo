# 瞄准算法逻辑设计

## 概述

本文档描述洛克王国精灵捕捉场景下的瞄准算法，包括坐标转换、距离补偿、平滑处理和安全性考量。

## 与导航的关系

捕捉流程分为**两个独立阶段**，通过状态机衔接：

```
阶段1: WASD 导航（靠近精灵）           阶段2: 鼠标瞄准（投掷精灵球）
┌──────────────────────────────┐    ┌─────────────────────────────────┐
│ NavigationStrategy +          │    │ AimStrategy + AimAndThrow       │
│ MoveController               │    │                                 │
│                               │    │  输入: 鼠标移动 + 点击            │
│ 输入: 键盘 WASD               │    │  目的: 精灵球精准命中              │
│ 目的: 让精灵出现在画面中心      │    │  补偿: 抛物线下落、动量预测        │
│ 完成条件: 精灵中心 ±150px 内   │───→│                                 │
└──────────────────────────────┘    └─────────────────────────────────┘
```

- **阶段1** 由 `NavigationStrategy` 决策、`MoveController` 执行，控制角色 WASD 靠近精灵
- **阶段2** 由 `AimStrategy` 决策、`AimAndThrow` 执行，控制鼠标瞄准并投掷
- 本算法文档聚焦于**阶段2**，但阶段1的完成是阶段2的前置条件

## 三层架构

项目采用**策略决策 → 动作执行 → 底层能力**的三层架构：

| 层次 | 模块 | 职责 | 返回值 |
|------|------|------|--------|
| **策略决策** | `NavigationStrategy` | 精灵离画面中心远不远？要不要 WASD 靠近？ | `Action.MOVE_WASD` / `Action.NO_OP` |
| **策略决策** | `AimStrategy` | 精灵在画面中心了吗？在精灵球界面了吗？能投掷了吗？ | `Action.THROW` / `Action.PRESS_E` / `Action.NO_OP` |
| **动作执行** | `MoveController` | 具体按哪个 WASD 键、按多久、循环几次 | `bool`（是否已足够近） |
| **动作执行** | `AimAndThrow` | 鼠标移动到目标 → 按住 → 微调 → 松开 | `bool`（是否投掷完成） |
| **底层能力** | `InterceptionSimulator` | 驱动级输入发送（按键、鼠标移动、点击） | 事件计数 |

**关键原则**：Strategy 只返回 `Action` 枚举，不直接操作键鼠；Action 模块才真正执行，通过 `InterceptionSimulator` 发送输入。

## 代码映射

| 算法模块 | 对应文件 | 说明 |
|----------|----------|------|
| 导航策略 | `src/strategies/navigation_strategy.py` | WASD 靠近决策 |
| 导航执行 | `src/actions/move_controller.py` | WASD 按键控制 |
| 瞄准策略 | `src/strategies/aim_strategy.py` | 投掷时机决策 |
| 瞄准执行 | `src/actions/aim_and_throw.py` | 鼠标瞄准 + 投掷 |
| 驱动输入 | `src/core/capabilities/interception_sim.py` | 贝塞尔曲线 + 拟人化算法 |
| 目标评分 | `src/core/capabilities/target_scoring.py` | 距离分类 + 优先级排序 |
| 目标验证 | `src/core/capabilities/target_verifier.py` | 多帧确认目标 |

## 坐标系定义

### 游戏坐标特点

洛克王国游戏窗口分辨率为 1280x720（客户区），在捕获模式下：

- 鼠标移动采用**客户区绝对坐标**方式，即 `mouse_move_to(target_x, target_y)` 直接传入目标在 1280x720 客户区中的像素坐标
- `InterceptionSimulator.mouse_move_to()` 内部从当前鼠标位置计算偏移量，沿贝塞尔曲线分段移动至目标
- 精灵球飞行存在抛物线轨迹和重力下落

### 坐标系转换

```
YOLO 检测输出 → 计算中心 (cx, cy) → 可选距离补偿 → 传入 mouse_move_to(cx, cy)
```

| 阶段 | 数据 | 说明 |
|------|------|------|
| YOLO 输出 | (cx, cy) - 像素坐标 | 目标在 1280x720 客户区中的中心位置 |
| 距离补偿 | (cx, cy + y_compensation) | 根据距离向上补偿（负值） |
| 鼠标移动 | `mouse_move_to(aim_x, aim_y)` | 客户区绝对坐标，内部走贝塞尔曲线 |

### 鼠标移动方式

`InterceptionSimulator.mouse_move_to(rel_x, rel_y)` 内部逻辑：

1. 调用 `GetCursorPos()` 获取当前鼠标位置（屏幕绝对坐标）
2. 减去窗口左上角，转换为客户区相对坐标
3. 计算从**当前鼠标位置**到**目标位置**的偏移量 `(dx, dy)`
4. 根据距离动态计算步数：`steps = max(15, min(50, int(distance / 10)))`
5. 生成贝塞尔曲线路径，沿路径分段移动

体感控制通过**调节步数（steps）**实现，而非直接缩放偏移量：
- 距离远 → 步数多 → 移动更平滑
- 距离近 → 步数少 → 响应更快

**注意**：Windows 指针加速（"提高指针精确度"）会导致非线性位移。当前方案通过贝塞尔曲线步数控制来缓解，如果实测仍有偏差，可考虑引入加速度补偿函数（见待验证项）。

---

## 距离补偿（Drop Compensation）

### 问题描述

精灵球投掷存在飞行时间，距离越远，飞行时间越长，同时受重力影响产生抛物线下落。

### 补偿公式（阶梯式）

```python
def calculate_drop_compensation(bbox_area: float, distance_state: str) -> int:
    """根据目标距离状态计算 Y 轴补偿量"""
    if distance_state == "CLOSE":
        return 0
    elif distance_state == "MEDIUM":
        return -10
    elif distance_state == "FAR":
        return -25
    return 0
```

### 补偿公式（线性插值，推荐）

**优化原因**：阶梯式在阈值边界会发生剧烈跳变，使用线性插值使瞄准点平滑上漂。

```python
def calculate_drop_compensation_linear(
    bbox_area: float,
    screen_area: float,
    min_compensation: int = -25,
    max_compensation: int = 0,
    far_ratio: float = 0.005,
    near_ratio: float = 0.015
) -> int:
    """
    根据目标面积线性插值计算 Y 轴补偿量

    Args:
        bbox_area: 目标边界框面积
        screen_area: 屏幕总面积 (1280x720 = 921600)
        min_compensation: 最远距离的补偿量（负值，向上）
        max_compensation: 最近距离的补偿量（0）
        far_ratio: 远距离阈值（面积百分比）
        near_ratio: 近距离阈值（面积百分比）

    Returns:
        y_compensation: Y 轴补偿量
    """
    min_area = screen_area * far_ratio     # FAR 阈值
    max_area = screen_area * near_ratio  # CLOSE 阈值

    if bbox_area >= max_area:
        return max_compensation  # 0
    elif bbox_area <= min_area:
        return min_compensation  # -25

    # 线性插值
    t = (bbox_area - min_area) / (max_area - min_area)
    compensation = int(min_compensation + t * (max_compensation - min_compensation))
    return compensation
```

| 参数 | 值 | 说明 |
|------|-----|------|
| far_ratio | 0.5% | 屏幕面积的 0.5% 作为 FAR 阈值 |
| near_ratio | 1.5% | 屏幕面积的 1.5% 作为 CLOSE 阈值 |
| min_compensation | -25 | 最远距离补偿 |
| max_compensation | 0 | 最近距离补偿 |

### 补偿后的瞄准点

```
aim_y = cy + y_compensation  # 负值表示向上移动瞄准点
aim_point = (cx, aim_y)
```

---

## 动量预测（Lead Shooting）

### 问题描述

如果精灵处于移动状态，直接瞄准当前位置会导致投掷滞后。

### 实现逻辑

```python
class MovementPredictor:
    """基于历史轨迹的目标移动预测器"""

    def __init__(self, history_size: int = 3, max_predict_step: int = 50):
        self._history: list[tuple[float, float, float]] = []  # [(x, y, timestamp), ...]
        self._history_size = history_size
        self._max_predict_step = max_predict_step  # 最大预测步长限制

    def update(self, cx: float, cy: float) -> None:
        """更新目标位置历史"""
        import time
        self._history.append((cx, cy, time.time()))
        if len(self._history) > self._history_size:
            self._history.pop(0)

    def predict(self, flight_time: float = 0.5) -> tuple[float, float]:
        """
        预测未来位置的瞄准点

        Args:
            flight_time: 精灵球预估飞行时间（秒）

        Returns:
            (predicted_x, predicted_y) - 预测的瞄准位置
        """
        if len(self._history) < 2:
            return self._history[-1][:2] if self._history else (0, 0)

        # 计算真实时间差 dt
        p1 = self._history[-2]
        p2 = self._history[-1]
        dt = p2[2] - p1[2]

        if dt <= 0:
            return p2[:2]

        # 计算速度（像素/秒）
        vx = (p2[0] - p1[0]) / dt
        vy = (p2[1] - p1[1]) / dt

        # 限制最大预测步长，防止精灵闪现导致准星飞走
        max_step = self._max_predict_step
        vx = max(-max_step, min(max_step, vx))
        vy = max(-max_step, min(max_step, vy))

        # 预测位置
        predicted_x = p2[0] + vx * flight_time
        predicted_y = p2[1] + vy * flight_time

        return (predicted_x, predicted_y)

    def reset(self) -> None:
        """重置历史记录"""
        self._history.clear()
```

**优化说明**：
- 使用真实时间戳差值 `dt` 计算速度，而非帧数差
- 添加 `max_predict_step` 限制，防止卡顿时预测矢量暴涨导致准星飞走

---

## 平滑处理（Smoothing）

### 问题描述

YOLO 检测输出存在帧间抖动（ jitter ），直接影响鼠标移动的平滑度。

### 滤波方案

#### 方案一：一阶低通滤波（简单有效）

```python
class SmoothFilter:
    """一阶低通滤波平滑器"""

    def __init__(self, alpha: float = 0.3):
        """
        Args:
            alpha: 平滑系数，值越小越平滑 (0 < alpha <= 1)
        """
        self._alpha = alpha
        self._last_x: float | None = None
        self._last_y: float | None = None

    def process(self, x: float, y: float) -> tuple[float, float]:
        """对输入坐标进行平滑处理"""
        if self._last_x is None:
            self._last_x = x
            self._last_y = y
            return (x, y)

        # 一阶低通滤波公式
        smoothed_x = self._last_x + self._alpha * (x - self._last_x)
        smoothed_y = self._last_y + self._alpha * (y - self._last_y)

        self._last_x = smoothed_x
        self._last_y = smoothed_y

        return (smoothed_x, smoothed_y)
```

#### 方案二：Kalman Filter（更优但复杂）

对于高精度需求，可使用扩展 Kalman Filter：

```
预测: x_hat(k) = A * x_hat(k-1) + B * u(k-1)
更新: K(k) = P(k) * H' / (H * P(k) * H' + R)
      x_hat(k) = x_hat(k) + K(k) * (z(k) - H * x_hat(k))
      P(k) = (I - K(k) * H) * P(k)
```

**推荐**：先实现低通滤波，验证效果后再考虑 Kalman。

---

## 距离阈值设定

### 问题描述

当前阈值为绝对像素值（如 50px²），在不同分辨率下表现不一致。

### 优化方案

使用屏幕面积百分比替代绝对值：

```python
class DistanceClassifier:
    """基于分辨率的距离分类器"""

    def __init__(self, screen_width: int, screen_height: int):
        self._screen_area = screen_width * screen_height
        # 阈值改为屏幕面积的百分比
        self._far_threshold = self._screen_area * 0.005    # 0.5% -> FAR
        self._near_threshold = self._screen_area * 0.015  # 1.5% -> CLOSE
        # MEDIUM: 0.5% ~ 1.5%

    def classify(self, bbox_area: float) -> str:
        """根据 bbox 面积分类距离"""
        if bbox_area < self._far_threshold:
            return "FAR"
        elif bbox_area < self._near_threshold:
            return "MEDIUM"
        else:
            return "CLOSE"
```

### 阈值对照表（1280x720）

屏幕面积 = 921600 px²

| 状态 | 面积阈值 | 相对阈值 |
|------|----------|----------|
| FAR | < 4608px² | < 0.5% |
| MEDIUM | 4608 ~ 13824px² | 0.5% ~ 1.5% |
| CLOSE | > 13824px² | > 1.5% |

---

## 安全性评估

### 输入方式对比

| 方式 | 安全性 | 延迟 | 实现复杂度 |
|------|--------|------|------------|
| SendInput | 低 | 低 | 简单 |
| Interception 驱动 | 中 | 低 | 中等 |
| Arduino 硬件 | 高 | 中 | 复杂 |

### 当前方案

项目采用 **Interception 驱动** + 拟人化算法：

- 贝塞尔曲线轨迹
- Fitts's Law 变速
- 微颤模拟（±5px）
- 过冲修正
- 高斯分布随机延迟

### 检测规避建议

1. **移动轨迹**：避免直线移动，使用曲线轨迹
2. **移动速度**：添加随机变速，避免匀速
3. **微动修正**：每帧移动后添加 10-50ms 随机延迟
4. **点击时序**：mouse_down 和 mouse_up 之间添加随机间隔

---

## 完整算法流程

### 整体状态机流程

```
SEARCH ──→ VERIFY ──→ NAVIGATE ──→ AIM_AND_THROW ──→ WAIT_RESULT
(WASD 靠近)        (鼠标瞄准投掷)
```

### 阶段1: WASD 导航靠近

```
┌─────────────────────────────────────────────────────────────────┐
│  NavigationStrategy.execute(ctx)                                 │
│    → 检查 verified_target                                        │
│    → 计算 target_center 与 screen_center 的偏移                   │
│    → dist <= 150px? → Action.NO_OP（导航完成）                     │
│    → dist >  150px? → Action.MOVE_WASD                           │
├─────────────────────────────────────────────────────────────────┤
│  MoveController.move_toward_target(target)                       │
│    → 循环: 计算偏移 → 决定 WASD 方向 → press_key()               │
│    → 随机按键时长 200-500ms，间隔 300-800ms                       │
│    → 最大迭代 5 次，超时 15s                                      │
│    → 直到目标中心在 ±150px 范围内                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 阶段2: 鼠标瞄准投掷

```
┌─────────────────────────────────────────────────────────────────┐
│  AimStrategy.execute(ctx)                                        │
│    → 检查 verified_target                                        │
│    → 检查投掷次数 < max_throws                                   │
│    → is_capture_mode? → Action.THROW                              │
│    → 否? → Action.PRESS_E                                        │
├─────────────────────────────────────────────────────────────────┤
│  AimAndThrow.aim_and_throw(target)                               │
│    Step 1: 获取目标中心 (cx, cy)                                  │
│    Step 2: 距离补偿（可选）                                       │
│            aim_y = cy + drop_compensation(bbox_area)              │
│    Step 3: 动量预测（可选，移动目标）                               │
│            (pred_x, pred_y) = predictor.predict(flight_time)     │
│    Step 4: 平滑滤波（可选，YOLO 抖动）                              │
│            (smooth_x, smooth_y) = filter.process(pred_x, pred_y) │
│    Step 5: mouse_move_to(aim_x, aim_y)                           │
│            → 贝塞尔曲线路径 + 拟人化算法                           │
│    Step 6: sleep(100-200ms) 稳定                                  │
│    Step 7: mouse_down() 按住                                      │
│    Step 8: sleep(hold_duration * 0.6)                             │
│    Step 9: mouse_move(±5px) 按住微调                              │
│    Step 10: sleep(hold_duration * 0.4)                            │
│    Step 11: mouse_up() 松开，完成投掷                              │
└─────────────────────────────────────────────────────────────────┘
```

### 各阶段对应的代码文件

| 阶段 | 策略 | 执行模块 | 能力层 |
|------|------|----------|--------|
| WASD 导航 | `strategies/navigation_strategy.py` | `actions/move_controller.py` | `capabilities/interception_sim.py` (press_key) |
| 鼠标瞄准 | `strategies/aim_strategy.py` | `actions/aim_and_throw.py` | `capabilities/interception_sim.py` (mouse_move_to/down/up) |
| 目标评分 | — | `capabilities/target_scoring.py` | — |
| 目标验证 | — | `capabilities/target_verifier.py` | — |

---

## 待验证项

1. **距离补偿实测**：根据实测调整 FAR/MEDIUM 的 Y 轴补偿值（当前 -25 ~ 0）
2. **动量预测**：精灵是否频繁移动？是否需要 `MovementPredictor`？飞行时间 `flight_time` 需实测
3. **平滑滤波**：测试不同 `alpha` 值的效果，找到 YOLO 抖动平滑与响应速度的平衡点
4. **Windows 指针加速**：开启"提高指针精确度"后，贝塞尔曲线步数控制是否足够？是否需要加速度补偿函数
5. **WASD 导航参数**：`center_tolerance=150px` 是否合理？`max_iterations=5` 是否足够？
6. **投掷时序**：`fine_tune_ms=500ms` 的按住时长是否符合游戏实际投掷手感

---

## 更新日志

| 日期 | 修改内容 |
|------|----------|
| 2026-04-12 | 初始版本，涵盖坐标转换、距离补偿、动量预测、平滑处理、距离阈值 |
| 2026-04-12 | 补充与导航的关系、三层架构说明、代码映射表；修正灵敏度描述误导；统一 near_ratio 为 1.5%；修正阈值对照表 |