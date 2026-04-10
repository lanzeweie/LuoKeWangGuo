# 洛克王国自动捕捉 — 实现计划

> 本文档定义后续开发的完整模块计划。不实现，仅规划。

---

## 状态机总览

### 核心原则

> **按 E 进入精灵捕捉状态** — 只有在精灵球界面下才能执行捕捉。画面中没有精灵球界面时，绝对不要按鼠标。
> **捕捉精灵状态中按下鼠标后进入"待捕捉"期间** — 此期间精灵球界面暂时消失，CV 无法检测到捕捉状态，这是正常现象，不能因此判定为异常。
> **进入战斗后不打架，直接跑** — 按 ESC 后需要鼠标点击确认按钮才能退出，按钮的相对坐标需要用户提供（建议用 `template_captor.py` 类似的人机结合方式获取）。

### 完整状态流转

```
用户走到精灵刷新点 → 启动工具
        │
        ▼
  SEARCH（搜索目标）
        │
        ├─ 检测到目标（Y 次/每 X 秒）→ 距离判断
        │                            │
        │                            ├─ FAR（框太小）→ MOVE_CLOSER → SEARCH
        │                            └─ MEDIUM/CLOSE → VERIFY
        │                                                 ↓ N 个周期连续确认
        │                                              通过
        │                                              ↓
        │                                           MOVE_CLOSER（如果需要）
        │                                                 ↓ 距离足够近
        │                                           【关键】检测精灵球界面
        │                                                 │
        │                                                 ├─ 没有精灵球界面 → 按 E → ENTER_CAPTURE
        │                                                 │                      ↓ CV 确认精灵球界面
        │                                                 │                   AIM_AND_THROW（瞄准 → 按住 → 松开）
        │                                                 │                      ↓ 投掷完成，等待 2-3 秒
        │                                                 │                   WAIT_RESULT
        │                                                 │                      │
        │                                                 │                      ├─ 成功 → COOLDOWN → SEARCH
        │                                                 │                      ├─ 触发战斗 → BATTLE_STATE
        │                                                 │                      └─ 仍在精灵球界面 → 继续 AIM_AND_THROW
        │                                                 │
        │                                                 └─ 已有精灵球界面 → 直接 AIM_AND_THROW
        │
        └─ 画面没精灵 → ROTATE（360° 旋转搜索）
                          │
                          ├─ 找到 → 重新进入检测逻辑
                          └─ 转完一圈没找到 → 回到 SEARCH（循环）

  BATTLE_STATE（检测到进入战斗界面）
        ↓ 按 ESC
        ↓ 鼠标点击确认退出按钮（坐标由用户提供）
        ↓ CV 确认战斗界面已消失
  COOLDOWN → 回到 SEARCH
```

### 状态定义（更新版）

| 状态 | 描述 | 进入条件 | 退出条件 |
|------|------|---------|---------|
| SEARCH | 搜索画面中的精灵 | 初始状态 / COOLDOWN 结束 | 画面检测到精灵 |
| ROTATE | 360° 旋转搜索 | SEARCH 超时/无精灵 | 找到精灵 / 转完一圈 |
| VERIFY | 验证目标稳定性 | 检测到精灵 | N 个周期连续确认通过 |
| MOVE_CLOSER | WASD 靠近 | 验证通过，距离较远 | 进入可投掷范围 |
| ENTER_CAPTURE | 按 E 进入捕捉模式 | 距离足够近 | CV 确认精灵球界面出现 |
| AIM_AND_THROW | 瞄准 + 按住 + 松开 | 精灵球界面已确认 | 投掷动作完成 |
| WAIT_RESULT | 等待投掷结果 | 投掷完成 | 成功/战斗/仍在精灵球界面 |
| PENDING_CAPTURE | 投掷后等待（此期间精灵球界面暂时消失） | 松开鼠标后 | 结果判定完成 |
| BATTLE_STATE | 处理战斗 | 检测到战斗界面 | ESC + 点击确认 → 退出成功 |
| COOLDOWN | 冷却 | 捕捉成功 / 战斗退出 | 冷却结束 |
| ERROR | 异常恢复 | 超时 / 连续失败 | 恢复 SEARCH |

> **注意**：`PENDING_CAPTURE` 是一个特殊的中间状态。投掷后精灵球界面会短暂消失（精灵球飞出去动画期间），此时 CV 无法检测到精灵球界面，但这是正常流程。需要在该状态下等待 2-3 秒后重新检测，判断结果是成功/战斗/继续。

---

## 分块测试计划

> **不急整合整体链路，先分块验证三大核心模块。**

### 测试块 A：战斗退出

**文件**：`src/core/battle_mode_detector.py` + `src/core/battle_exit.py`

**测试内容**：
1. 用 `test_cv_matcher.py` 验证战斗模式模板匹配效果
2. 手动触发战斗，确认 `BattleModeDetector.check()` 能正确返回 `(True, confidence)`
3. 测试 `BattleExit.exit_battle()`：
   - 按 ESC
   - **鼠标点击确认退出按钮**（相对坐标需用户提供）
   - CV 确认战斗界面已消失
