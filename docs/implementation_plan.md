# 洛克王国自动捕捉 — 实现计划

> 本文档定义后续开发的完整模块计划。不实现，仅规划。

---

## 状态机总览

```
用户走到精灵堆（刷新点） → 启动工具
        │
        ▼
  SEARCH（搜索目标）
        │
        ├─ 检测到目标（Y 次/每 X 秒）→ CHECK_DISTANCE
        │                            │
        │                            ├─ FAR（框太小）→ MOVE_CLOSER → SEARCH
        │                            └─ MEDIUM/CLOSE → VERIFY_START
        │                                                 ↓ N 个周期连续确认
        │                                              通过
        │                                              ↓
        │                                           MOVE_CLOSER(如果需要)
        │                                                 ↓ 距离足够近
        │                                              ENTER_CAPTURE（按 E 进入精灵球模式）
        │                                                 ↓ CV 确认精灵球界面
        │                                              AIM_AND_THROW（瞄准 → 按住 → 松开）
        │                                                 ↓ 投掷完成
        │                                              WAIT_RESULT（等待结果）
        │                                                 │
        │                                                 ├─ 成功 → COOLDOWN → 回到 SEARCH
        │                                                 └─ 触发战斗 → BATTLE_STATE
        │
        └─ 画面没精灵 → ROTATE（360° 旋转搜索）
                          │
                          ├─ 找到 → 重新进入检测逻辑
                          └─ 转完一圈没找到 → 回到 SEARCH（循环）

  BATTLE_STATE（检测到进入战斗界面）
        ↓ 按 ESC 退出战斗
  COOLDOWN → 回到 SEARCH
```

---

## 模块一：目标验证（防误判 + 距离判断）

**文件**：`src/core/target_verifier.py`（重构，原 `target_tracker.py`）

**需求**：

### AC1: 降低识别频率
- 检测不再每帧运行，而是按可配置时间间隔轮询（默认：2 秒/次）
- 减少 GPU/CPU 负载，同时避免过度干扰玩家操作

### AC2: 多周期确认机制
- 同一目标必须在连续 N 个检测周期中出现（默认：3 次 = 6 秒）
- 如果目标在某周期消失或被遮挡，计数器重置
- **关键设计原则**：只有连续多次确认后，系统才认为目标是真实的，进入瞄准模式
- 此机制确保不抢玩家键盘——玩家在移动时画面会波动，无法通过连续确认

### AC3: 多目标优先级排序
- 当多个精灵同时出现时，计算每个目标中心点到屏幕中心的距离
- 优先处理离中心最近的精灵
- 公式：`dist = sqrt((x - center_x)^2 + (y - center_y)^2)`
- 在叠加层显示优先级排名（1、2、3...）

### AC4: 基于 YOLO 检测框大小的距离判断
- YOLO 输出的 bbox 面积与目标距离相关：**框越大 = 目标越近**
- 使用三个可配置阈值定义三状态：

| 状态 | 条件 | 动作 |
|------|------|------|
| **FAR** | bbox_area < MAX_DISTANCE_THRESHOLD (50px²) | 跳过捕捉，触发 MOVE_CLOSER |
| **MEDIUM** | MAX_DISTANCE ≤ bbox_area < NEAR_THRESHOLD (100px²) | 继续验证，可能需要靠近 |
| **CLOSE** | bbox_area ≥ CAPTURE_THRESHOLD (200px²) | 可以开始捕捉序列 |

- 配置参数（config.py）：
  ```python
  DETECTION_INTERVAL: float = 2.0          # 检测间隔秒数
  VERIFICATION_CYCLES: int = 3             # 需要几次连续检测
  MAX_DISTANCE_THRESHOLD: float = 50.0     # 太远阈值
  NEAR_THRESHOLD: float = 100.0            # 靠近阈值
  CAPTURE_THRESHOLD: float = 200.0         # 捕捉阈值
  SCREEN_CENTER_X_OFFSET: int = 0          # 中心 x 偏移
  SCREEN_CENTER_Y_OFFSET: int = 0          # 中心 y 偏移
  ```

**要做的事**：

1. 维护一个滚动历史窗口，记录每个目标在过去 N 个检测周期的存在状态
2. 每个检测周期：
   - 调用 YOLO 检测得到当前帧目标列表
   - 计算每个目标的 bbox 面积和距屏幕中心的距离
   - 根据阈值分类为 FAR/MEDIUM/CLOSE
   - 按优先级排序（最近优先）
