#!/usr/bin/env python3
"""
目标验证模块
多周期确认机制 — 防止误判，确保目标真实存在且稳定
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from src.core.detection import DetectionResult
from src.core.target_scoring import TargetScore, TargetScorer
from src.logger import get_logger


class TargetVerifier:
    """
    多周期目标验证器

    工作原理：
    1. 每个检测周期调用 process_cycle() 传入当前检测结果
    2. 验证器追踪最高优先级目标的连续出现次数
    3. 当连续出现次数达到 required_cycles 时，返回验证通过
    4. 如果目标消失，计数器重置
    """

    def __init__(self, required_cycles: int, debug: bool = False):
        """
        Args:
            required_cycles: 需要连续检测到的周期数
            debug: 调试模式
        """
        self.required_cycles = required_cycles
        self.debug = debug
        self.logger = get_logger(debug=debug)

        # 当前连续计数（针对正在验证的目标）
        self._consecutive_count = 0
        # 当前正在验证的最高优先级目标
        self._current_target: Optional[TargetScore] = None

    @property
    def is_verifying(self) -> bool:
        """是否正在验证某个目标"""
        return self._current_target is not None and self._consecutive_count > 0

    @property
    def verification_progress(self) -> int:
        """当前验证进度（已确认周期数）"""
        return self._consecutive_count

    @property
    def current_target(self) -> Optional[TargetScore]:
        """当前正在验证的目标"""
        return self._current_target

    def process_cycle(
        self,
        scored_detections: List[TargetScore],
    ) -> Tuple[bool, Optional[TargetScore]]:
        """
        处理单个检测周期

        Args:
            scored_detections: 已评分和排序的目标列表

        Returns:
            (verified, target): verified 为 True 时表示有目标验证通过
        """
        if not scored_detections:
            # 当前周期没有检测到任何目标
            if self._current_target is not None:
                self.logger.info(
                    f"验证中断: 目标消失 (进度 {self._consecutive_count}/{self.required_cycles})"
                )
            self._current_target = None
            self._consecutive_count = 0
            return False, None

        # 取最高优先级目标
        top_target = scored_detections[0]

        if self._current_target is None:
            # 开始验证新目标
            self._current_target = top_target
            self._consecutive_count = 1
            if self.debug:
                self.logger.debug_msg(
                    f"开始验证目标: 优先级={top_target.priority_rank}, "
                    f"距离={top_target.distance_to_center:.0f}px, "
                    f"面积={top_target.bbox_area:.0f}px², "
                    f"状态={top_target.distance_state} "
                    f"(进度 1/{self.required_cycles})"
                )
        elif self._matches_target(top_target, self._current_target):
            # 同一个目标继续出现
            self._consecutive_count += 1
            if self.debug:
                self.logger.debug_msg(
                    f"目标连续出现: 进度 {self._consecutive_count}/{self.required_cycles}"
                )
        else:
            # 目标切换，重置计数
            self.logger.info(
                f"目标切换: 旧优先级={self._current_target.priority_rank} "
                f"→ 新优先级={top_target.priority_rank}，重置计数"
            )
            self._current_target = top_target
            self._consecutive_count = 1

        # 检查是否验证通过
        if self._consecutive_count >= self.required_cycles:
            verified_target = self._current_target
            self.logger.success(
                f"目标验证通过! 优先级={verified_target.priority_rank}, "
                f"距离={verified_target.distance_to_center:.0f}px, "
                f"面积={verified_target.bbox_area:.0f}px², "
                f"状态={verified_target.distance_state}"
            )
            self._consecutive_count = 0
            self._current_target = None
            return True, verified_target

        return False, self._current_target

    def reset(self):
        """重置验证状态"""
        self._current_target = None
        self._consecutive_count = 0

    @staticmethod
    def _matches_target(a: TargetScore, b: TargetScore, tolerance: float = 50.0) -> bool:
        """判断两个检测是否指向同一个目标。

        使用中心点距离 + bbox 面积相似度判断。

        tolerance 选择依据：
        - 中心距离容差 50px：YOLO 检测小目标时存在约 20-40px 抖动，
          50px 可容纳抖动又不会把不同目标误判为同一目标
        - 面积容差 100px²：bbox 面积在相邻帧间波动约 10-30%，
          对于 100-500px² 的小目标，100px² 可覆盖正常波动
        - 如频繁重置计数，可调大 tolerance 至 80-100
        """
        center_dist = (
            (a.detection.center[0] - b.detection.center[0]) ** 2
            + (a.detection.center[1] - b.detection.center[1]) ** 2
        ) ** 0.5
        area_diff = abs(a.bbox_area - b.bbox_area)

        return center_dist < tolerance and area_diff < tolerance * 2
