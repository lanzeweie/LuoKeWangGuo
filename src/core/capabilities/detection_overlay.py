#!/usr/bin/env python3
"""
检测覆盖层模块
跳帧调度、目标跟踪、插值平滑、绘框输出
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import logging

from src.core.capabilities.detection import DetectionResult


logger = logging.getLogger(__name__)


# ── 工具函数 ──


def calc_iou(
    box1: Tuple[float, float, float, float],
    box2: Tuple[float, float, float, float],
) -> float:
    """
    计算两个 bbox 的 IoU

    Args:
        box1: (x1, y1, x2, y2)
        box2: (x1, y1, x2, y2)

    Returns:
        IoU 值 [0, 1]
    """
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - inter

    return inter / union if union > 0 else 0.0


# ── 数据结构 ──


@dataclass
class TrackedTarget:
    """被跟踪的目标（可变，逐帧更新）"""
    track_id: int  # 唯一标识，不回收
    state: str  # "candidate" | "active" | "lost" | "destroy"
    bbox: Tuple[float, float, float, float]  # 当前插值后的坐标 (x1, y1, x2, y2)
    raw_bbox: Tuple[float, float, float, float]  # 最近一次 YOLO 检测的原始坐标
    prev_center: Optional[Tuple[float, float]]  # 上一帧中心点（用于速度计算）
    last_center: Tuple[float, float]  # 当前最新中心点
    confidence: float  # 最近一次检测的置信度
    confirm_count: int = 0  # 候选确认计数
    lost_count: int = 0  # 丢失帧计数
    class_id: int = 0  # 类别 ID
    center_history: List[Tuple[float, float]] = field(default_factory=list)  # 中心点历史（用于动态调频）
    destroy_frame: Optional[int] = None  # 销毁帧号（用于记忆坟场过期清理）


# ── 检测覆盖层类 ──


class DetectionOverlay:
    """检测覆盖层 — 跳帧调度、目标跟踪、插值平滑、绘框输出"""

    def __init__(
        self,
        detector: "ObjectDetector",  # YOLO 检测器
        screen_width: int,
        screen_height: int,
        detect_interval: int = 5,  # 每 N 帧检测一次（默认，逐帧检测）
        lerp_alpha: float = 0.5,  # 插值平滑系数
        confirm_frames: int = 1,  # 候选→活跃所需帧数（降低为1，缓动场景下更容易转正）
        lost_tolerance: int = 2,  # 丢失容错帧数
        candidate_lost_tolerance: int = 10,  # 候选目标的丢失容错帧数（更高的容忍度）
        iou_threshold: float = 0.45,  # IoU 匹配阈值
        max_predict_distance: float = 80.0,  # Lost 状态最大预测距离（像素）
        draw_boxes: bool = True,  # 打框开关
        min_confidence: float = 0.5,  # 最小置信度阈值
        max_teleport_distance: Optional[float] = 130.0,  # 最大瞬移距离（None=屏幕宽度50%）
        # 动态调频参数
        enable_dynamic_interval: bool = True,  # 启用动态调频
        static_threshold: float = 10.0,  # 静止阈值（像素/帧）
        fast_threshold: float = 50.0,  # 高速阈值（像素/帧）
        static_interval: int = 10,  # 静止时检测间隔
        fast_interval: int = 2,  # 高速时检测间隔
        history_size: int = 5,  # 中心点历史队列长度
        # 匹配判定参数
        strong_match_dist: float = 250.0,  # 强匹配中心点距离阈值（像素）
        weak_match_iou: float = 0.05,  # 弱匹配 IoU 阈值（降低权重）
        weak_match_max_dist: float = 400.0,  # 弱匹配/贪婪匹配最大距离（像素）
        # 新增：极近距离匹配阈值（无视 IoU，优先处理 YOLO 抖动）
        very_close_dist: float = 30.0,  # 极近距离阈值（像素），低于此值直接通过
        candidate_merge_iou: float = 0.6,  # 候选去重最小 IoU（配合 very_close_dist）
        # 防抖参数
        deadzone_px: float = 8.0,  # 死区阈值（bbox 中心移动小于此值不更新）
        shake_purge_threshold: float = 250.0,  # 剧烈晃动阈值（像素/帧），超过此值时清空所有 Lost 目标
        # 自适应平滑参数
        adaptive_lerp_threshold: float = 30.0,  # 位移超过此值（像素）时，lerp_alpha 强制设为 1.0（不平滑，直接跟进）
        # 其他
        max_skip_frames: int = 10,  # 连续失败后强制重新检测的帧数
        dashed_line_length: int = 10,  # 虚线线段长度（像素）
        debug: bool = False,
    ):
        self.detector = detector
        self.screen_width = screen_width
        self.screen_height = screen_height

        # 参数
        # 关键问题：候选目标的容错时间必须足够长，避免跳帧期间被销毁
        # 公式：candidate_lost_tolerance >= (detect_interval - 1) + confirm_frames + 缓冲帧
        # 例如：detect_interval=3 时，需要至少 3 + 1 + 2 = 6 帧容错
        # 默认设置：detect_interval=3, confirm_frames=1, candidate_lost_tolerance=10（足够）
        self.default_detect_interval = detect_interval
        self.detect_interval = detect_interval  # 当前动态调整后的间隔
        self.lerp_alpha = lerp_alpha
        self.confirm_frames = confirm_frames
        self.lost_tolerance = lost_tolerance
        # 确保 candidate_lost_tolerance 足够大，避免跳帧期间候选目标被销毁
        self.candidate_lost_tolerance = max(
            candidate_lost_tolerance,
            detect_interval + confirm_frames + 2  # 最低保障：跳帧+确认+缓冲
        )
        self.iou_threshold = iou_threshold
        self.max_predict_distance = max_predict_distance
        self.draw_boxes = draw_boxes
        self.min_confidence = min_confidence
        self.max_teleport_distance = max_teleport_distance or (screen_width * 0.5)

        # 动态调频参数
        self.enable_dynamic_interval = enable_dynamic_interval
        self.static_threshold = static_threshold
        self.fast_threshold = fast_threshold
        self.static_interval = static_interval
        self.fast_interval = fast_interval
        self.history_size = history_size

        # 匹配判定参数
        self.strong_match_dist = strong_match_dist
        self.weak_match_iou = weak_match_iou
        self.weak_match_max_dist = weak_match_max_dist
        self.very_close_dist = very_close_dist
        self.candidate_merge_iou = candidate_merge_iou

        # 防抖参数
        self.deadzone_px = deadzone_px
        self.shake_purge_threshold = shake_purge_threshold

        # 自适应平滑参数
        self.adaptive_lerp_threshold = adaptive_lerp_threshold

        # 检测结果去重参数（解决 YOLO 同一帧多框问题）
        self.enable_detection_dedup = True  # 启用检测结果去重
        self.dedup_distance_threshold = 40.0  # 去重距离阈值（像素）

        # 其他
        self._max_skip_frames: int = max_skip_frames
        self._dashed_line_length: int = dashed_line_length
        self.debug = debug

        # 内部状态
        self._frame_count: int = 0
        self._next_track_id: int = 1
        self._targets: List[TrackedTarget] = []  # 跟踪列表（不含 Destroy）
        self._last_detection_results: List[DetectionResult] = []  # 上次检测结果
        self._consecutive_failures: int = 0  # 连续失败计数
        self._is_detect_frame: bool = False  # 当前帧是否实际跑了检测

        # 记忆坟场（方案一：保留最近销毁的目标，用于 ID 复用）
        self._destroyed_targets: List[TrackedTarget] = []
        self._destroyed_keep_frames: int = 30  # 保留 30 帧（约 1 秒）

        # scipy 可用性
        self._has_scipy: bool = True

    def update(self, frame: np.ndarray) -> List[TrackedTarget]:
        """
        每帧调用。
        自动判断是否需要运行 YOLO 推理，更新所有跟踪目标的状态。
        返回当前所有非 Destroy 状态的目标列表。

        Args:
            frame: BGR 格式的图像 (H, W, 3)

        Returns:
            TrackedTarget 列表
        """
        self._frame_count += 1

        # 动态调整检测间隔
        if self.enable_dynamic_interval:
            self._adjust_detect_interval()

        # 判断是否需要运行检测
        should_detect = (self._frame_count % self.detect_interval == 0) or \
                        (self._consecutive_failures >= self._max_skip_frames)

        self._is_detect_frame = should_detect

        if should_detect:
            # 重置连续失败计数
            self._consecutive_failures = 0

            # 运行 YOLO 检测
            try:
                detections = self.detector.detect(frame)
                self._last_detection_results = detections
            except Exception as e:
                logger.warning(f"YOLO 推理异常: {e}, 降级为纯插值模式")
                self._consecutive_failures += 1
                detections = []

            # 检测帧：完整匹配更新
            self._match_and_update(detections)
        else:
            # 补偿帧：更新 Lost 状态的预测位置和计数器
            self._update_lost_predictions()
            self._increment_lost_counts()
            self._cleanup_destroyed_targets()

            # 关键修复：在非检测帧中，让 Active/Candidate 目标继续向 raw_bbox 平滑滑动
            # 消除跳帧导致的框体停滞感
            self._smooth_active_targets()

        # 返回非 Destroy 状态的目标
        return [t for t in self._targets if t.state != "destroy"]

    def _dedup_overlapping_detections(
        self,
        det_boxes: List[Tuple],
    ) -> List[Tuple]:
        """
        帧内去重：合并 YOLO 同一帧内中心点距离过近的检测框

        Args:
            det_boxes: [(x1, y1, x2, y2, confidence, class_id), ...]

        Returns:
            去重后的检测框列表
        """
        if len(det_boxes) <= 1:
            return det_boxes

        # 按置信度从高到低排序
        sorted_dets = sorted(det_boxes, key=lambda x: x[4], reverse=True)
        keep_indices = []
        used = set()

        for i, det in enumerate(sorted_dets):
            if i in used:
                continue
            cx1 = (det[0] + det[2]) / 2
            cy1 = (det[1] + det[3]) / 2
            keep_indices.append(i)

            # 标记与当前框距离过近的其他框
            for j, other in enumerate(sorted_dets[i + 1:], start=i + 1):
                if j in used:
                    continue
                cx2 = (other[0] + other[2]) / 2
                cy2 = (other[1] + other[3]) / 2
                dist = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
                if dist < self.dedup_distance_threshold:
                    used.add(j)
                    if self.debug:
                        logger.debug(
                            f"帧内去重: 框{j}(conf={other[4]:.3f}) 与 框{i}(conf={det[4]:.3f}) "
                            f"距离={dist:.1f}px < {self.dedup_distance_threshold}px，已合并"
                        )

        # 按原顺序返回保留下来的框
        result = [sorted_dets[i] for i in keep_indices]
        return result

    def _get_predicted_center(self, target: TrackedTarget) -> Tuple[float, float]:
        """获取预测中心点（速度补偿）

        如果有速度信息（prev_center 和 last_center 都存在），
        根据距离上次检测的帧数进行外推预测。
        否则返回 last_center。
        """
        if target.prev_center is None:
            return target.last_center

        # 计算速度向量（每帧位移）
        vx = target.last_center[0] - target.prev_center[0]
        vy = target.last_center[1] - target.prev_center[1]

        # 距离上次检测的帧数（detect_interval - 1 是补偿帧数）
        frames_since_detect = max(1, self.detect_interval - 1)

        # 外推预测：last_center + velocity * frames_since_detect
        predicted_cx = target.last_center[0] + vx * frames_since_detect
        predicted_cy = target.last_center[1] + vy * frames_since_detect

        return (predicted_cx, predicted_cy)

    def _match_and_update(self, detections: List[DetectionResult]) -> None:
        """匹配检测结果与跟踪目标，并更新状态"""
        # 提取检测框
        det_boxes = [(d.x1, d.y1, d.x2, d.y2, d.confidence, d.class_id) for d in detections]

        # ── 帧内去重：合并 YOLO 同一帧内高度重叠的检测框 ──
        if self.enable_detection_dedup and len(det_boxes) > 1:
            det_boxes = self._dedup_overlapping_detections(det_boxes)
            if self.debug:
                logger.debug(f"帧内去重后: {len(det_boxes)} 个检测框")

        # 构建 IoU 矩阵
        tracked_boxes = [(t.track_id, t.bbox) for t in self._targets if t.state != "destroy"]

        # 当前有跟踪目标但没有新检测：所有目标进入丢失处理
        if not det_boxes and tracked_boxes:
            self._handle_all_lost()
            return

        # 无跟踪目标但有新检测：创建新目标
        if not tracked_boxes and det_boxes:
            if self.debug:
                logger.debug(f"无跟踪目标，创建新目标: {len(det_boxes)} 个检测框")
            self._create_new_targets(det_boxes)
            self._merge_close_candidates()
            return

        # 两者都为空：无操作
        if not det_boxes and not tracked_boxes:
            return

        if self.debug:
            logger.debug(
                f"开始匹配: {len(tracked_boxes)} 个跟踪目标, {len(det_boxes)} 个检测框"
            )

        # 计算 IoU 矩阵和中心点距离矩阵
        iou_matrix = np.zeros((len(tracked_boxes), len(det_boxes)))
        dist_matrix = np.zeros((len(tracked_boxes), len(det_boxes)))

        for i, (track_id, t_box) in enumerate(tracked_boxes):
            target = next(t for t in self._targets if t.track_id == track_id)
            # 使用预测中心点（速度补偿），而不是滞后的 bbox 中心
            t_cx, t_cy = self._get_predicted_center(target)

            for j, d_box in enumerate(det_boxes):
                # 计算 IoU
                iou_matrix[i, j] = calc_iou(t_box, d_box[:4])

                # 计算中心点距离（使用预测中心）
                d_cx = (d_box[0] + d_box[2]) / 2
                d_cy = (d_box[1] + d_box[3]) / 2
                dist = ((t_cx - d_cx) ** 2 + (t_cy - d_cy) ** 2) ** 0.5
                dist_matrix[i, j] = dist

                # 总是输出匹配候选信息（使用 info 级别）
                logger.info(
                    f"匹配候选: track={track_id} det={j} "
                    f"iou={iou_matrix[i, j]:.3f} dist={dist:.1f}px "
                    f"(pred=({t_cx:.0f},{t_cy:.0f}))"
                )

        # 匈牙利算法匹配（优先使用中心点距离）
        matched_pairs = self._hungarian_match_by_distance(
            dist_matrix, iou_matrix, len(tracked_boxes), len(det_boxes)
        )

        # 总是输出匹配结果
        logger.info(f"匈牙利匹配结果: {len(matched_pairs)} 对: {matched_pairs}")

        # 标记已匹配
        matched_det_indices = set()
        matched_track_indices = set()

        for track_idx, det_idx in matched_pairs:
            iou_val = iou_matrix[track_idx, det_idx]
            dist_val = dist_matrix[track_idx, det_idx]
            # 信任匈牙利算法的匹配结果：匈牙利算法已经通过距离最小化找到了最优匹配
            # 不再进行二次验证，避免 valid matches 被错误拒绝
            matched_track_indices.add(track_idx)
            matched_det_indices.add(det_idx)
            if self.debug:
                logger.debug(
                    f"匹配成功: track={tracked_boxes[track_idx][0]} "
                    f"iou={iou_val:.3f} dist={dist_val:.1f}px"
                )
            self._update_target(
                tracked_boxes[track_idx][0],
                det_boxes[det_idx]
            )

        # 未匹配的检测 → 新目标
        for j, det_box in enumerate(det_boxes):
            if j not in matched_det_indices:
                det_center = ((det_box[0] + det_box[2]) / 2, (det_box[1] + det_box[3]) / 2)
                if self.debug:
                    logger.debug(
                        f"检测框 {j} 未匹配，中心=({det_center[0]:.0f},{det_center[1]:.0f})，尝试恢复..."
                    )
                # 优化 C：检查附近是否有刚被标记为 lost 的目标（借尸还魂）
                if self._try_recover_lost_target(det_box):
                    continue
                if self.debug:
                    logger.debug(f"恢复失败，创建新目标")
                self._create_single_target(det_box)

        # 未匹配的跟踪目标 → 丢失
        for i, (track_id, _) in enumerate(tracked_boxes):
            if i not in matched_track_indices:
                self._mark_target_lost(track_id)

        # 检测帧结束：再做一次候选去重，避免 YOLO 抖动生成多个 ID
        self._merge_close_candidates()

    def _hungarian_match(
        self,
        iou_matrix: np.ndarray,
        n_tracks: int,
        n_dets: int,
    ) -> List[Tuple[int, int]]:
        """匈牙利算法匹配，返回 (track_idx, det_idx) 列表"""
        if n_tracks == 0 or n_dets == 0:
            return []

        try:
            from scipy.optimize import linear_sum_assignment
            # 代价矩阵：取负 IoU（求最小代价 = 求最大 IoU）
            cost_matrix = -iou_matrix[:n_tracks, :n_dets]
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            return list(zip(row_ind, col_ind))
        except ImportError:
            # 无 scipy：降级为贪婪匹配
            if self.debug:
                logger.debug("scipy 不可用，使用贪婪匹配")
            return self._greedy_match(iou_matrix, n_tracks, n_dets)

    def _hungarian_match_by_distance(
        self,
        dist_matrix: np.ndarray,
        iou_matrix: np.ndarray,
        n_tracks: int,
        n_dets: int,
    ) -> List[Tuple[int, int]]:
        """匈牙利算法匹配（优先中心点距离），返回 (track_idx, det_idx) 列表"""
        if n_tracks == 0 or n_dets == 0:
            return []

        try:
            from scipy.optimize import linear_sum_assignment
            # 代价矩阵：使用中心点距离（距离越小越好）
            cost_matrix = dist_matrix[:n_tracks, :n_dets]
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            return list(zip(row_ind, col_ind))
        except ImportError:
            # 无 scipy：降级为贪婪匹配（按距离从小到大）
            if self.debug:
                logger.debug("scipy 不可用，使用贪婪匹配（按距离）")
            return self._greedy_match_by_distance(dist_matrix, n_tracks, n_dets)

    def _greedy_match(
        self,
        iou_matrix: np.ndarray,
        n_tracks: int,
        n_dets: int,
    ) -> List[Tuple[int, int]]:
        """贪婪匹配：按 IoU 从大到小依次配对"""
        matches = []
        used_tracks = set()
        used_dets = set()

        # 按 IoU 从大到小排序
        pairs = []
        for i in range(n_tracks):
            for j in range(n_dets):
                pairs.append((iou_matrix[i, j], i, j))
        pairs.sort(key=lambda x: -x[0])

        for iou_val, i, j in pairs:
            if iou_val < self.iou_threshold:
                break
            if i not in used_tracks and j not in used_dets:
                matches.append((i, j))
                used_tracks.add(i)
                used_dets.add(j)

        return matches

    def _greedy_match_by_distance(
        self,
        dist_matrix: np.ndarray,
        n_tracks: int,
        n_dets: int,
    ) -> List[Tuple[int, int]]:
        """贪婪匹配：按中心点距离从小到大依次配对"""
        matches = []
        used_tracks = set()
        used_dets = set()

        # 按距离从小到大排序
        pairs = []
        for i in range(n_tracks):
            for j in range(n_dets):
                pairs.append((dist_matrix[i, j], i, j))
        pairs.sort(key=lambda x: x[0])  # 距离越小越好

        for dist_val, i, j in pairs:
            if dist_val > self.weak_match_max_dist:  # 距离超过阈值不匹配
                break
            if i not in used_tracks and j not in used_dets:
                matches.append((i, j))
                used_tracks.add(i)
                used_dets.add(j)

        return matches

    def _create_new_targets(self, det_boxes: List[Tuple]) -> None:
        """从检测结果创建新目标"""
        for det_box in det_boxes:
            self._create_single_target(det_box)

    def _merge_close_candidates(self) -> None:
        """合并空间上极近的候选目标，防止同一物体生成多个 track_id"""
        candidates = [t for t in self._targets if t.state == "candidate"]
        if len(candidates) < 2:
            return

        # 优先保留确认次数、置信度更高的候选
        candidates.sort(key=lambda t: (t.confirm_count, t.confidence), reverse=True)
        removed_ids = set()

        for idx, primary in enumerate(candidates):
            if primary.track_id in removed_ids:
                continue
            pcx = (primary.bbox[0] + primary.bbox[2]) / 2
            pcy = (primary.bbox[1] + primary.bbox[3]) / 2

            for other in candidates[idx + 1:]:
                if other.track_id in removed_ids or other.class_id != primary.class_id:
                    continue

                ocx = (other.bbox[0] + other.bbox[2]) / 2
                ocy = (other.bbox[1] + other.bbox[3]) / 2
                dist = ((pcx - ocx) ** 2 + (pcy - ocy) ** 2) ** 0.5
                if dist > self.very_close_dist:
                    continue

                iou_val = calc_iou(primary.bbox, other.bbox)
                if iou_val < self.candidate_merge_iou:
                    continue

                merged_bbox = tuple(
                    (primary.bbox[k] + other.bbox[k]) / 2 for k in range(4)
                )
                primary.bbox = merged_bbox
                primary.raw_bbox = merged_bbox
                primary.last_center = (
                    (merged_bbox[0] + merged_bbox[2]) / 2,
                    (merged_bbox[1] + merged_bbox[3]) / 2,
                )
                if primary.prev_center is None and other.prev_center is not None:
                    primary.prev_center = other.prev_center
                primary.confirm_count = max(primary.confirm_count, other.confirm_count)
                primary.confidence = max(primary.confidence, other.confidence)
                primary.center_history.extend(other.center_history)
                if len(primary.center_history) > self.history_size:
                    primary.center_history = primary.center_history[-self.history_size:]

                removed_ids.add(other.track_id)
                if self.debug:
                    logger.debug(
                        f"候选去重: merge ID={other.track_id} → ID={primary.track_id} "
                        f"dist={dist:.1f}px iou={iou_val:.2f}"
                    )

        if removed_ids:
            before = len(self._targets)
            self._targets = [t for t in self._targets if t.track_id not in removed_ids]
            if self.debug:
                logger.debug(
                    f"候选去重完成: {before} → {len(self._targets)} "
                    f"(剔除 {len(removed_ids)} 个冗余候选)"
                )

    def _try_recover_lost_target(self, det_box: Tuple) -> bool:
        """尝试从 lost/已销毁 状态的目标中恢复（借尸还魂）

        检测框未匹配到任何目标时，先检查 _targets 中 lost 状态的目标，
        再检查坟场（_destroyed_targets）中最近销毁的目标。
        如果距离足够近且类别一致，直接复用该 ID，而不是创建新 ID。

        Args:
            det_box: (x1, y1, x2, y2, confidence, class_id)

        Returns:
            True 表示成功恢复，False 表示需要创建新目标
        """
        x1, y1, x2, y2, confidence, class_id = det_box
        det_center = ((x1 + x2) / 2, (y1 + y2) / 2)

        # 关键修复：增大搜索半径，覆盖静止目标的微小抖动
        # 搜索半径 = max(very_close_dist * 4, 检测间隔内的最大位移)
        search_radius = max(self.very_close_dist * 4, self.detect_interval * 10.0 + 50.0)

        best_target = None
        best_dist = search_radius

        # 第一步：查找 lost 状态的目标
        lost_count = 0
        for target in self._targets:
            if target.state == "lost":
                lost_count += 1
                # 使用 raw_bbox 的中心点（最新的 YOLO 检测位置）而不是预测位置
                # 避免预测误差导致距离计算错误
                raw_cx = (target.raw_bbox[0] + target.raw_bbox[2]) / 2
                raw_cy = (target.raw_bbox[1] + target.raw_bbox[3]) / 2
                dist = ((det_center[0] - raw_cx) ** 2 +
                        (det_center[1] - raw_cy) ** 2) ** 0.5

                if self.debug:
                    logger.debug(
                        f"  Lost目标 ID={target.track_id}: 中心=({raw_cx:.0f},{raw_cy:.0f}), "
                        f"距离检测框={dist:.1f}px, class={target.class_id}"
                    )

                if class_id != target.class_id:
                    continue

                if dist < best_dist:
                    best_dist = dist
                    best_target = target

        if self.debug:
            logger.debug(f"搜索 Lost 目标: {lost_count} 个，search_radius={search_radius:.1f}px")

        # 第二步：如果 lost 列表没找到，搜索坟场（记忆坟场）
        if best_target is None:
            graveyard_count = 0
            for target in self._destroyed_targets:
                # 只考虑最近 30 帧内销毁的目标（增大时间窗口）
                frames_since_destroy = self._frame_count - target.destroy_frame
                if frames_since_destroy > 30:
                    continue
                graveyard_count += 1
                # 使用 raw_bbox 的中心点
                raw_cx = (target.raw_bbox[0] + target.raw_bbox[2]) / 2
                raw_cy = (target.raw_bbox[1] + target.raw_bbox[3]) / 2
                dist = ((det_center[0] - raw_cx) ** 2 +
                        (det_center[1] - raw_cy) ** 2) ** 0.5

                if self.debug:
                    logger.debug(
                        f"  坟墓目标 ID={target.track_id}: 中心=({raw_cx:.0f},{raw_cy:.0f}), "
                        f"距离检测框={dist:.1f}px, 销毁{frames_since_destroy}帧前, class={target.class_id}"
                    )

                if class_id != target.class_id:
                    continue

                if dist < best_dist:
                    best_dist = dist
                    best_target = target

            if self.debug:
                logger.debug(f"搜索坟场: {graveyard_count} 个有效目标")

        if best_target is not None:
            if self.debug:
                source = "lost" if best_target in self._targets else "graveyard"
                logger.debug(
                    f"恢复目标 ID={best_target.track_id} "
                    f"(source={source}, dist={best_dist:.1f}px < {search_radius:.1f}px)"
                )
            # 如果来自坟场，需要重新加回 _targets 列表
            if best_target not in self._targets:
                best_target.state = "lost"
                best_target.lost_count = 0
                self._targets.append(best_target)
                self._destroyed_targets.remove(best_target)
            self._update_target(best_target.track_id, det_box)
            return True

        if self.debug:
            logger.debug(f"恢复失败：无足够近的目标 (best_dist={best_dist:.1f}px >= {search_radius:.1f}px)")
        return False

    def _create_single_target(self, det_box: Tuple) -> None:
        """创建单个新目标"""
        x1, y1, x2, y2, confidence, class_id = det_box

        # 置信度低于阈值，不创建
        if confidence < self.min_confidence:
            if self.debug:
                logger.debug(f"跳过低置信度检测: conf={confidence:.3f} < {self.min_confidence}")
            return

        track_id = self._next_track_id
        self._next_track_id += 1

        center = ((x1 + x2) / 2, (y1 + y2) / 2)

        target = TrackedTarget(
            track_id=track_id,
            state="candidate",
            bbox=(x1, y1, x2, y2),
            raw_bbox=(x1, y1, x2, y2),
            prev_center=None,
            last_center=center,
            confidence=confidence,
            confirm_count=1,
            lost_count=0,
            class_id=class_id,
        )
        self._targets.append(target)
        if self.debug:
            logger.debug(f"创建新目标 ID={track_id} conf={confidence:.3f}")

    def _update_target(self, track_id: int, det_box: Tuple) -> None:
        """更新已有目标"""
        x1, y1, x2, y2, confidence, class_id = det_box
        new_bbox = (x1, y1, x2, y2)
        new_center = ((x1 + x2) / 2, (y1 + y2) / 2)

        for target in self._targets:
            if target.track_id == track_id:
                # 空间一致性校验：检测瞬移
                if target.last_center:
                    dist = ((new_center[0] - target.last_center[0]) ** 2 +
                            (new_center[1] - target.last_center[1]) ** 2) ** 0.5
                    if dist > self.max_teleport_distance:
                        if self.debug:
                            logger.debug(
                                f"目标 ID={track_id} 瞬移距离过大 ({dist:.1f}px > {self.max_teleport_distance:.1f}px)，舍弃该检测"
                            )
                        # 标记为丢失，不更新位置
                        if target.state == "candidate":
                            target.state = "destroy"
                        elif target.state == "active":
                            target.state = "lost"
                            target.lost_count = 1
                        return

                # 死区：bbox 中心移动小于 deadzone_px 时不更新插值位置，消除静止目标抖动
                old_bbox = target.bbox
                old_cx = (old_bbox[0] + old_bbox[2]) / 2
                old_cy = (old_bbox[1] + old_bbox[3]) / 2
                new_cx_val = (new_bbox[0] + new_bbox[2]) / 2
                new_cy_val = (new_bbox[1] + new_bbox[3]) / 2
                dist = ((new_cx_val - old_cx) ** 2 + (new_cy_val - old_cy) ** 2) ** 0.5

                # 状态转移（必须在死区检查之后执行，因为死区检查有 break）
                if target.state == "candidate":
                    target.confirm_count += 1
                    if target.confirm_count >= self.confirm_frames:
                        target.state = "active"
                        if self.debug:
                            logger.debug(f"目标 ID={track_id} 验证通过，转为 Active")
                elif target.state == "lost":
                    # 重新检测到，恢复为 active
                    target.state = "active"
                    target.lost_count = 0
                    if self.debug:
                        logger.debug(f"目标 ID={track_id} 重新检测到，恢复 Active")

                # 死区内仅更新元数据，跳过插值
                if dist < self.deadzone_px:
                    target.confidence = confidence
                    target.last_center = new_center
                    target.raw_bbox = new_bbox
                    target.center_history.append(new_center)
                    if len(target.center_history) > self.history_size:
                        target.center_history.pop(0)
                    break

                # 自适应 Lerp：位移大时直接跟进（不平滑），位移小时用 lerp_alpha 防抖
                current_alpha = 1.0 if dist >= self.adaptive_lerp_threshold else self.lerp_alpha

                # Lerp 插值
                interpolated_bbox = (
                    old_bbox[0] + (new_bbox[0] - old_bbox[0]) * current_alpha,
                    old_bbox[1] + (new_bbox[1] - old_bbox[1]) * current_alpha,
                    old_bbox[2] + (new_bbox[2] - old_bbox[2]) * current_alpha,
                    old_bbox[3] + (new_bbox[3] - old_bbox[3]) * current_alpha,
                )

                target.prev_center = target.last_center
                target.last_center = new_center
                target.raw_bbox = new_bbox
                target.bbox = interpolated_bbox
                target.confidence = confidence

                # 更新中心点历史（用于动态调频）
                target.center_history.append(new_center)
                if len(target.center_history) > self.history_size:
                    target.center_history.pop(0)

                break

    def _mark_target_lost(self, track_id: int) -> None:
        """标记目标丢失"""
        for target in self._targets:
            if target.track_id == track_id:
                if target.state == "candidate":
                    # 候选目标匹配失败：转为 lost，使用更高的容错帧数
                    target.state = "lost"
                    target.lost_count = 1
                elif target.state == "active":
                    # 活跃目标进入 lost 状态
                    target.state = "lost"
                    target.lost_count = 1
                elif target.state == "lost":
                    # 继续丢失
                    target.lost_count += 1
                    # 根据原始状态使用不同的容错阈值
                    tolerance = self.candidate_lost_tolerance if target.confirm_count < self.confirm_frames else self.lost_tolerance
                    if target.lost_count >= tolerance:
                        target.state = "destroy"
                        target.destroy_frame = self._frame_count  # 记录销毁帧号
                break

    def _handle_all_lost(self) -> None:
        """处理所有目标丢失（无新检测结果时调用）"""
        for target in self._targets:
            if target.state == "candidate":
                # Candidate 尚未验证，给更多容错帧（YOLO 检测不稳定时不会轻易销毁）
                target.lost_count += 1
                if target.lost_count >= self.candidate_lost_tolerance:
                    target.state = "destroy"
                    target.destroy_frame = self._frame_count  # 记录销毁帧号
            elif target.state == "active":
                target.state = "lost"
                target.lost_count = 1
            elif target.state == "lost":
                target.lost_count += 1
                # 根据原始状态使用不同的容错阈值
                tolerance = self.candidate_lost_tolerance if target.confirm_count < self.confirm_frames else self.lost_tolerance
                if target.lost_count >= tolerance:
                    target.state = "destroy"
                    target.destroy_frame = self._frame_count  # 记录销毁帧号

        # ── 立即清理 destroy 目标，让它们进入记忆坟场 ──
        # 这样借尸还魂才能在下一帧检测到时正确恢复 ID
        self._cleanup_destroyed_targets()

    def render(self, frame: np.ndarray, targets: List[TrackedTarget]) -> np.ndarray:
        """
        在帧上绘制检测框。

        Args:
            frame: 原始帧
            targets: TrackedTarget 列表

        Returns:
            绘制了检测框的帧（draw_boxes=False 时返回原帧拷贝）
        """
        import cv2

        if not self.draw_boxes:
            return frame.copy()

        output = frame.copy()

        for target in targets:
            if target.state == "candidate":
                # 候选状态：黄色细线框
                color = (0, 255, 255)  # 黄色
                thickness = 1
                line_type = cv2.LINE_AA
                x1, y1, x2, y2 = map(int, target.bbox)
                cv2.rectangle(output, (x1, y1), (x2, y2), color, thickness, line_type)
                # 绘制标签
                label = f"ID:{target.track_id} ?{target.confirm_count}/{self.confirm_frames}"
                cv2.putText(
                    output,
                    label,
                    (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    1,
                    line_type,
                )
                continue

            x1, y1, x2, y2 = map(int, target.bbox)

            # 根据状态选择样式
            if target.state == "active":
                # 实线框
                color = (0, 255, 0)  # 绿色
                thickness = 2
                line_type = cv2.LINE_AA
            elif target.state == "lost":
                # 虚线框
                color = (0, 0, 255)  # 红色
                thickness = 2
                # 绘制虚线
                self._draw_dashed_rect(output, x1, y1, x2, y2, color, thickness)
                # 绘制标签（预测中）
                label = f"ID:{target.track_id} 预测中 {target.lost_count}/{self.lost_tolerance}"
                cv2.putText(
                    output,
                    label,
                    (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    1,
                    cv2.LINE_AA,
                )
                continue

            # 绘制实线框
            cv2.rectangle(output, (x1, y1), (x2, y2), color, thickness, line_type)

            # 绘制标签
            label = f"ID:{target.track_id} {target.confidence:.2f}"
            cv2.putText(
                output,
                label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
                line_type,
            )

        return output

    def _draw_dashed_rect(
        self,
        img: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        color: Tuple[int, int, int],
        thickness: int,
        dash_length: Optional[int] = None,
    ) -> None:
        """绘制虚线矩形"""
        import cv2

        if dash_length is None:
            dash_length = self._dashed_line_length

        # 上边
        for i in range(x1, x2, dash_length * 2):
            cv2.line(img, (i, y1), (min(i + dash_length, x2), y1), color, thickness)
        # 下边
        for i in range(x1, x2, dash_length * 2):
            cv2.line(img, (i, y2), (min(i + dash_length, x2), y2), color, thickness)
        # 左边
        for i in range(y1, y2, dash_length * 2):
            cv2.line(img, (x1, i), (x1, min(i + dash_length, y2)), color, thickness)
        # 右边
        for i in range(y1, y2, dash_length * 2):
            cv2.line(img, (x2, i), (x2, min(i + dash_length, y2)), color, thickness)

    def reset(self) -> None:
        """重置所有跟踪状态（场景切换时调用）"""
        self._frame_count = 0
        self._targets = []
        self._last_detection_results = []
        self._consecutive_failures = 0
        # Track ID 继续递增，不重置

    @property
    def is_detect_frame(self) -> bool:
        """当前帧是否为检测帧（调用方可据此决定是否跑业务逻辑）"""
        return self._is_detect_frame

    @property
    def active_targets(self) -> List[TrackedTarget]:
        """当前活跃的目标列表"""
        return [t for t in self._targets if t.state == "active"]

    @property
    def current_interval(self) -> int:
        """当前动态调整后的检测间隔"""
        return self.detect_interval

    def _adjust_detect_interval(self) -> None:
        """动态调整检测间隔（根据目标运动状态）"""
        if not self.enable_dynamic_interval:
            return

        # 只考虑 Active 状态的目标
        active = [t for t in self._targets if t.state == "active"]
        if not active:
            # 无活跃目标，恢复默认间隔
            self.detect_interval = self.default_detect_interval
            return

        # 计算所有活跃目标的平均位移
        total_disp = 0.0
        count = 0
        for target in active:
            disp = self._calculate_avg_displacement(target)
            if disp is not None:
                total_disp += disp
                count += 1

        if count == 0:
            # 无足够历史数据，保持默认
            self.detect_interval = self.default_detect_interval
            return

        avg_disp = total_disp / count

        # 根据平均位移调整间隔
        old_interval = self.detect_interval
        if avg_disp < self.static_threshold:
            # 静止：增加间隔
            self.detect_interval = self.static_interval
        elif avg_disp > self.fast_threshold:
            # 高速：减少间隔
            self.detect_interval = self.fast_interval
        else:
            # 正常速度：默认间隔
            self.detect_interval = self.default_detect_interval

        if self.debug and old_interval != self.detect_interval:
            logger.debug(
                f"动态调频: 平均位移={avg_disp:.1f}px/帧, "
                f"间隔 {old_interval} → {self.detect_interval} 帧"
            )

    def _calculate_avg_displacement(self, target: TrackedTarget) -> Optional[float]:
        """计算目标的平均帧间位移"""
        if len(target.center_history) < 2:
            return None

        total_dist = 0.0
        for i in range(1, len(target.center_history)):
            prev = target.center_history[i - 1]
            curr = target.center_history[i]
            dist = ((curr[0] - prev[0]) ** 2 + (curr[1] - prev[1]) ** 2) ** 0.5
            total_dist += dist

        return total_dist / (len(target.center_history) - 1)

    def _update_lost_predictions(self) -> None:
        """更新 Lost 状态目标的预测位置（补偿帧调用）"""
        # 剧烈晃动时，直接销毁所有 Lost 目标（防止惯性把框甩到空气上）
        active_displacements = [
            self._calculate_avg_displacement(t)
            for t in self._targets
            if t.state == "active"
        ]
        if any(d is not None and d > self.shake_purge_threshold for d in active_displacements):
            for target in self._targets:
                if target.state == "lost":
                    target.state = "destroy"
            return

        for target in self._targets:
            if target.state == "lost" and target.prev_center and target.last_center:
                # 计算速度矢量
                vx = target.last_center[0] - target.prev_center[0]
                vy = target.last_center[1] - target.prev_center[1]

                # 预测新位置
                predicted_cx = target.last_center[0] + vx * target.lost_count
                predicted_cy = target.last_center[1] + vy * target.lost_count

                # 限制预测距离
                pred_dist = ((predicted_cx - target.last_center[0]) ** 2 +
                             (predicted_cy - target.last_center[1]) ** 2) ** 0.5
                if pred_dist > self.max_predict_distance:
                    # 超过最大距离，保持最后位置
                    predicted_cx = target.last_center[0]
                    predicted_cy = target.last_center[1]

                # 更新 bbox（保持宽高不变）
                w = target.bbox[2] - target.bbox[0]
                h = target.bbox[3] - target.bbox[1]
                target.bbox = (
                    predicted_cx - w / 2,
                    predicted_cy - h / 2,
                    predicted_cx + w / 2,
                    predicted_cy + h / 2,
                )

    def _increment_lost_counts(self) -> None:
        """补偿帧递增 Lost 状态的计数器，检查超时销毁"""
        for target in self._targets:
            if target.state == "lost":
                target.lost_count += 1
                # 关键修复：候选目标的容错时间更长，避免跳帧期间被销毁
                tolerance = self.candidate_lost_tolerance if target.confirm_count < self.confirm_frames else self.lost_tolerance
                if target.lost_count >= tolerance:
                    target.state = "destroy"
                    if self.debug:
                        logger.debug(f"目标 ID={target.track_id} Lost 超时，销毁 (tolerance={tolerance})")

    def _smooth_active_targets(self) -> None:
        """
        在非检测帧中，让活跃目标的画框位置(bbox)平滑地向真实位置(raw_bbox)逼近。
        消除因为跳帧导致的框体停滞感。
        """
        for target in self._targets:
            # 只处理 candidate 和 active 状态，lost 状态由 _update_lost_predictions 负责
            if target.state in ("candidate", "active"):
                old_bbox = target.bbox
                new_bbox = target.raw_bbox

                # 计算当前框中心与目标框中心的距离
                old_cx = (old_bbox[0] + old_bbox[2]) / 2
                old_cy = (old_bbox[1] + old_bbox[3]) / 2
                new_cx = (new_bbox[0] + new_bbox[2]) / 2
                new_cy = (new_bbox[1] + new_bbox[3]) / 2
                dist = ((new_cx - old_cx) ** 2 + (new_cy - old_cy) ** 2) ** 0.5

                # 1. 死区校验：如果已经靠得足够近了，就不动了，防止微小抖动
                if dist < self.deadzone_px:
                    continue

                # 2. 自适应平滑：如果距离被拉开得特别大（比如突然快速拖动画面），取消平滑直接跟上
                current_alpha = 1.0 if dist >= self.adaptive_lerp_threshold else self.lerp_alpha

                # 3. Lerp 插值计算：每一帧都向前挪动一小步
                interpolated_bbox = (
                    old_bbox[0] + (new_bbox[0] - old_bbox[0]) * current_alpha,
                    old_bbox[1] + (new_bbox[1] - old_bbox[1]) * current_alpha,
                    old_bbox[2] + (new_bbox[2] - old_bbox[2]) * current_alpha,
                    old_bbox[3] + (new_bbox[3] - old_bbox[3]) * current_alpha,
                )

                # 更新绘图框体
                target.bbox = interpolated_bbox

    def _cleanup_destroyed_targets(self) -> None:
        """清理 Destroy 状态的目标，但保留到记忆坟场（方案一）"""
        # 将 destroy 状态的目标移到坟场
        newly_destroyed = [t for t in self._targets if t.state == "destroy"]
        for target in newly_destroyed:
            target.destroy_frame = self._frame_count  # 记录销毁帧号
        self._destroyed_targets.extend(newly_destroyed)

        # 从主列表中移除
        self._targets = [t for t in self._targets if t.state != "destroy"]

        # 清理过期的坟场目标（保留最近 30 帧）
        self._destroyed_targets = [
            t for t in self._destroyed_targets
            if (self._frame_count - t.destroy_frame) <= self._destroyed_keep_frames
        ]