3. 对最高优先级目标进行连续性验证：
   - 如果该目标在当前周期被检测到 → 计数器 +1
   - 如果未检测到 → 计数器重置为 0
   - 当计数达到 VERIFICATION_CYCLES → 确认为有效目标
4. 输出接口返回经过验证的目标及其状态

**核心类设计**：

```python
@dataclass(frozen=True)
class TargetScore:
    detection: DetectionResult
    distance_to_center: float
    bbox_area: float
    distance_state: str  # "FAR", "MEDIUM", "CLOSE"
    priority_rank: int

class TargetVerifier:
    def __init__(self, required_cycles: int):
        self.required_cycles = required_cycles
        self.detection_count = 0  # 当前已检测次数
        self.target_history: dict[int, list[bool]] = {}
        
    def process_cycle(self, detections: list[DetectionResult]) -> tuple[int | None, TargetScore | None]:
        """
        处理单个检测周期
        返回：(verified_target_id, highest_priority_verified_score)
        """
        
    def get_distance_state(self, bbox_area: float) -> str:
        """根据 bbox 面积判断距离状态"""
```

**可视化反馈**（layered_overlay.py）：
- 对每个目标显示优先级数字标签
- 距离状态颜色编码：
  - 🔴 红色边框：FAR（太远）
  - 🟡 黄色边框：MEDIUM（中等距离）
  - 🟢 绿色边框：CLOSE（可以捕捉）
- 显示验证进度条（例如：✓ ✓ ✓ / 3）
- 在状态栏显示当前检测间隔和已检测次数

**与原 target_tracker.py 的对比**：

| 特性 | 旧版 target_tracker | 新版 target_verifier |
|------|---------------------|----------------------|
| 时间基础 | 3 秒持续检测 | N 个周期（可配）× 间隔 |
| 坐标稳定性 | 检查坐标偏移 < 50px | 增加了 bbox 面积距离判断 |
| 多目标支持 | 只处理第一个 | 全排序 + 优先级 |
| 距离判断 | 无 | FAR/MEDIUM/CLOSE 三状态 |
| 灵活性 | 固定 3 秒 | 完全可配置 |

---

## 模块二：WASD 移动靠近

**文件**：`src/core/move_controller.py`

**需求**：
- 用 WASD 移动角色靠近目标宠物
- 使目标进入可投掷范围后再执行捕捉
- 移动不能太快，模拟人工节奏

**要做的事**：
1. 根据目标在画面中的位置判断移动方向：
   - 目标偏左 → 按 A
   - 目标偏右 → 按 D
   - 目标偏上 → 按 W
   - 目标偏下 → 按 S
2. 移动控制：
   - 每个方向按住 200-500ms（随机）后松开
   - 每次移动间隔随机延迟 300-800ms
   - 移动 3-5 次后重新检测距离
3. 停止条件：
   - 目标中心在画面中心 ±150px 范围内（可投掷距离）
   - 或超时（如 15 秒未靠近成功）
4. 所有坐标使用**客户区相对坐标**

**输出接口**：
```python
class MoveController:
    def move_toward(self, target_center) -> bool  # 是否成功靠近
    def is_in_range(self, target_center) -> bool  # 是否在可投掷范围
    def stop(self)
```

---

## 模块三：精灵球模式 CV 判定

**文件**：`src/core/capture_mode_detector.py`

**需求**：
- 按 E 后，用 CV 检测是否成功进入精灵球捕捉界面
- 如果未进入，需要重试或放弃

**要做的事**：
1. 用户提供模板图片（精灵球界面截图）
2. 方法：`cv2.matchTemplate` 模板匹配
3. 输入：当前游戏画面截图
4. 输出：
   - `is_capture_mode: bool` — 是否进入精灵球模式
   - `confidence: float` — 匹配置信度
5. 超时处理：等待 3 秒仍未进入 → 判定失败

**模板图片路径**：`data/templates/capture_mode.png`（待提供）

**输出接口**：
```python
class CaptureModeDetector:
    def load_template(self, path) -> bool
    def check(self, frame) -> tuple[bool, float]  # (is_capture_mode, confidence)
```

---

## 模块四：战斗状态 CV 判定

**文件**：`src/core/battle_mode_detector.py`

**需求**：
- 捕捉过程中如果触发战斗，用 CV 识别战斗界面
- 检测到战斗后，按 ESC 退出

