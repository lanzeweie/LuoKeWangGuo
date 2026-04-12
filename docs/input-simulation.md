# 仿真键鼠输入文档

## 概述

本项目使用 `Interception` 驱动级输入模拟，内置拟人化算法，使键鼠操作在行为特征上贴近真实人类用户。所有输入坐标均为**游戏窗口客户区相对坐标**。

模块路径：`src/core/capabilities/interception_sim.py`

---

## 为什么使用 Interception 而不是 SendInput

| 对比项 | SendInput | Interception |
|--------|-----------|-------------|
| 层级 | 用户态 API | 驱动级注入 |
| 反检测 | 可被游戏反作弊检测 | 极难检测 |
| 坐标系统 | 绝对屏幕坐标 | 相对位移 |
| 拟人化 | 无 | 内置多种算法 |

**核心规则**：所有键鼠操作必须优先使用 `InterceptionSimulator`。仅在 Interception 不可用时降级到 `SendInputSimulator`（已标记为 Legacy）。

---

## 拟人化算法

### 1. 贝塞尔曲线轨迹（Cubic Bezier Curve）

人类控制鼠标时，受手臂关节（肘、腕）物理支点影响，轨迹呈现自然弧度，而非完美直线。

**数学模型**：三阶贝塞尔曲线

```
B(t) = (1-t)³P₀ + 3(1-t)²tP₁ + 3(1-t)t²P₂ + t³P₃,  t ∈ [0, 1]
```

- `P₀` — 起始点
- `P₃` — 目标点
- `P₁`, `P₂` — 动态生成的随机控制点

**实现细节**：
- 控制点在起点与终点连线两侧随机偏置
- 偏移量为距离的 15%-30%
- 每次移动的控制点角度随机，保证几何轨迹唯一性

```python
# 生成贝塞尔路径（默认 30 个采样点）
path = generate_bezier_path(start=Point(0, 0), end=Point(500, 300), steps=30)
```

### 2. Fitts's Law 变速模型

Fitts's Law 指出：移动到目标的时间是距离与目标宽度的函数。模拟人类"先加速后减速"的操作特征。

**速度曲线**：
- **前 30%** — 指数加速阶段：`(t / 0.3) ^ 1.5`
- **后 70%** — 正态分布减速阶段：`1.0 - (normalized_t²) × 0.3`

**延迟范围**：5ms - 20ms（速度快时延迟短，接近目标时延迟长）

```python
speed = fitts_speed_profile(t=0.5, distance=500)  # 返回 0-1 的速度系数
base_delay = 5 + (1 - speed) * 15  # 5-20ms
```

### 3. 微颤模拟（Micro-tremor）

人类手部因肌肉收缩存在静止震颤。在大型位移过程中，每隔 5-10 步插入 1-2 像素的随机极小位移。

```python
if i % random.randint(5, 10) == 0:
    dx += random.randint(-1, 1)
    dy += random.randint(-1, 1)
```

### 4. 过冲修复（Overshoot & Correction）

模拟准星略微移过目标点后，经过极短反应时间再移回的过程。这是高端玩家的典型生理特征，也是反作弊区分真实玩家与脚本的关键判据。

- **触发概率**：10%（仅当移动距离 > 50px 时）
- **过冲幅度**：3-8 像素
- **回调延迟**：20-50ms

```python
if random.random() < 0.1 and distance > 50:
    # 过冲
    stroke.x = direction * overshoot
    send(stroke)
    time.sleep(random.uniform(0.02, 0.05))
    # 回调
    stroke.x = -direction * overshoot
    send(stroke)
```

### 5. 高斯分布随机延迟（Stochastic Jitter）

弃用固定周期心跳轮询，改用高斯分布生成延迟。

```python
def human_like_delay(base_ms: float = 80.0) -> None:
    jitter = random.gauss(base_ms, base_ms * 0.15)  # 标准差为均值的 15%
    actual_delay = max(0.1, jitter)
    time.sleep(actual_delay / 1000.0)
```

**应用场景**：
- 按键按下/松开之间
- 鼠标点击前后
- 每段移动间隔

---

## InterceptionSimulator 类

### 初始化

```python
from src.core.capabilities.interception_sim import InterceptionSimulator

sim = InterceptionSimulator(window_mgr=window_mgr, debug=True)
```

**参数**：
- `window_mgr` — `WindowManager` 实例，用于坐标转换
- `debug` — 是否启用调试日志