4. 重试机制：ESC + 点击无效时，最多重试 3 次

**前置条件**：
- `data/templates/battle_mode.png` 模板已就绪
- **用户提供 ESC 后确认按钮的相对坐标**（建议用 `template_captor.py` 截取战斗画面，框选确认按钮位置）

**坐标获取方法**（推荐）：
```bash
# 进入战斗后，截图并框选确认按钮
uv run python -m src.tools.template_captor --battle
# 在 GUI 中框选确认按钮区域，输出相对坐标
```

**测试脚本计划**：新建 `src/tools/test_battle_exit.py`，模拟战斗退出完整流程。

---

### 测试块 B：WASD 移动靠近目标宠物

**文件**：`src/core/move_controller.py`

**测试内容**：
1. 在画面中放置一个精灵（用户手动走到精灵面前但不靠近）
2. 测试 `MoveController.move_toward(target_center)`：
   - 目标偏左 → 按 A，目标偏右 → 按 D
   - 目标偏上 → 按 W，目标偏下 → 按 S
   - 每次移动 200-500ms（随机），间隔 300-800ms
3. 测试 `MoveController.is_in_range(target_center)`：
   - 目标中心在画面中心 ±150px 范围内
4. 测试超时机制：15 秒未靠近成功则停止

**前置条件**：
- YOLO 检测正常返回目标中心坐标
- SendInput 键盘输入正常

**测试脚本计划**：新建 `src/tools/test_move_controller.py`，手动指定目标坐标，验证移动方向和停止逻辑。

---

### 测试块 C：捕捉宠物（精灵球模式下）

**文件**：`src/core/capture_mode_detector.py` + `src/core/aim_and_throw.py`

**测试内容**：
1. 用 `test_cv_matcher.py` 验证精灵球模式模板匹配效果
2. 手动按 E 进入精灵球界面，确认 `CaptureModeDetector.check()` 返回 `(True, confidence)`
3. 测试 `AimAndThrow.execute(target_center)`：
   - 鼠标移动到瞄准点（带轨迹 + 抖动）
   - 按住左键 → 微调瞄准 → 等待 → 松开
4. **注意**：松开鼠标后精灵球界面会暂时消失（动画期间），不能因此判定异常
5. 等待 2-3 秒后检测：
   - 战斗界面 → 进入战斗
   - 精灵球界面仍在 → 继续投掷
   - 精灵球界面消失 + 无战斗 → 捕捉成功

**前置条件**：
- `data/templates/capture_mode.png` 模板已就绪
- 精灵球界面下才能执行鼠标操作（安全原则：没有精灵球界面时不按鼠标）

**测试脚本计划**：新建 `src/tools/test_capture_and_throw.py`，用户手动按 E 进入精灵球界面后启动脚本，验证瞄准和投掷。

---

## 模块一：目标验证（防误判 + 距离判断）

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
- **ESC 后需要鼠标点击确认按钮**（不是单纯按 ESC 就能退出）
- 退出后返回 SEARCH 状态

**要做的事**：
1. 调用 SendInput 发送 ESC 按键
2. 等待 0.5-1 秒（等待确认按钮出现）
3. **鼠标点击确认退出按钮**（相对坐标，由用户提供）
   - 坐标存储在配置文件中（通过 `template_captor.py` 获取）
   - `mouse_click(confirm_x, confirm_y)` — 带轨迹 + 抖动
4. 等待 1-2 秒（随机）
5. 检测是否回到正常游戏界面（精灵球/战斗模板均不匹配）
6. 最多重试 3 次，超过则判定异常

**坐标获取方式**：
```bash
# 进入战斗后，运行模板截取工具框选确认按钮
uv run python -m src.tools.template_captor --battle
# 在 GUI 中框选 ESC 后的确认按钮区域
# 输出相对坐标 (rel_x, rel_y)，存入配置
```

**输出接口**：
```python
class BattleExit:
    def __init__(self, send_input, battle_detector, confirm_btn_pos: tuple[float, float]):
        """
        Args:
            confirm_btn_pos: (rel_x, rel_y) 确认按钮的相对坐标
        """
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
- **安全原则**：只有在确认精灵球界面存在时才能执行鼠标操作。如果 CV 没有检测到精灵球界面，绝对不要按鼠标。

**特殊状态：PENDING_CAPTURE**
- 松开鼠标后，精灵球会飞出去（动画期间精灵球界面暂时消失）
- 此期间 CV 无法检测到精灵球界面，这是正常现象
- 需要等待 2-3 秒后重新检测，判断结果：
  - 战斗界面 → 进入 BATTLE_STATE
  - 精灵球界面仍在 → 继续 AIM_AND_THROW
  - 精灵球界面消失 + 无战斗 → 捕捉成功

**要做的事**：
1. **安全校验**：执行前确认 `CaptureModeDetector.check()` 返回 True
2. 计算瞄准点：目标中心或底部（根据游戏实际调整）
3. 用 SendInput 移动鼠标到瞄准点（带轨迹模拟 + 随机抖动）
4. `mouse_down()` 按住左键
5. 微调瞄准（±抖动 2-5px，模拟人工瞄准）
6. 等待 300-600ms（随机）
7. `mouse_up()` 松开左键（抛出精灵球）
8. 进入 `PENDING_CAPTURE` 状态，等待 2-3 秒
9. 重新检测画面，判断结果

**输出接口**：
```python
class AimAndThrow:
    def __init__(self, send_input, capture_detector):
        pass

    def execute(self, target_center) -> bool  # 是否成功投掷
        """
        执行前会检查精灵球界面是否存在，不存在则拒绝执行
        """
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

