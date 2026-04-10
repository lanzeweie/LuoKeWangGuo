# 单元测试计划文档

> 本文档定义策略层和执行层的单元测试计划。
> 测试分为两个级别：Mock 测试（离线）和实时测试（在线）。

**最后更新**: 2026-04-10

---

## 测试目录

| # | 测试模块 | 测试类型 | 状态 |
|---|---------|---------|------|------|
| 1 | aim_and_throw.py | 实时测试 | ⏳ 待完成 |
| 2 | search_strategy.py | Mock 测试 | ⏳ 待完成 |
| 3 | navigation_strategy.py | Mock 测试 | ⏳ 待完成 |
| 4 | move_controller.py | Mock 测试 | ✅ 已完成 |
| 5 | layered_overlay.py | 实时测试 | ⏳ 待完成 |

---

## 测试环境

### 硬件要求

| 要求 | 规格 |
|------|------|
| CPU | Intel i5 / AMD R5 及以上 |
| 内存 | 8GB 及以上 |
| GPU | NVIDIA RTX 3060 Ti（推荐） |
| 显示器 | 1280x720 @ 60Hz |

### 软件要求

| 软件 | 版本 |
|------|------|
| Windows | 10/11 |
| Python | 3.9+ |
| 游戏客户端 | 洛克王国 NRC-Win64-Shipping.exe |

### 测试数据

- **模型**: `models/trained/luoke_pet.pt`
- **测试图片**: `data/images/` 目录下选取 5 张不同场景
- **模板**: `data/templates/capture_mode.png`

---

## 测试 1: aim_and_throw.py（实时测试）

### 测试目标

验证瞄准 + 投掷执行功能，包含实时打框、自动瞄准、投掷执行。

### 功能描述

- **实时打框**: 持续在检测到的目标周围绘制边界框
- **自动瞄准**: 鼠标移动到目标中心
- **投掷执行**: 按住鼠标左键 → 微调 → 松开鼠标
- **捕捉开始**: 用户切换到捕捉状态时触发

### 测试用例

#### TC1: 实时打框显示

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_AHT_01 |
| **前置条件** | 游戏窗口获取焦点，模型已加载 |
| **输入** | 检测到 1 个目标 |
| **预期输出** | 边界框持续显示在目标周围，不闪烁、不消失 |
| **验证方法** | 视觉验证：边界框始终跟随目标 |

#### TC2: 自动瞄准 + 投掷执行

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_AHT_02 |
| **前置条件** | 游戏窗口获取焦点，检测到目标，用户切换到捕捉状态 |
| **输入** | 目标中心坐标 (cx, cy) |
| **预期输出** | 1. 鼠标移动到目标中心 ±5px<br>2. mouse_down 成功<br>3. mouse_up 成功 |
| **验证方法** | 1. 观察鼠标位置<br>2. 检查 SendInput 日志 |

#### TC3: 多目标优先级

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_AHT_03 |
| **前置条件** | 检测到 3 个目标 |
| **输入** | 3 个目标的不同位置 |
| **预期输出** | 瞄准屏幕中心最近的目标 |
| **验证方法** | 记录瞄准的目标索引 |

#### TC4: 目标丢失处理

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_AHT_04 |
| **前置条件** | 正在瞄准时目标消失 |
| **输入** | 检测列表变为空 |
| **预期输出** | 停止投掷，状态机切换到 SEARCH |
| **验证方法** | 检查状态机状态 |

#### TC5: 超时处理

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_AHT_05 |
| **前置条件** | 目标存在但无法投掷 |
| **输入** | 超过 10s 无投掷动作 |
| **预期输出** | 超时重置，返回 SEARCH |
| **验证方法** | 检查超时日志 |

### 测试步骤

