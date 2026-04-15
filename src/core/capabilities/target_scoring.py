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
        max_distance_threshold: float = 2000.0,   # bbox 面积 < 2000 → FAR（远）
        near_threshold: float = 8000.0,           # bbox 面积 2000~8000 → MEDIUM（中距）
        capture_threshold: float = 15000.0,       # bbox 面积 > 8000 → CLOSE（可丢球）
        center_offset_x: int = 0,
        center_offset_y: int = 0,
        distance_k: float = 72000.0,              # 距离常数 k = D * h，基于 720p 分辨率校准
    ):
        self._center_x = screen_width / 2 + center_offset_x
        self._center_y = screen_height / 2 + center_offset_y
        self._max_distance_threshold = max_distance_threshold
        self._near_threshold = near_threshold
        self._capture_threshold = capture_threshold
        self._distance_k = distance_k

    @property
    def screen_center(self) -> Tuple[float, float]:
        return (self._center_x, self._center_y)

    def calculate_distance_to_center(self, detection: DetectionResult) -> float:
        """计算目标中心到屏幕中心的欧氏距离"""
        cx, cy = detection.center
        dx = cx - self._center_x
        dy = cy - self._center_y
        return (dx * dx + dy * dy) ** 0.5

    def classify_distance(self, bbox_area: float) -> str:
        """根据 bbox 面积判断距离状态"""
        if bbox_area < self._max_distance_threshold:
            return "FAR"
        elif bbox_area < self._near_threshold:
            return "MEDIUM"
        else:
            return "CLOSE"

    def estimate_distance(self, pixel_height: float) -> float:
        """
        基于像素高度估算距离（相似三角形原理）
        Distance = k / pixel_height
        k 值通过已知距离和像素高度校准：k = D_known * h_known
        返回相对距离单位，值越大表示越远
        """
        if pixel_height <= 0:
            return float('inf')
        return self._distance_k / pixel_height

    def score_detections(self, detections: List[DetectionResult]) -> List[TargetScore]:
        """
        对一批检测结果进行评分和排序
        按距屏幕中心距离升序排列（最近的排第一）
        """
        if not detections:
            return []

        scored = []
        for det in detections:
            dist = self.calculate_distance_to_center(det)
            area = float(det.area)
            state = self.classify_distance(area)
            # 计算估算距离（基于像素高度）
            bbox_height = float(det.y2 - det.y1)
            est_dist = self.estimate_distance(bbox_height)
            scored.append(TargetScore(
                detection=det,
                distance_to_center=dist,
                bbox_area=area,
                distance_state=state,
                priority_rank=0,  # 暂占位
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
