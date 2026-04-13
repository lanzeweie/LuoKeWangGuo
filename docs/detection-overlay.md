# 检测覆盖层 — DetectionOverlay

## 概述

将 YOLO 检测打框从分散逻辑中提取为独立模块 `src/core/capabilities/detection_overlay.py`，实现：

- 打框作为**可开关参数**（仅用于用户感知，不影响核心捕捉逻辑）
- 跳帧检测 + 插值补偿，降低 GPU 负担、消除框体闪烁
- 状态机管理目标生命周期，解决遮挡/掉帧导致的框体突变
- 稳定 Track ID 分配，解决多目标检测的 ID 切换问题

---

## 模块职责边界

| 模块 | 职责 |
|------|------|
| `detection.py` | YOLO 推理，返回原始 `DetectionResult` 列表 |
| `target_scoring.py` | 目标评分与优先级排序 |
| `target_verifier.py` | 多周期目标验证（独立使用） |
| `detection_overlay.py` | 跳帧调度、插值平滑、目标状态机、Track ID 管理、绘框输出 |
| `layered_overlay.py` | 负责将帧渲染到屏幕 |

打框开关只影响 `detection_overlay.py` 的绘制输出，不影响 `detection.py` 的推理结果，
也不影响 `target_scoring.py` 和 `target_verifier.py` 的业务逻辑。

---

## 与现有模块的关系

### 与 `target_verifier.py` 的关系

两者职责不同，**并行使用，互不干扰**：

| 维度 | `target_verifier.py` | `detection_overlay.py` |
|------|---------------------|----------------------|
| 目的 | 业务逻辑：确认目标真实存在，防止误判 | 视觉呈现：在覆盖层上稳定绘制检测框 |
| 生命周期 | 单目标验证（验证通过即重置） | 多目标跟踪（同时跟踪所有出现的目标） |
| 匹配方式 | 中心点距离 + 面积相似度 | 中心点距离优先 + IoU 辅助 |
| 输出 | `(verified: bool, target: TargetScore)` | `List[TrackedTarget]`（含插值坐标） |

数据流向：

```
frame → detection.detect() → DetectionResult[]
                                ├→ target_scoring → TargetScore[] → target_verifier（业务逻辑）
                                └→ detection_overlay.update() → TrackedTarget[] → layered_overlay（视觉呈现）
```

`detection_overlay.py` 不依赖 `target_verifier.py`，两者共享同一份 `DetectionResult[]` 输入。

---

## 核心设计

### 1. 跳帧检测（Keyframe Detection）

- 每隔 `detect_interval` 帧触发一次 YOLO 推理（默认值：5 帧）
- 补偿帧不运行 YOLO，直接使用上一次检测结果 + 插值位置

```
帧序列：  1    2    3    4    5    6    7 ...
YOLO：   [检测]                [检测]
补偿：        [插值][插值][插值][插值]
```

**帧计数器**：内部维护 `_frame_count`，调用方通过 `update(frame)` 每帧传入图像，
模块自动判断当前帧是否需要运行 YOLO 推理。

**异常降级**：如果 YOLO 推理抛出异常（如 CUDA OOM），捕获异常后降级为纯插值模式，
记录错误日志，不中断主循环。连续降级超过 `max_skip_frames` 帧后强制重新检测。

### 2. 位置插值（Lerp 平滑 + 自适应）

在两次检测之间，用线性插值平滑框体位置：

```
current_pos = old_pos + (new_pos - old_pos) * alpha
```

- `alpha`：平滑系数，默认 `0.8`（越小越平滑，延迟感越重）
- 对 `x1, y1, x2, y2` 四个坐标分别插值
- 首次检测到目标时（无历史位置），直接使用原始坐标，不做插值

**自适应 Lerp**：位移超过 `adaptive_lerp_threshold`（默认 50px）时，
`lerp_alpha` 强制设为 1.0，不平滑直接跟进，避免大位移时框体跟不上目标。

**死区过滤**：bbox 中心移动小于 `deadzone_px`（默认 8px）时不更新位置，
消除静止目标的微抖动。