**前置条件**：
1. 已安装 Interception 驱动：`pip install interception`
2. 以管理员身份运行
3. 驱动服务已启动

### 键盘操作

| 方法 | 说明 | 参数 |
|------|------|------|
| `press_key(key, duration)` | 按下 → 等待 → 松开 | `key`: 按键名, `duration`: 按住时长(秒) |
| `key_down(key)` | 仅按下 | `key`: 按键名 |
| `key_up(key)` | 仅松开 | `key`: 按键名 |

**支持的按键**：

```
WASD, E, R, F, Q, T-Z, 0-9, F1-F12
Space, Shift, Ctrl, Alt, Esc, Enter, Tab, Backspace
Delete, Insert, Home, End, PageUp, PageDown
Up, Down, Left, Right
```

**示例**：
```python
sim.press_key('w', duration=0.5)   # 按住 W 键 0.5 秒
sim.key_down('space')               # 按下空格（保持）
sim.key_up('space')                 # 松开空格
```

### 鼠标操作

| 方法 | 说明 | 坐标类型 |
|------|------|----------|
| `mouse_move(rel_x, rel_y)` | 分段相对移动（视角控制） | 相对偏移 |
| `mouse_move_to(rel_x, rel_y)` | 贝塞尔曲线移动到目标 | 客户区相对坐标 |
| `mouse_click()` | 左键点击（按下+松开） | — |
| `mouse_down()` | 左键按下 | — |
| `mouse_up()` | 左键松开 | — |
| `mouse_drag_relative(dx, dy)` | 右键拖动（视角调整） | 相对偏移 |

**示例**：
```python
# 瞄准：移动到客户区相对坐标 (640, 360)
sim.mouse_move_to(640, 360)

# 投掷：左键点击
sim.mouse_click()

# 视角调整：相对移动
sim.mouse_move(rel_x=50, rel_y=-30)

# 右键拖动（连续视角控制）
sim.mouse_drag_relative(dx=100, dy=-50)
```

---

## 按键时序特征

| 操作 | 时序特征 |
|------|----------|
| 按键按下前延迟 | 高斯分布，均值 80ms，标准差 12ms |
| 按键按住时长 | 设定值 ± 10% 高斯抖动 |
| 按键松开后延迟 | 高斯分布，均值 80ms |
| 鼠标点击按住时长 | 40-120ms 随机（高斯分布，均值 80ms） |
| 鼠标移动段间隔 | 5-20ms（根据 Fitts's Law 变速） |
| 过冲回调延迟 | 20-50ms 随机 |

这些时序特征契合人类在不同紧张程度下按键时长的统计分布。

---

## 坐标系统

**所有操作使用客户区相对坐标**，不是绝对屏幕坐标。

```
客户区相对坐标 = 屏幕绝对坐标 - 窗口客户区左上角坐标
```

`mouse_move_to()` 内部自动通过 `GetCursorPos()` 获取当前屏幕绝对坐标，再结合 `WindowManager.get_region()` 换算为客户区相对坐标。

---

## 安装与检查

### 安装 Interception 驱动

```bash
pip install interception
```

驱动需要以管理员权限安装并注册系统服务。

### 环境检查

```bash
uv run python -m src.tools.check_interception
```

### 一键测试

```bash
uv run python -m src.tools.test_input_auto
```

自动测试鼠标移动、点击、键盘操作等功能。

---

## 降级方案

如果 Interception 驱动不可用，可使用 `SendInputSimulator`（位于 `src/core/capabilities/sendinput_sim.py`），但：

- SendInput 可被部分游戏反作弊检测
- 不支持拟人化算法
- 仅作为临时降级方案

---

## 测试

### 单元测试

```bash
uv run python tests/test_interception_sim.py
```

测试覆盖：
- 贝塞尔曲线生成
- Fitts's Law 速度曲线
- 高斯延迟分布
- 各输入方法调用（Mock 驱动）

### 实际输入测试

```bash
uv run python -m src.tools.test_input_auto
```

会在屏幕上实际执行鼠标移动、点击、键盘操作，用于验证驱动级注入是否正常工作。

---

## 注意事项

1. **必须管理员运行** — Interception 驱动注入需要管理员权限
2. **坐标是客户区相对值** — 不是屏幕绝对坐标
3. **拟人化算法是核心** — 不要禁用或简化这些算法，否则可能被反作弊检测
4. **资源清理** — `InterceptionSimulator` 在 `__del__` 中自动销毁 context，也可手动管理生命周期
