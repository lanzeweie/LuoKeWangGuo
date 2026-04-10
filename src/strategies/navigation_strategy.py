#!/usr/bin/env python3
"""
导航策略
处理 WASD 靠近精灵的逻辑
"""

import time
from typing import TYPE_CHECKING, Optional, Tuple

from src.strategies.base import BaseStrategy, Action
from src.utils.math_utils import center_offset, distance

if TYPE_CHECKING:
    from src.core.context import AppContext


class NavigationStrategy(BaseStrategy):
    """
    导航策略 — WASD 怎么走近精灵

    核心逻辑：
    - 根据目标在屏幕中的偏移量决定 WASD 方向
    - 分两阶段：远距离快速靠近 → 近距离精细调整
    - 目标在 CENTER_TOLERANCE（150px）范围内 → 返回 NO_OP
    """

    def __init__(
        self,
        center_tolerance: int = 150,
        far_threshold: int = 300,
        timeout_seconds: float = 15.0
    ):
        """
        初始化导航策略

        Args:
            center_tolerance: 中心容差（像素），目标在此范围内认为已到达
            far_threshold: 远距离阈值（像素），超过此距离使用快速移动
            timeout_seconds: 导航超时时间（秒）
        """
        self.center_tolerance = center_tolerance
        self.far_threshold = far_threshold
        self.timeout_seconds = timeout_seconds
        self.navigation_start_time: Optional[float] = None

    def execute(self, ctx: "AppContext") -> Action:
        """
        执行导航策略

        Args:
            ctx: 应用上下文

        Returns:
            Action.NO_OP 如果目标在中心范围内
            Action.MOVE_WASD 如果需要移动
        """
        # 检查是否有已验证的目标
        if not ctx.verified_target:
            ctx.logger.debug("没有已验证的目标，停止导航")
            self._reset_navigation_state()
            return Action.NO_OP

        # 获取目标中心点
        target_center = self._get_target_center(ctx.verified_target)
        if not target_center:
            ctx.logger.warning("无法获取目标中心点")
            return Action.NO_OP

        # 计算目标相对于屏幕中心的偏移
        offset_x, offset_y = center_offset(
            target_center,
            ctx.frame_width,
            ctx.frame_height
        )

        # 计算距离
        screen_center = ctx.screen_center
        dist = distance(screen_center, target_center)

        ctx.logger.debug(
            f"导航: 目标偏移=({offset_x}, {offset_y}), 距离={dist:.1f}px"
        )

        # 如果目标在中心容差范围内，停止移动
        if dist <= self.center_tolerance:
            ctx.logger.debug(f"目标在中心范围内（{dist:.1f}px <= {self.center_tolerance}px），停止导航")
            self._reset_navigation_state()
            return Action.NO_OP

        # 检查超时
        if self.navigation_start_time is None:
            self.navigation_start_time = time.time()
        elif time.time() - self.navigation_start_time > self.timeout_seconds:
            ctx.logger.warning(f"导航超时（{self.timeout_seconds}s），停止")
            self._reset_navigation_state()
            return Action.NO_OP

        # 返回移动动作
        return Action.MOVE_WASD

    def get_movement_parameters(
        self,
        ctx: "AppContext"
    ) -> Optional[Tuple[str, float]]:
        """
        获取移动参数（供状态机调用）

        Args:
            ctx: 应用上下文

        Returns:
            (direction, duration) - 移动方向和持续时间
            None 如果无法计算
        """
        if not ctx.verified_target:
            return None

        target_center = self._get_target_center(ctx.verified_target)
        if not target_center:
            return None

        # 计算偏移
        offset_x, offset_y = center_offset(
            target_center,
            ctx.frame_width,
            ctx.frame_height
        )

        # 计算距离
        screen_center = ctx.screen_center
        dist = distance(screen_center, target_center)

        # 确定主要移动方向
        if abs(offset_x) > abs(offset_y):
            # 水平移动为主
            direction = 'd' if offset_x > 0 else 'a'
        else:
            # 垂直移动为主
            direction = 's' if offset_y > 0 else 'w'

        # 根据距离计算移动时长
        if dist > self.far_threshold:
            # 远距离：快速移动
            duration = 0.5
        else:
            # 近距离：精细调整
            duration = 0.3

        ctx.logger.debug(
            f"移动参数: 方向={direction}, 时长={duration}s, 距离={dist:.1f}px"
        )

        return direction, duration

    def _get_target_center(self, target) -> Optional[Tuple[int, int]]:
        """
        获取目标中心点

        Args:
            target: 目标对象（DetectionResult 或类似结构）

        Returns:
            (center_x, center_y) 或 None
        """
        try:
            # 尝试从 bbox 计算中心
            if hasattr(target, 'bbox'):
                x1, y1, x2, y2 = target.bbox
                center_x = int((x1 + x2) / 2)
                center_y = int((y1 + y2) / 2)
                return center_x, center_y
            # 尝试直接获取 center 属性
            elif hasattr(target, 'center'):
                return target.center
        except Exception:
            pass
        return None

    def _reset_navigation_state(self) -> None:
        """重置导航状态"""
        self.navigation_start_time = None