### 3. 目标匹配（中心点距离优先 + IoU 辅助）

将每帧的 YOLO 检测结果与已跟踪目标进行关联。

**匹配流程**：

```
1. 同时计算 IoU 矩阵和中心点距离矩阵
2. 匈牙利算法优先使用距离矩阵匹配（距离越小越好）
3. 匹配有效性判定：
   - 强匹配：中心点距离 < strong_match_dist（默认 250px）→ 直接匹配
   - 弱匹配：IoU >= weak_match_iou（默认 0.05）且距离 < weak_match_max_dist（默认 400px）
4. 未匹配的新检测 → 创建新 Candidate 目标
5. 未匹配的已跟踪目标 → 进入 Lost 状态
```

**为什么用距离优先**：小目标的 IoU 对位置偏移非常敏感，微小移动就会导致 IoU 大幅下降。
中心点距离在相邻帧间更稳定，能有效减少框体闪烁。

**匹配器降级**：scipy 不可用时，降级为贪婪匹配（按距离从小到大依次配对）。

### 4. 目标状态机

每个被跟踪目标维护独立状态：

```
[候选 Candidate] → 连续 N 帧检测到 → [活跃 Active]
[活跃 Active]    → 检测失败         → [丢失 Lost]
[丢失 Lost]      → 重新检测到       → [活跃 Active]
[丢失 Lost]      → 连续 M 帧未检测  → [销毁 Destroy]
```

| 状态 | 行为 | 推荐参数 |
|------|------|----------|
| Candidate | 记录坐标，绘制黄色细线框（让用户知道"正在确认中"） | 确认帧数 N=1 |
| Active | 绘框（绿色实线），开启容错窗口 | — |
| Lost | 按速度矢量预测位置，绘框（红色虚线） | 容错帧数 M=2 |
| Destroy | 从跟踪列表移除 | — |

**速度矢量预测（Lost 状态）**：

```
velocity = (last_center - prev_center) / dt  # 单位帧位移
predicted_center = last_center + velocity * frames_since_lost
```

- 使用中心点 `(cx, cy)` 的速度分量，而非 bbox 四角
- 加**最大预测距离**限制：预测位置不得超过 `max_predict_distance`（默认 50px）
  与上一帧位置的偏移，防止精灵突然转向时框体飘太远
- 超过限制后保持最后一帧位置不动，继续绘框（虚线）

**剧烈晃动保护**：当 Active 目标的平均位移超过 `shake_purge_threshold`（默认 150px/帧）时，
直接销毁所有 Lost 目标，防止惯性把框甩到空气上。

### 5. Track ID 分配

- 使用自增计数器 `_next_track_id`，从 1 开始
- 新目标（Candidate 创建时）分配唯一 ID
- Destroy 后的 ID **不回收**，避免新目标复用旧 ID 造成用户混淆
- ID 在绘框时显示为 `ID:{track_id}` 标签

### 6. 双重置信度过滤（解决虚空打框）

防止 YOLO 偶发误报导致屏幕出现莫名其妙的框：

**模型置信度（Confidence）**：
- YOLO 返回的原始 `conf` 值
- 低于 `min_confidence`（默认 0.5）的检测直接丢弃，不创建 Candidate

**状态确信度（Consistency）**：
- Candidate 阶段设置 `confirm_count` 计数器
- 只有连续 `confirm_frames` 帧（默认 1）都成功匹配到，才转为 Active 状态开始绘框
- 中途丢失则重置计数，直接销毁

**空间一致性校验**：
- 检测目标在相邻帧间的位移不得超过 `max_teleport_distance`（默认 100px）
- 如果位移过大（"瞬移"），判定为误报，直接舍弃该检测
- 公式：`dist = sqrt((new_cx - old_cx)^2 + (new_cy - old_cy)^2)`
- 适用于 Candidate → Active 和 Active 更新时的校验

### 7. 容错机制（解决容易掉框）