**要做的事**：
1. 用户提供模板图片（战斗界面截图）
2. 方法：`cv2.matchTemplate` 模板匹配
3. 输入：当前游戏画面截图
4. 输出：
   - `is_battle_mode: bool` — 是否进入战斗
   - `confidence: float` — 匹配置信度
5. 超时处理：等待 3 秒仍未退出战斗 → 判定异常

**模板图片路径**：`data/templates/battle_mode.png`（待提供）

**输出接口**：
```python
class BattleModeDetector:
    def load_template(self, path) -> bool
    def check(self, frame) -> tuple[bool, float]  # (is_battle_mode, confidence)
```

---

## 模块五：ESC 退出战斗

**文件**：`src/core/battle_exit.py`

**需求**：
- 检测到战斗状态后，按 ESC 退出
- 退出后返回 SEARCH 状态

**要做的事**：
1. 调用 SendInput 发送 ESC 按键
2. 等待 1-2 秒（随机）
3. 检测是否回到正常游戏界面（精灵球/战斗模板均不匹配）
4. 最多重试 3 次，超过则判定异常

**输出接口**：
```python
class BattleExit:
    def exit_battle(self) -> bool  # 是否成功退出
```

---

## 模块六：键鼠输入（SendInput API）

**文件**：`src/core/sendinput_sim.py`（替换现有 `input_sim.py`）

**需求**：
- 不能用 pynput（太直接，容易被反作弊检测）
- 使用 Windows `SendInput` API，与 AutoHotkey 的 `SendInput` 相同
- 所有坐标使用**客户区相对坐标**

**要做的事**：

### 6.1 键盘输入
- `SendInput` 发送键盘事件（`INPUT_KEYBOARD`）
- 支持普通按键（E、ESC、Space 等）
- 随机延迟：80-150ms

### 6.2 鼠标输入
- `SendInput` 发送鼠标事件（`INPUT_MOUSE`）
- 支持：
  - `MOUSEEVENTF_LEFTDOWN` / `MOUSEEVENTF_LEFTUP`
  - `MOUSEEVENTF_MOVE`（移动）
- 坐标计算：
  - `WindowManager.get_region()` 获取客户区左上角 `(rx, ry)`
  - 发送的绝对坐标 = `(rx + rel_x, ry + rel_y)`

### 6.3 反检测模拟
- **随机延迟**：每个操作之间加 80-150ms 随机间隔
- **鼠标轨迹**：
  - 不瞬移，分 3-5 段移动
  - 每段用线性插值 + 随机偏移
  - 先快后慢（模拟人工"扫过去"的感觉）
- **随机抖动**：
  - 瞄准目标时，在目标周围 ±3-8px 范围随机抖动
  - 每次抖动间隔 50-100ms

**输出接口**：
```python
class SendInputSimulator:
    def press_key(self, key: str) -> bool
    def mouse_move(self, rel_x: int, rel_y: int) -> bool  # 带轨迹
    def mouse_click(self, rel_x: int, rel_y: int) -> bool
    def mouse_down() -> bool  # 按住左键
    def mouse_up() -> bool    # 松开左键
```

---

## 模块七：瞄准与投掷

**文件**：`src/core/aim_and_throw.py`

**需求**：
- 进入精灵球模式后，瞄准目标宠物
- 按住鼠标左键 → 对准 → 松开抛出
- 无需计算抛物线

**要做的事**：
1. 计算瞄准点：目标中心或底部（根据游戏实际调整）
2. 用 SendInput 移动鼠标到瞄准点（带轨迹模拟 + 随机抖动）
3. `mouse_down()` 按住左键
4. 微调瞄准（±抖动 2-5px，模拟人工瞄准）
5. 等待 300-600ms（随机）
6. `mouse_up()` 松开左键（抛出精灵球）
7. 等待 2-3 秒，等待结果

**输出接口**：
```python
class AimAndThrow:
    def execute(self, target_center) -> bool  # 是否成功投掷
```

---

## 模块八：状态机重构

**文件**：`src/core/state_machine.py`（重构）

**新状态定义**：

