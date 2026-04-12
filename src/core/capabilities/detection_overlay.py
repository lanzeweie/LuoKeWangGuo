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


# ── 检测覆盖层类 ──


class DetectionOverlay:
    """检测覆盖层 — 跳帧调度、目标跟踪、插值平滑、绘框输出"""

    def __init__(
        self,
        detector: "ObjectDetector",  # YOLO 检测器
        screen_width: int,
        screen_height: int,
        detect_interval: int = 3,  # 每 N 帧检测一次
        lerp_alpha: float = 0.3,  # 插值平滑系数
        confirm_frames: int = 3,  # 候选→活跃所需帧数
        lost_tolerance: int = 5,  # 丢失容错帧数
        iou_threshold: float = 0.3,  # IoU 匹配阈值
        max_predict_distance: float = 100.0,  # Lost 状态最大预测距离（像素）
        draw_boxes: bool = True,  # 打框开关
        debug: bool = False,
    ):
        self.detector = detector
        self.screen_width = screen_width
        self.screen_height = screen_height

        # 参数
        self.detect_interval = detect_interval
        self.lerp_alpha = lerp_alpha
        self.confirm_frames = confirm_frames
        self.lost_tolerance = lost_tolerance
        self.iou_threshold = iou_threshold
        self.max_predict_distance = max_predict_distance
        self.draw_boxes = draw_boxes
        self.debug = debug

        # 内部状态
        self._frame_count: int = 0
        self._next_track_id: int = 1
        self._targets: List[TrackedTarget] = []  # 跟踪列表（不含 Destroy）
        self._last_detection_results: List[DetectionResult] = []  # 上次检测结果
        self._consecutive_failures: int = 0  # 连续失败计数
        self._max_skip_frames: int = 10  # 强制重新检测阈值

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

        # 判断是否需要运行检测
        should_detect = (self._frame_count % self.detect_interval == 0) or \
                        (self._consecutive_failures >= self._max_skip_frames)

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
        else:
            # 补偿帧：使用上次检测结果（已插值）
            detections = []

        # 目标匹配与状态更新
        self._match_and_update(detections)

        # 返回非 Destroy 状态的目标
        return [t for t in self._targets if t.state != "destroy"]

    def _match_and_update(self, detections: List[DetectionResult]) -> None:
        """匹配检测结果与跟踪目标，并更新状态"""
        # 提取检测框
        det_boxes = [(d.x1, d.y1, d.x2, d.y2, d.confidence, d.class_id) for d in detections]

        # 构建 IoU 矩阵
        tracked_boxes = [(t.track_id, t.bbox) for t in self._targets if t.state != "destroy"]

        if not det_boxes or not tracked_boxes:
            # 无检测结果：所有目标进入丢失处理
            if not det_boxes and self._last_detection_results:
                self._handle_all_lost()
            # 无跟踪目标：创建新目标
            if not tracked_boxes and det_boxes:
                self._create_new_targets(det_boxes)
            return

        # 计算 IoU 矩阵
        iou_matrix = np.zeros((len(tracked_boxes), len(det_boxes)))
        for i, (_, t_box) in enumerate(tracked_boxes):
            for j, d_box in enumerate(det_boxes):
                iou_matrix[i, j] = calc_iou(t_box, d_box[:4])

        # 匈牙利算法匹配
        matched_pairs = self._hungarian_match(iou_matrix, len(tracked_boxes), len(det_boxes))

        # 标记已匹配
        matched_det_indices = set()
        matched_track_indices = set()

        for track_idx, det_idx in matched_pairs:
            if iou_matrix[track_idx, det_idx] >= self.iou_threshold:
                matched_track_indices.add(track_idx)
                matched_det_indices.add(det_idx)
                self._update_target(
                    tracked_boxes[track_idx][0],
                    det_boxes[det_idx]
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

    def _create_new_targets(self, det_boxes: List[Tuple]) -> None:
        """从检测结果创建新目标"""
        for det_box in det_boxes:
            self._create_single_target(det_box)

    def _create_single_target(self, det_box: Tuple) -> None:
        """创建单个新目标"""
        x1, y1, x2, y2, confidence, class_id = det_box
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

    def _update_target(self, track_id: int, det_box: Tuple) -> None:
        """更新已有目标"""
        x1, y1, x2, y2, confidence, class_id = det_box
        new_bbox = (x1, y1, x2, y2)
        new_center = ((x1 + x2) / 2, (y1 + y2) / 2)

        for target in self._targets:
            if target.track_id == track_id:
                # Lerp 插值
                old_bbox = target.bbox
                interpolated_bbox = (
                    old_bbox[0] + (new_bbox[0] - old_bbox[0]) * self.lerp_alpha,
                    old_bbox[1] + (new_bbox[1] - old_bbox[1]) * self.lerp_alpha,
                    old_bbox[2] + (new_bbox[2] - old_bbox[2]) * self.lerp_alpha,
                    old_bbox[3] + (new_bbox[3] - old_bbox[3]) * self.lerp_alpha,
                )

                target.prev_center = target.last_center
                target.last_center = new_center
                target.raw_bbox = new_bbox
                target.bbox = interpolated_bbox
                target.confidence = confidence

                # 状态转移
                if target.state == "candidate":
                    target.confirm_count += 1
                    if target.confirm_count >= self.confirm_frames:
                        target.state = "active"
                elif target.state == "lost":
                    # 重新检测到，恢复为 active
                    target.state = "active"
                    target.lost_count = 0

                break

    def _mark_target_lost(self, track_id: int) -> None:
        """标记目标丢失"""
        for target in self._targets:
            if target.track_id == track_id:
                if target.state == "candidate":
                    # 候选目标直接销毁
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
                # 候选状态不绘框
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
        dash_length: int = 10,
    ) -> None:
        """绘制虚线矩形"""
        import cv2

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
        return self._frame_count % self.detect_interval == 0

    @property
    def active_targets(self) -> List[TrackedTarget]:
        """当前活跃的目标列表"""
        return [t for t in self._targets if t.state == "active"]