**缓冲生命值（TTL）**：
- 每个目标维护 `lost_count` 计数器
- 检测失败时不立即删除，标记为 Lost 状态
- 连续 `lost_tolerance` 帧（默认 2）未检测到才销毁

**虚线绘框**：
- Lost 状态用红色虚线绘制，Active 状态用绿色实线
- Lost 状态显示 "预测中" 标签

**运动预测**：
- 利用 `prev_center` 和 `last_center` 计算速度矢量
- Lost 状态下按速度预测位置：`predicted_pos = last_pos + velocity * lost_count`
- 预测距离限制：不超过 `max_predict_distance`（默认 50px）

### 8. 动态调整检测频率（按需识别）

根据目标运动状态自动调整 YOLO 推理频率，降低 GPU 负担：

**静止补偿**：
- 检测到目标最近 N 帧（默认 5）位移 < `static_threshold`（默认 4px）
- 自动将 `detect_interval` 从默认值增加到 `static_interval`（默认 10 帧）
- 插值准确度极高时减少推理频率

**高速检测**：
- 目标位移 > `fast_threshold`（默认 80px/帧）
- 自动将 `detect_interval` 缩短到 `fast_interval`（默认 1 帧，即每帧检测）
- 剧烈运动时提高推理频率

**动态调整逻辑**：
```python
if avg_displacement < static_threshold:
    detect_interval = static_interval  # 10 帧
elif avg_displacement > fast_threshold:
    detect_interval = fast_interval    # 1 帧
else:
    detect_interval = default_interval # 默认值
```

**位移计算**：
- 维护最近 N 帧的中心点历史 `center_history`（队列）
- 计算平均帧间位移：`avg_disp = sum(|center[i] - center[i-1]|) / N`

---

## 数据结构

```python
@dataclass
class TrackedTarget:
    """被跟踪的目标（可变，逐帧更新）"""
    track_id: int                               # 唯一标识，不回收
    state: str                                  # "candidate" | "active" | "lost" | "destroy"
    bbox: tuple[float, float, float, float]     # 当前插值后的坐标 (x1, y1, x2, y2)
    raw_bbox: tuple[float, float, float, float] # 最近一次 YOLO 检测的原始坐标
    prev_center: tuple[float, float] | None     # 上一帧中心点（用于速度计算）
    last_center: tuple[float, float]            # 当前最新中心点
    confidence: float                           # 最近一次检测的置信度
    confirm_count: int = 0                      # 候选确认计数
    lost_count: int = 0                         # 丢失帧计数
    class_id: int = 0                           # 类别 ID
    center_history: list[tuple[float, float]] = field(default_factory=list)  # 中心点历史（用于动态调频）
```

设计说明：
- `prev_center` + `last_center` 替代原来的 `velocity` 四元组，语义更清晰
- 速度在 Lost 预测时即时计算，避免维护额外的 velocity 状态
- `bbox` 始终存储插值后的坐标，供绘框和业务逻辑使用
- `center_history` 存储最近 N 帧的中心点，用于计算平均位移（动态调频）

---

## 接口设计