```python
# 伪代码
def test_aim_and_throw_realtime():
    # 1. 初始化
    init_window()
    init_capture()
    init_detector()
    init_aim_and_throw()
    
    # 2. 启动主循环
    while running:
        frame = capture()
        detections = detector.detect(frame)
        
        # 3. 实时打框
        overlay.draw_detections(detections)
        
        # 4. 检测捕捉状态
        if is_capture_mode(frame) and detections:
            # 5. 自动瞄准
            aim_and_throw.aim_and_throw(
                target=detections[0],
                screen_width=1280,
                screen_height=720
            )
```

### 成功标准

- [ ] TC1: 边界框持续显示，不闪烁
- [ ] TC2: 鼠标成功瞄准并触发投掷
- [ ] TC3: 正确选择最近目标
- [ ] TC4: 目标丢失时正确处理
- [ ] TC5: 超时时正确重置

---

## 测试 2: search_strategy.py（Mock 测试）

### 测试目标

验证搜索策略逻辑：屏幕怎么移、怎么找精灵。

### 功能描述

- **检测到精灵**: 返回 NO_OP，交给验证层
- **没精灵**: 返回 SEARCH_PAN（小幅平移鼠标方向）
- **左右交替**: 每次平移固定角度（如 5°）

### 测试用例

#### TC1: 检测到精灵时返回 NO_OP

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_SS_01 |
| **前置条件** | ctx.detections 非空 |
| **输入** | ctx = {detections: [DetectionResult(...)]} |
| **预期输出** | Action.NO_OP |
| **验证方法** | assert execute(ctx) == Action.NO_OP |

#### TC2: 没精灵时返回 SEARCH_PAN

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_SS_02 |
| **前置条件** | ctx.detections 为空 |
| **输入** | ctx = {detections: []} |
| **预期输出** | Action.SEARCH_PAN |
| **验证方法** | assert execute(ctx) == Action.SEARCH_PAN |

#### TC3: 左右交替逻辑

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_SS_03 |
| **前置条件** | 连续 2 次调用 |
| **输入** | ctx = {detections: []} × 2 |
| **预期输出** | pan_direction: 1 → -1 → 1 |
| **验证方法** | 检查 pan_direction 变化 |

#### TC4: 最大周期后重置

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_SS_04 |
| **前置条件** | current_cycle >= max_pan_cycles |
| **输入** | 连续 N 次 ctx = {detections: []} |
| **预期输出** | current_cycle 重置为 0 |
| **验证方法** | 检查 current_cycle == 0 |

#### TC5: 获取平移参数

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_SS_05 |
| **前置条件** | 返回 SEARCH_PAN 后 |
| **输入** | get_pan_parameters() |
| **预期输出** | (pan_angle, pan_direction) |
| **验证方法** | 返回值类型和范围正确 |

### 测试数据

```python
# Mock 数据
mock_detection = DetectionResult(
    x1=800, y1=400,
    x2=850, y2=450,
    confidence=0.92,
    class_id=0
)

mock_ctx = AppContext(
    config={},
    logger=get_logger(),
    detections=[mock_detection]
)
```

### 成功标准

- [ ] TC1: 检测到精灵 → NO_OP
- [ ] TC2: 无精灵 → SEARCH_PAN
- [ ] TC3: 左右交替正确
- [ ] TC4: 周期重置正确
- [ ] TC5: 参数获取正确

---

## 测试 3: navigation_strategy.py（Mock 测试）

### 测试目标

验证导航策略逻辑：WASD 怎么靠近。

### 功能描述

- **目标在中心容差内**: 返回 NO_OP
- **目标远离**: 返回 MOVE_WASD
- **超时**: 超过 timeout_seconds 时返回 NO_OP

### 测试用例

#### TC1: 目标在中心范围内返回 NO_OP

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_NS_01 |
| **前置条件** | 目标中心距离屏幕中心 < center_tolerance |
| **输入** | target.center = (640, 360), screen_center = (640, 360) |
| **预期输出** | Action.NO_OP |
| **验证方法** | assert execute(ctx) == Action.NO_OP |