### 阶段一：分块测试（当前阶段）

| 步骤 | 模块 | 前置依赖 | 优先级 | 说明 |
|------|------|---------|--------|------|
| 1 | **测试 A：战斗退出** | 战斗模板 + ESC 确认按钮坐标 | **高** | CV 验证 + ESC + 鼠标点击确认 |
| 2 | **测试 B：WASD 移动靠近** | YOLO 检测正常 | **高** | 方向判断 + 距离判断 + 停止 |
| 3 | **测试 C：精灵球捕捉** | 精灵球模板 | **高** | CV 确认 + 瞄准投掷 + 结果判定 |

### 阶段二：状态机整合

| 步骤 | 模块 | 前置依赖 | 优先级 | 说明 |
|------|------|---------|--------|------|
| 4 | **目标验证增强**（模块一） | 无 | **高** | 检测间隔、多周期确认、距离判断 |
| 5 | **SendInput 输入**（模块六） | 无 | 高 | 键盘/鼠标/反检测分段轨迹 |
| 6 | **TargetScorer 模块** | 模块一 | 高 | bbox 面积计算、距离分类、优先级排序 |
| 7 | **精灵球模式 CV**（模块三） | 模板图片 | 高 | 模板匹配确认捕捉界面 |
| 8 | **战斗状态 CV**（模块四） | 模板图片 | 高 | 模板匹配确认战斗界面 |
| 9 | **WASD 移动**（模块二） | 测试 A/B/C 通过 | 高 | 实际调用 MoveController |
| 10 | **瞄准投掷**（模块七） | 测试 C 通过 | 高 | 实际调用 AimAndThrow |
| 11 | **ESC 退出战斗**（模块五） | 测试 A 通过 | 高 | ESC + 点击确认按钮 |
| 12 | **状态机重构**（模块八） | 模块 4-11 通过 | 高 | 整合所有模块，打通完整链路 |

### 阶段三：配置与优化

| 步骤 | 模块 | 前置依赖 | 优先级 | 说明 |
|------|------|---------|--------|------|
| 13 | **配置管理**（模块九） | 所有模块 | 中 | YAML 配置文件 |
| 14 | **Error handling** | 所有模块 | 中 | 健壮的错误恢复 |
| 15 | **Packaging** | 所有模块 | 低 | 独立可执行文件 |

---

## 需要你提供的素材

| 素材 | 用途 | 存放路径 | 获取方式 |
|------|------|---------|---------|
| 精灵球捕捉界面截图 | CV 模板匹配 | `data/templates/capture_mode.png` | `uv run python -m src.tools.template_captor --capture` |
| 战斗界面截图 | CV 模板匹配 | `data/templates/battle_mode.png` | `uv run python -m src.tools.template_captor --battle` |
| **ESC 确认按钮坐标** | 战斗退出时鼠标点击 | 配置文件 / `battle_exit.py` | 进入战斗后按 ESC，用 `template_captor` 框选确认按钮位置 |

---

## 当前已完成（不需再做）

- [x] 屏幕捕获（dxcam）
- [x] 目标检测（YOLO 模型）
- [x] 分层覆盖窗口（DWM 透明叠加）
- [x] 窗口管理（客户区坐标获取）
- [x] 状态机骨架（枚举 + 转换逻辑）
- [x] 目标验证 + 距离评分
- [x] SendInput 输入（反检测分段轨迹）
- [x] 移动控制器（WASD）
- [x] 瞄准与投掷逻辑
- [x] 战斗退出（ESC，待加入鼠标点击确认）
- [x] CV 模板检测器（精灵球 / 战斗）
- [x] 模板截取工具（`template_captor.py`）

## 下一步：分块测试

> 不急整合整体链路，先分块验证三大核心模块。

| 测试块 | 内容 | 需要你提供 |
|--------|------|-----------|
| **A：战斗退出** | CV 验证战斗界面 → ESC → 点击确认按钮 → 确认退出 | 战斗模板 + ESC 确认按钮的相对坐标 |
| **B：WASD 移动靠近** | 方向判断 → 移动 → 距离判断 → 停止 | 走到精灵面前（不靠近），启动检测 |
| **C：精灵球捕捉** | CV 确认精灵球界面 → 瞄准 → 按住 → 松开 → 等待结果 | 精灵球模板 + 手动按 E 进入界面 |