```python
class DetectionOverlay:
    """检测覆盖层 — 跳帧调度、目标跟踪、插值平滑、绘框输出"""

    def __init__(
        self,
        detector: ObjectDetector,        # 已有的 YOLO 检测器
        screen_width: int,
        screen_height: int,
        detect_interval: int = 5,        # 每 N 帧检测一次（默认）
        lerp_alpha: float = 0.8,         # 插值平滑系数
        confirm_frames: int = 1,         # 候选→活跃所需帧数
        lost_tolerance: int = 2,         # 丢失容错帧数
        iou_threshold: float = 0.3,      # IoU 匹配阈值
        max_predict_distance: float = 50.0,  # Lost 状态最大预测距离（像素）
        min_confidence: float = 0.5,     # 最小置信度阈值
        max_teleport_distance: float = 100.0,  # 最大瞬移距离（像素）
        # 动态调频参数
        enable_dynamic_interval: bool = True,  # 启用动态调频
        static_threshold: float = 4.0,   # 静止阈值（像素/帧）
        fast_threshold: float = 80.0,    # 高速阈值（像素/帧）
        static_interval: int = 10,       # 静止时检测间隔
        fast_interval: int = 1,          # 高速时检测间隔
        history_size: int = 5,           # 中心点历史队列长度
        # 匹配判定参数
        strong_match_dist: float = 250.0,  # 强匹配中心点距离阈值（像素）
        weak_match_iou: float = 0.05,    # 弱匹配 IoU 阈值
        weak_match_max_dist: float = 400.0,  # 弱匹配/贪婪匹配最大距离（像素）
        # 防抖参数
        deadzone_px: float = 8.0,        # 死区阈值（bbox 中心移动小于此值不更新）
        shake_purge_threshold: float = 150.0,  # 剧烈晃动阈值（像素/帧）
        # 自适应平滑参数
        adaptive_lerp_threshold: float = 50.0,  # 位移超过此值时 lerp_alpha 强制 1.0
        # 其他
        max_skip_frames: int = 10,       # 连续失败后强制重新检测的帧数
        draw_boxes: bool = True,         # 打框开关
        debug: bool = False,
    ): ...

    def update(self, frame: np.ndarray) -> list[TrackedTarget]:
        """
        每帧调用。
        自动判断是否需要运行 YOLO 推理，更新所有跟踪目标的状态。
        返回当前所有非 Destroy 状态的目标列表。
        """

    def render(self, frame: np.ndarray, targets: list[TrackedTarget]) -> np.ndarray:
        """
        在帧上绘制检测框。
        draw_boxes=False 时直接返回原帧的拷贝。
        Active 状态画实线，Lost 状态画虚线，Candidate 状态画黄色细线。
        """

    def reset(self) -> None:
        """重置所有跟踪状态（场景切换时调用）"""

    @property
    def is_detect_frame(self) -> bool:
        """当前帧是否为检测帧（调用方可据此决定是否跑业务逻辑）"""

    @property
    def active_targets(self) -> list[TrackedTarget]:
        """当前活跃的目标列表"""

    @property
    def current_interval(self) -> int:
        """当前动态调整后的检测间隔"""
```

---

## 防闪烁优化

### 问题分析

**原因**：匹配逻辑过于严格，导致同一个目标在相邻帧间因为坐标微小变化而被判定为"不同目标"，
造成框体频繁销毁重建，产生闪烁。

**核心思路**：假如识别出来坐标相差范围不大，即代表是同一个目标，不用让框消失，
而是平滑移动，避免闪烁。

### 优化方案

**匹配优先级调整**：优先使用中心点距离匹配，IoU 作为辅助验证。

```python
# 匈牙利算法使用中心点距离作为代价矩阵
cost_matrix = dist_matrix  # 距离越小越好
```

**宽松的匹配条件**：
- **强匹配**：中心点距离 < 250px → 直接匹配
- **弱匹配**：IoU >= 0.05 且距离 < 400px → 也算匹配

```python
def is_similar_enough(track_box, det_box, iou_val, dist_val):
    """判断两个框是否足够相似（优先中心点距离）"""
    # 中心点距离在 strong_match_dist 内 → 强匹配
    if dist_val < self.strong_match_dist:
        return True
    # IoU >= weak_match_iou 且距离 < weak_match_max_dist → 弱匹配
    if iou_val >= self.weak_match_iou and dist_val < self.weak_match_max_dist:
        return True
    return False
```

### 效果对比

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| 匹配优先级 | IoU 优先 | 中心点距离优先 |
| IoU 阈值 | 0.3（主匹配） | 0.05（辅助） |
| 距离阈值 | 50px | 250px（强匹配）/ 400px（弱匹配） |
| 小目标稳定性 | 差（IoU 敏感） | 好（距离稳定） |
| 框体闪烁 | 频繁 | 大幅减少 |

### 调优建议

如果仍有闪烁，可以进一步调整：