#### TC2: 目标远离返回 MOVE_WASD

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_NS_02 |
| **前置条件** | 目标中心距离屏幕中心 > center_tolerance |
| **输入** | target.center = (100, 360), screen_center = (640, 360) |
| **预期输出** | Action.MOVE_WASD |
| **验证方法** | assert execute(ctx) == Action.MOVE_WASD |

#### TC3: 移动参数计算

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_NS_03 |
| **前置条件** | verified_target 存在 |
| **输入** | target.center = (100, 360) |
| **预期输出** | direction = 'd', duration = 0.5 |
| **验证方法** | 检查返回的 (direction, duration) |

#### TC4: 超时处理

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_NS_04 |
| **前置条件** | navigation_start_time + timeout_seconds < now |
| **输入** | 时间超过 15s |
| **预期输出** | Action.NO_OP, navigation_start_time = None |
| **验证方法** | 检查状态重置 |

#### TC5: 无目标时返回 NO_OP

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_NS_05 |
| **前置条件** | verified_target = None |
| **输入** | ctx.verified_target = None |
| **预期输出** | Action.NO_OP |
| **验证方法** | assert execute(ctx) == Action.NO_OP |

### 测试数据

```python
# Mock 数据
mock_target = DetectionResult(
    x1=100, y1=400,
    x2=200, y2=500,
    confidence=0.95,
    class_id=0
)

mock_scored = TargetScore(
    detection=mock_target,
    distance_to_center=540.0,
    bbox_area=10000.0,
    distance_state="FAR",
    priority_rank=1
)
```

### 成功标准

- [ ] TC1: 中心内 → NO_OP
- [ ] TC2: 远离 → MOVE_WASD
- [ ] TC3: 参数计算正确
- [ ] TC4: 超时重置
- [ ] TC5: 无目标 → NO_OP

---

## 测试 4: layered_overlay.py（实时测试）

### 测试目标

验证分层覆盖窗口的实时显示。

### 测试用例

#### TC1: 窗口创建成功

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_LO_01 |
| **前置条件** | 无 |
| **输入** | x, y, width, height |
| **预期输出** | 窗口句柄有效 |
| **验证方法** | hwnd != 0 |

#### TC2: 边界框绘制

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_LO_02 |
| **前置条件** | 窗口已创建 |
| **输入** | TargetScore 列表 |
| **预期输出** | 在目标位置绘制矩形 |
| **验证方法** | 视觉验证 |

#### TC3: 状态文字显示

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_LO_03 |
| **前置条件** | 窗口已创建 |
| **输入** | current_state = "SEARCH" |
| **预期输出** | 显示 "寻找目标" 文字 |
| **验证方法** | 视觉验证 |

#### TC4: 验证进度条

| 测试项 | 说明 |
|--------|------|
| **测试 ID** | TC_LO_04 |
| **前置条件** | 窗口已创建 |
| **输入** | verification_progress = 2, required = 3 |
| **预期输出** | 显示 2/3 进度条 |
| **验证方法** | 视觉验证 |

---

## 测试执行顺序

```
1. Mock 测试（可离线执行）
   ├── search_strategy.py
   ├── navigation_strategy.py
   └── move_controller.py（已存在）
                ▼
2. 实时测试（需要游戏运行）
   ├── layered_overlay.py
   └── aim_and_throw.py
```

---

## 测试报告模板

```markdown
# 测试报告

## 测试环境
- 日期: YYYY-MM-DD
- 测试者: XXX

## 测试结果

| 测试 ID | 测试项 | 结果 | 备注 |
|--------|--------|------|------|
| TC_AHT_01 | 实时打框显示 | PASS/FAIL | |
| ... | ... | ... | |

## 问题记录

| # | 问题描述 | 严重级别 | 状态 |
|---|---------|---------|------|
| 1 | | | Open/Closed |

## 总结

- 通过: X/Y
- 失败: Z/Y
```

---

## 成功标准

| 模块 | 通过率 |
|------|-------|
| aim_and_throw.py | 100% |
| search_strategy.py | 100% |
| navigation_strategy.py | 100% |
| layered_overlay.py | 100% |

**总体目标**: 80%+ 测试通过率