| 状态 | 描述 | 进入条件 | 退出条件 |
|------|------|---------|---------|
| SEARCH | 搜索画面中的精灵 | 初始状态 / COOLDOWN 结束 | 画面检测到精灵 |
| ROTATE | 360° 旋转搜索 | SEARCH 画面中无精灵 | 找到精灵 / 转完一圈 |
| VERIFY | 验证目标稳定性 | 检测到精灵 | 持续 3 秒坐标稳定 |
| MOVE_CLOSER | WASD 靠近 | 验证通过，距离较远 | 进入可投掷范围 |
| ENTER_CAPTURE | 按 E 进入捕捉 | 靠近完成 | CV 确认精灵球界面 |
| AIM_AND_THROW | 瞄准 + 投掷 | 进入精灵球模式 | 投掷完成 |
| WAIT_RESULT | 等待结果 | 投掷完成 | 结果判定（成功/失败/战斗） |
| BATTLE_STATE | 处理战斗 | 检测到战斗界面 | ESC 退出成功 |
| COOLDOWN | 冷却 | 捕捉成功 / 放弃 | 冷却结束 |
| ERROR | 异常恢复 | 超时 / 连续失败 | 恢复 SEARCH |

**要做的事**：
1. 重构状态机类，每个状态调用对应模块
2. 增加 `ROTATE` 状态：画面无精灵时按 A 或 D 持续旋转搜索，设定最大旋转角度（360°）
3. 旋转中一旦检测到精灵 → 立即停止旋转 → 进入 VERIFY
4. 增加超时和失败重试逻辑
5. 每个状态转换时打印日志

---

## 模块九：配置管理

**文件**：`src/capture_config.yaml` + `src/config.py` 扩展

**要做的事**：
1. 新增 `capture_config.yaml`：
```yaml
# 目标验证
verify_duration: 3.0          # 验证持续时间（秒）
verify_position_threshold: 50 # 位置偏移阈值（像素）
verify_min_count: 5           # 最少检测次数

# 移动控制
move_range_threshold: 150     # 可投掷范围（像素）
move_press_duration_min: 200  # WASD 按住最短时间（ms）
move_press_duration_max: 500  # WASD 按住最长时间（ms）
move_interval_min: 300        # 移动间隔最短（ms）
move_interval_max: 800        # 移动间隔最长（ms）
move_max_attempts: 15         # 最大移动尝试次数

# 模式检测
capture_template: "data/templates/capture_mode.png"
battle_template: "data/templates/battle_mode.png"
mode_match_threshold: 0.8     # 模板匹配阈值
mode_wait_timeout: 3.0        # 模式检测超时（秒）

# 反检测
input_delay_min: 80           # 输入随机延迟最短（ms）
input_delay_max: 150          # 输入随机延迟最长（ms）
mouse_jitter_range: 8         # 鼠标抖动范围（像素）
mouse_move_segments: 4        # 鼠标移动分段数

# 战斗退出
battle_exit_max_retries: 3    # 最大重试次数
battle_exit_wait: 1.5         # 退出后等待时间（秒）
```

2. `config.py` 增加命令行参数覆盖 YAML 配置

---

## 实施顺序

| 阶段 | 模块 | 前置依赖 | 优先级 | 说明 |
|------|------|---------|--------|------|
| 1 | **模块一：目标验证**（新版） | 无 | **高 (Story 1.1)** | 增强版，包含检测间隔、多周期确认、距离判断 |
| 2 | 模块六：SendInput 输入 | 无 | 高 | 基础功能，可并行 |
| 3 | **新增：TargetScorer 模块** | 模块一 | 高 (Story 1.1) | 负责 bbox 面积计算、距离分类、优先级排序 |
| 4 | 模块三：精灵球模式 CV | 你提供模板图片 | 高 | 需要你先给截图 |
| 5 | 模块四：战斗状态 CV | 你提供模板图片 | 高 | 需要你先给截图 |
| 6 | 模块二：WASD 移动 | 模块一、六 | 高 | 需要验证 + 输入 |
| 7 | 模块七：瞄准投掷 | 模块三、六 | 高 | 需要精灵球 CV + 输入 |
| 8 | 模块五：ESC 退出战斗 | 模块四、六 | 高 | 需要战斗 CV + 输入 |
| 9 | 模块八：状态机重构 | 模块一~八 | 高 | 整合所有模块 |
| 10 | 模块九：配置管理 | 所有模块 | 中 | 最后统一配置 |

---

## 需要你提供的素材

| 素材 | 用途 | 存放路径 |
|------|------|---------|
| 精灵球捕捉界面截图 | CV 模板匹配 | `data/templates/capture_mode.png` |
| 战斗界面截图 | CV 模板匹配 | `data/templates/battle_mode.png` |

---

## 当前已完成（不需再做）

- [x] 屏幕捕获（dxcam）
- [x] 目标检测（YOLO 模型）
- [x] 分层覆盖窗口（DWM 透明叠加）
- [x] 窗口管理（客户区坐标获取）