1. **增大距离阈值**：`strong_match_dist` 从 250 增加到 300
2. **增大死区**：`deadzone_px` 从 8 增加到 12
3. **增加 Lost 容错帧数**：`lost_tolerance` 从 2 增加到 5
4. **增大 Lerp 平滑系数**：`lerp_alpha` 从 0.8 减小到 0.5（越小越平滑）

---

## 调参指南

本节按"症状 → 调什么参数 → 为什么"的方式组织，方便按需查阅。

### 症状：ID 频繁断代（同一目标反复丢失/重建 ID）

**典型表现**：
- 目标静止不动，框却一会儿消失一会儿出现
- ID 从 1 跳到 2 再跳回 1
- YOLO明明每帧都能看到目标，却反复"丢失"

**根本原因**：目标在两次检测之间，因为 YOLO 跳帧或位置抖动，被判定为"不同目标"而销毁重建

**调参方案**：

| 参数 | 默认值 | 建议值 | 作用 |
|------|--------|--------|------|
| `candidate_lost_tolerance` | 10 | `detect_interval + confirm_frames + 5` | 候选目标在跳帧期间的容错帧数，必须够大覆盖跳帧周期 |
| `lost_tolerance` | 2 | 3~5 | Active 目标丢失后保留的帧数，越大越不容易丢失 |
| `confirm_frames` | 1 | 1~3 | 候选转活跃需要的连续帧数，越小越快转正但越容易误判 |
| `deadzone_px` | 8 | 10~15 | 中心点移动小于此值时不更新位置，消除抖动导致的误匹配 |

**配置建议**：
```python
# 防止 ID 断代的关键配置
candidate_lost_tolerance = 15  # 覆盖 detect_interval=5 + confirm_frames=1 + 缓冲
lost_tolerance = 3            # Active 目标丢失 3 帧才销毁
confirm_frames = 1            # 1 帧确认即可转正
deadzone_px = 10               # 10px 内的抖动忽略
```

---

### 症状：移动画面时框体延迟（画面移动后框对准空气）

**典型表现**：
- 移动画面时，检测框没有及时跟上宠物，出现了框对准空气的情况
- 框很快才跟上目标宠物
- 虽然每 5 帧识别一次（约 83ms）不慢，但仍有明显的"拖尾"或"延迟感"

**根本原因**：插值平滑系数（lerp_alpha）过低，导致每一帧框体只向目标真实位置挪动一小步，产生明显的延迟感。虽然检测间隔不慢，但过度的平滑会造成视觉上的滞后。

**调参方案**：

| 参数 | 默认值 | 建议值 | 作用 |
|------|--------|--------|------|
| `lerp_alpha` | 0.8 | 0.9~0.95 | 显著提升跟随速度，值越大跟得越快 |
| `adaptive_lerp_threshold` | 50 | 30 | 降低阈值，位移超过 30px 时瞬间跟进 |
| `fast_threshold` | 80 | 40~50 | 降低进入"高速模式"的门槛 |
| `fast_interval` | 1 | 2 | 高速移动时检测间隔，2 帧检测一次 |

**配置建议**：
```python
# 移动画面快速跟进配置
lerp_alpha = 0.9               # 显著提升跟随速度
adaptive_lerp_threshold = 30   # 超过 30px 位移直接瞬移跟进
fast_threshold = 50            # 降低高速模式门槛
fast_interval = 2              # 高速时每 2 帧检测一次
```

**优化维度说明**：

1. **核心调节：提高插值系数**
   - `lerp_alpha` 决定了框体跟随的速度
   - 原值 0.3 时每帧只移动剩余距离的 30%，延迟感非常强
   - 提高到 0.9~0.95 后框体会几乎同步贴合目标

2. **启用并调低自适应阈值**
   - 当目标位移超过 `adaptive_lerp_threshold` 时，自动强制 `lerp_alpha = 1.0`（瞬间跟进）
   - 移动画面时宠物的相对位移通常很大，调低阈值能更快进入"暴力跟进"模式

3. **优化动态调频参数**
   - 降低 `fast_threshold`（40~50），让画面一动就立即切换到高速检测模式
   - 设置 `fast_interval = 2`，确保高速移动时有足够的检测频率

