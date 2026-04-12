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


# ── 检测覆盖层类 ──


class DetectionOverlay:
    """检测覆盖层 — 跳帧调度、目标跟踪、插值平滑、绘框输出"""

    def __init__(
        self,
        detector: "ObjectDetector",  # YOLO 检测器
        screen_width: int,
        screen_height: int,
        detect_interval: int = 5,  # 每 N 帧检测一次（默认，逐帧检测）
        lerp_alpha: float = 0.8,  # 插值平滑系数
        confirm_frames: int = 4,  # 候选→活跃所需帧数
        lost_tolerance: int = 2,  # 丢失容错帧数
        iou_threshold: float = 0.3,  # IoU 匹配阈值
        max_predict_distance: float = 50.0,  # Lost 状态最大预测距离（像素）
        draw_boxes: bool = True,  # 打框开关
        min_confidence: float = 0.5,  # 最小置信度阈值
        max_teleport_distance: Optional[float] = 100.0,  # 最大瞬移距离（None=屏幕宽度50%）
        # 动态调频参数
        enable_dynamic_interval: bool = True,  # 启用动态调频
        static_threshold: float = 4.0,  # 静止阈值（像素/帧）
        fast_threshold: float = 80.0,  # 高速阈值（像素/帧）
        static_interval: int = 10,  # 静止时检测间隔
        fast_interval: int = 1,  # 高速时检测间隔
        history_size: int = 5,  # 中心点历史队列长度
        # 匹配判定参数
        strong_match_dist: float = 250.0,  # 强匹配中心点距离阈值（像素）
        weak_match_iou: float = 0.05,  # 弱匹配 IoU 阈值
        weak_match_max_dist: float = 400.0,  # 弱匹配/贪婪匹配最大距离（像素）
        # 防抖参数
        deadzone_px: float = 3.0,  # 死区阈值（bbox 中心移动小于此值不更新）
        shake_purge_threshold: float = 150.0,  # 剧烈晃动阈值（像素/帧），超过此值时清空所有 Lost 目标
        # 自适应平滑参数
        adaptive_lerp_threshold: float = 50.0,  # 位移超过此值（像素）时，lerp_alpha 强制设为 1.0（不平滑，直接跟进）
        # 其他
        max_skip_frames: int = 10,  # 连续失败后强制重新检测的帧数
        dashed_line_length: int = 10,  # 虚线线段长度（像素）
        debug: bool = False,
    ):
        self.detector = detector
        self.screen_width = screen_width
        self.screen_height = screen_height

        # 参数
        self.default_detect_interval = detect_interval
        self.detect_interval = detect_interval  # 当前动态调整后的间隔
        self.lerp_alpha = lerp_alpha
        self.confirm_frames = confirm_frames
        self.lost_tolerance = lost_tolerance
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

        # 防抖参数
        self.deadzone_px = deadzone_px
        self.shake_purge_threshold = shake_purge_threshold

        # 自适应平滑参数
        self.adaptive_lerp_threshold = adaptive_lerp_threshold

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

        # 返回非 Destroy 状态的目标
        return [t for t in self._targets if t.state != "destroy"]

    def _match_and_update(self, detections: List[DetectionResult]) -> None:
        """匹配检测结果与跟踪目标，并更新状态"""
        # 提取检测框
        det_boxes = [(d.x1, d.y1, d.x2, d.y2, d.confidence, d.class_id) for d in detections]

        # 构建 IoU 矩阵
        tracked_boxes = [(t.track_id, t.bbox) for t in self._targets if t.state != "destroy"]

        # 当前有跟踪目标但没有新检测：所有目标进入丢失处理
        if not det_boxes and tracked_boxes:
            self._handle_all_lost()
            return

        # 无跟踪目标但有新检测：创建新目标
        if not tracked_boxes and det_boxes:
            self._create_new_targets(det_boxes)
            return

        # 两者都为空：无操作
        if not det_boxes and not tracked_boxes:
            return

        # 计算 IoU 矩阵和中心点距离矩阵
        iou_matrix = np.zeros((len(tracked_boxes), len(det_boxes)))
        dist_matrix = np.zeros((len(tracked_boxes), len(det_boxes)))

        for i, (_, t_box) in enumerate(tracked_boxes):
            t_cx = (t_box[0] + t_box[2]) / 2
            t_cy = (t_box[1] + t_box[3]) / 2

            for j, d_box in enumerate(det_boxes):
                # 计算 IoU
                iou_matrix[i, j] = calc_iou(t_box, d_box[:4])

                # 计算中心点距离
                d_cx = (d_box[0] + d_box[2]) / 2
                d_cy = (d_box[1] + d_box[3]) / 2
                dist = ((t_cx - d_cx) ** 2 + (t_cy - d_cy) ** 2) ** 0.5
                dist_matrix[i, j] = dist

                if self.debug and (iou_matrix[i, j] > 0 or dist < 100):
                    logger.debug(
                        f"匹配候选: track={tracked_boxes[i][0]} det={j} "
                        f"iou={iou_matrix[i, j]:.3f} dist={dist:.1f}px"
                    )

        # 匈牙利算法匹配（优先使用中心点距离）
        matched_pairs = self._hungarian_match_by_distance(
            dist_matrix, iou_matrix, len(tracked_boxes), len(det_boxes)
        )

        # 判断匹配是否有效（宽松条件）
        def is_similar_enough(track_box, det_box, iou_val, dist_val):
            """判断两个框是否足够相似（优先中心点距离）"""
            # 中心点距离在 strong_match_dist 内 → 强匹配
            if dist_val < self.strong_match_dist:
                return True
            # IoU >= weak_match_iou 且距离 < weak_match_max_dist → 弱匹配
            if iou_val >= self.weak_match_iou and dist_val < self.weak_match_max_dist:
                return True
            return False

        if self.debug and matched_pairs:
            logger.debug(f"匹配结果: {len(matched_pairs)} 对")

        # 标记已匹配
        matched_det_indices = set()
        matched_track_indices = set()

        for track_idx, det_idx in matched_pairs:
            iou_val = iou_matrix[track_idx, det_idx]
            dist_val = dist_matrix[track_idx, det_idx]
            if is_similar_enough(tracked_boxes[track_idx][1], det_boxes[det_idx][:4], iou_val, dist_val):
                matched_track_indices.add(track_idx)
                matched_det_indices.add(det_idx)
                self._update_target(
                    tracked_boxes[track_idx][0],
                    det_boxes[det_idx]
                )
                if self.debug:
                    logger.debug(
                        f"匹配成功: track={tracked_boxes[track_idx][0]} "
                        f"iou={iou_val:.3f} dist={dist_val:.1f}px"
                    )

        # 未匹配的检测 → 新目标
        for j, det_box in enumerate(det_boxes):
            if j not in matched_det_indices:
                self._create_single_target(det_box)

        # 未匹配的跟踪目标 → 丢失
        for i, (track_id, _) in enumerate(tracked_boxes):
            if i not in matched_track_indices:
                self._mark_target_lost(track_id)

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

                # 死区：bbox 中心移动小于 deadzone_px 时不更新，消除静止目标抖动
                old_bbox = target.bbox
                old_cx = (old_bbox[0] + old_bbox[2]) / 2
                old_cy = (old_bbox[1] + old_bbox[3]) / 2
                new_cx = (new_bbox[0] + new_bbox[2]) / 2
                new_cy = (new_bbox[1] + new_bbox[3]) / 2
                dist = ((new_cx - old_cx) ** 2 + (new_cy - old_cy) ** 2) ** 0.5
                if dist < self.deadzone_px:
                    return

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

                # 状态转移
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

                break

    def _mark_target_lost(self, track_id: int) -> None:
        """标记目标丢失"""
        for target in self._targets:
            if target.track_id == track_id:
                if target.state == "candidate":
                    # 候选目标也给丢失容错，避免因单帧漏检立即销毁
                    target.lost_count += 1
                    if target.lost_count >= self.lost_tolerance:
                        target.state = "destroy"
                elif target.state == "active":
                    # 活跃目标进入 lost 状态
                    target.state = "lost"
                    target.lost_count = 1
                elif target.state == "lost":
                    # 继续丢失
                    target.lost_count += 1
                    if target.lost_count >= self.lost_tolerance:
                        target.state = "destroy"
                break

    def _handle_all_lost(self) -> None:
        """处理所有目标丢失（无新检测结果时调用）"""
        for target in self._targets:
            if target.state == "candidate":
                target.lost_count += 1
                if target.lost_count >= self.lost_tolerance:
                    target.state = "destroy"
            elif target.state == "active":
                target.state = "lost"
                target.lost_count = 1
            elif target.state == "lost":
                target.lost_count += 1
                if target.lost_count >= self.lost_tolerance:
                    target.state = "destroy"

        # 清理 destroy 状态的目标
        self._targets = [t for t in self._targets if t.state != "destroy"]

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
                if target.lost_count >= self.lost_tolerance:
                    target.state = "destroy"
                    if self.debug:
                        logger.debug(f"目标 ID={target.track_id} Lost 超时，销毁")

    def _cleanup_destroyed_targets(self) -> None:
        """清理 Destroy 状态的目标"""
        self._targets = [t for t in self._targets if t.state != "destroy"]