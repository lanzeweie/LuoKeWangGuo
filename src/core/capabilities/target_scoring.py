#!/usr/bin/env python3
"""
目标评分模块
负责距离评分、优先级排序、基于 bbox 面积的距离分类
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from src.core.capabilities.detection import DetectionResult


@dataclass(frozen=True)
class TargetScore:
    """目标评分数据（不可变）"""
    detection: DetectionResult
    distance_to_center: float
    bbox_area: float
    distance_state: str  # "FAR", "MEDIUM", "CLOSE"
    priority_rank: int
    estimated_distance: float = 0.0  # 估算距离（相对单位，值越大越远）


class TargetScorer:
    """目标评分器 — 计算距离、分类、排序"""

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        center_offset_x: int = 0,
        center_offset_y: int = 0,
        # 伪距离阈值（值越大表示越远）
        far_threshold: float = 40.0,     # 伪距离 > 40 → FAR
        near_threshold: float = 15.0,    # 伪距离 15~40 → MEDIUM
        # capture_threshold 现在保留但不再用于分类
    ):
        self._center_x = screen_width / 2 + center_offset_x
        self._center_y = screen_height / 2 + center_offset_y
        self._far_threshold = far_threshold
        self._near_threshold = near_threshold

    @property
    def screen_center(self) -> Tuple[float, float]:
        return (self._center_x, self._center_y)

    def calculate_distance_to_center(self, detection: DetectionResult) -> float:
        """计算目标中心到屏幕中心的欧氏距离"""
        cx, cy = detection.center
        dx = cx - self._center_x
        dy = cy - self._center_y
        return (dx * dx + dy * dy) ** 0.5

    # 伪距离常数 k = 1000
    # 效果：贴脸(area~20000)→7，中距(area~5000)→14，远方(area~500)→45
    PSEUDO_DIST_K = 1000.0

    def classify_distance(self, pseudo_dist: float) -> str:
        """根据伪距离判断距离状态（值越大越远）"""
        if pseudo_dist > self._far_threshold:
            return "FAR"
        elif pseudo_dist > self._near_threshold:
            return "MEDIUM"
        else:
            return "CLOSE"

    def estimate_distance(self, bbox_area: float) -> float:
        """
        基于 bbox 面积估算伪距离（值越大表示越远，值越小表示越近）
        使用面积的平方根，能有效抵抗目标待机动画（趴下/伸展）带来的长宽剧烈变化
        """
        if bbox_area <= 0:
            return float('inf')
        return round(self.PSEUDO_DIST_K / (bbox_area ** 0.5), 1)

    def score_detections(self, detections: List[DetectionResult]) -> List[TargetScore]:
        """
        对一批检测结果进行评分和排序
        按伪距离升序排列（越近越靠前）
        """
        if not detections:
            return []

        scored = []
        for det in detections:
            area = float(det.area)
            est_dist = self.estimate_distance(area)
            state = self.classify_distance(est_dist)
            scored.append(TargetScore(
                detection=det,
                distance_to_center=est_dist,  # 复用字段，存伪距离
                bbox_area=area,
                distance_state=state,
                priority_rank=0,
                estimated_distance=est_dist,
            ))

        # 按距离升序排序
        scored.sort(key=lambda s: s.distance_to_center)

        # 写入优先级排名（1-based）
        ranked = []
        for rank, sc in enumerate(scored, start=1):
            ranked.append(TargetScore(
                detection=sc.detection,
                distance_to_center=sc.distance_to_center,
                bbox_area=sc.bbox_area,
                distance_state=sc.distance_state,
                priority_rank=rank,
                estimated_distance=sc.estimated_distance,
            ))

        return ranked