---

### 症状：框体跟不上目标（通用版）

**典型表现**：
- 目标已经移动了，框体还在原位
- 移动过程中框体"卡顿"，有明显延迟
- 快速移动时框体甩不开

**根本原因**：Lerp 平滑系数太大（alpha 太小），导致新位置被严重平均化

**调参方案**：

| 参数 | 默认值 | 建议值 | 作用 |
|------|--------|--------|------|
| `lerp_alpha` | 0.8 | 0.9~1.0 | 平滑系数，越大越快跟进（1.0 = 完全不平滑） |
| `adaptive_lerp_threshold` | 50 | 30~80 | 位移超过此值时强制 lerp_alpha=1.0，快速跟上 |
| `fast_interval` | 1 | 1 | 高速时检测间隔，保持每帧检测 |

**配置建议**：
```python
# 快速跟进的配置
lerp_alpha = 0.95              # 高平滑系数，快速响应
adaptive_lerp_threshold = 50  # 位移超过 50px 时强制不平滑
```

---

### 症状：框体抖动/闪烁（目标静止但框体晃动）

**典型表现**：
- 目标完全静止，框体却在一两像素范围内抖动
- 框体边缘"毛刺"，不稳定
- 框体时而消失时而又出现（非常轻微的抖动导致匹配失败）

**根本原因**：YOLO 检测本身有 1~2 像素的输出波动，死区阈值太小无法过滤

**调参方案**：

| 参数 | 默认值 | 建议值 | 作用 |
|------|--------|--------|------|
| `deadzone_px` | 8 | 10~20 | 中心点移动小于此值时不更新插值，消除抖动 |
| `lerp_alpha` | 0.8 | 0.6~0.7 | 越小越平滑，但延迟增加 |
| `static_interval` | 10 | 15~20 | 静止时检测间隔，减少检测频率也能减少抖动 |

**配置建议**：
```python
# 防抖配置
deadzone_px = 12               # 12px 内的抖动完全忽略
lerp_alpha = 0.7               # 中等平滑
static_interval = 15           # 静止时每 15 帧检测一次
```

---

### 症状：目标消失后框体乱飞（Lost 状态预测位置失控）

**典型表现**：
- 目标被遮挡后，框体突然飘到屏幕其他位置
- 目标重新出现时，框体需要好几帧才能"追回来"
- 剧烈晃动时框体甩出屏幕

**根本原因**：Lost 状态的预测算法基于历史速度，外推过度导致位置爆炸

**调参方案**：

| 参数 | 默认值 | 建议值 | 作用 |
|------|--------|--------|------|
| `max_predict_distance` | 50 | 30~60 | Lost 预测的最大位移，越小越保守 |
| `shake_purge_threshold` | 150 | 100~200 | 超过此位移时清空所有 Lost 目标，防止惯性甩框 |

**配置建议**：
```python
# 保守预测配置
max_predict_distance = 40      # Lost 预测最多外推 40px
shake_purge_threshold = 120   # 剧烈晃动超过 120px/帧时清空 Lost
```

---

### 症状：同一目标被分配多个 ID（ID 重复）

**典型表现**：
- 目标明明是同一个，却出现了 ID=1 和 ID=2 两个框
- 目标丢失后重新出现，被当成新目标处理
- YOLO 检测不稳定时反复触发"借尸还魂"失败

**根本原因**：候选去重机制不完善，或者搜索半径太小导致"借尸还魂"无法恢复

**调参方案**：

| 参数 | 默认值 | 建议值 | 作用 |
|------|--------|--------|------|
| `very_close_dist` | 30 | 40~60 | 极近距离阈值，在此距离内直接合并 |
| `candidate_merge_iou` | 0.6 | 0.3~0.5 | 候选去重的 IoU 阈值，越小越容易合并 |
| `candidate_lost_tolerance` | 10 | 15~20 | 候选目标的容错帧数，足够大才能撑过跳帧周期 |
| `strong_match_dist` | 250 | 200~300 | 强匹配中心点距离，越大越容易匹配到 |

**配置建议**：
```python
# 防重复 ID 配置
very_close_dist = 40           # 40px 内直接合并
candidate_merge_iou = 0.4     # IoU > 0.4 即合并
candidate_lost_tolerance = 15 # 候选目标有 15 帧容错
```

---

### 症状：YOLO 偶尔漏检导致目标丢失

**典型表现**：
- YOLO 每隔几帧就"瞎"一次，目标突然丢失
- 目标明明在画面中央，YOLO 就是检测不到
- 漏检后需要好几帧才能恢复

**根本原因**：YOLO 模型本身有置信度波动，低于阈值被过滤；或者跳帧期间没有补偿机制

**调参方案**：

| 参数 | 默认值 | 建议值 | 作用 |
|------|--------|--------|------|
| `min_confidence` | 0.5 | 0.3~0.4 | 降低置信度阈值，接收更多检测结果 |
| `candidate_lost_tolerance` | 10 | 15~25 | 容错帧数，覆盖漏检周期 |
| `enable_detection_dedup` | True | True | 启用帧内去重，减少重复框 |
| `dedup_distance_threshold` | 40 | 30~50 | 去重距离阈值 |

**配置建议**：
```python
# 容忍漏检配置
min_confidence = 0.35          # 更低的置信度阈值
candidate_lost_tolerance = 20  # 20 帧容错，覆盖漏检
dedup_distance_threshold = 35  # 去重阈值
```

---

### 症状：框体位置不准确（框没有完全贴合目标）

**典型表现**：
- 框体比目标小，框和目标之间有缝隙
- 框体比目标大，框超出了目标范围
- 框体位置整体偏移

**根本原因**：这是 YOLO 模型本身的检测框精度问题，不是 DetectionOverlay 的问题

**解决方案**：
1. 检查 YOLO 模型训练质量，mAP 是否足够高
2. 考虑在检测后添加 bbox 缩放系数（DetectionOverlay 不直接支持，需要修改 `detection.py`）

---

## 已实现参数汇总

| 参数 | 默认值 | 说明 |
|------|--------|------|
| detect_interval | 5 | 检测间隔（帧） |
| lerp_alpha | 0.8 | 插值平滑系数 |
| confirm_frames | 1 | 候选→活跃所需帧数 |
| lost_tolerance | 2 | 丢失容错帧数 |
| candidate_lost_tolerance | 10+ | 候选目标的丢失容错帧数（自动计算最小值） |
| iou_threshold | 0.3 | IoU 匹配阈值 |
| max_predict_distance | 50 | Lost 最大预测距离（px） |
| min_confidence | 0.5 | 最小置信度 |
| max_teleport_distance | 100 | 最大瞬移距离（px） |
| strong_match_dist | 250 | 强匹配距离（px） |
| weak_match_iou | 0.05 | 弱匹配 IoU |
| weak_match_max_dist | 400 | 弱匹配最大距离（px） |
| very_close_dist | 30 | 极近距离阈值（px） |
| candidate_merge_iou | 0.6 | 候选去重 IoU 阈值 |
| deadzone_px | 8 | 死区阈值（px） |
| shake_purge_threshold | 150 | 剧烈晃动阈值（px/帧） |
| adaptive_lerp_threshold | 50 | 自适应 Lerp 阈值（px） |
| static_threshold | 4 | 静止阈值（px/帧） |
| fast_threshold | 80 | 高速阈值（px/帧） |
| static_interval | 10 | 静止检测间隔 |
| fast_interval | 1 | 高速检测间隔 |
| history_size | 5 | 中心点历史长度 |
| max_skip_frames | 10 | 连续失败强制重检帧数 |
| enable_detection_dedup | True | 启用帧内去重 |
| dedup_distance_threshold | 40 | 去重距离阈值（px） |

---

## 依赖说明

- `scipy`：用于匈牙利算法（`scipy.optimize.linear_sum_assignment`）
  - 如 scipy 不可用，降级为贪婪匹配（按距离从小到大依次配对）
