#!/usr/bin/env python3
"""
搜索策略
处理画面中没精灵时的小范围平移搜索逻辑
"""

from typing import TYPE_CHECKING

from src.strategies.base import BaseStrategy, Action

if TYPE_CHECKING:
    from src.core.context import AppContext


class SearchStrategy(BaseStrategy):
    """
    搜索策略 — 画面中没精灵时，决定屏幕怎么移动来寻找精灵

    核心逻辑：
    - 检测到精灵 → 返回 NO_OP，交给验证层
    - 没精灵 → 返回 SEARCH_PAN（小幅平移鼠标方向）
    - 每次平移固定角度（如 5°），左右交替
    """

    def __init__(self, pan_angle: float = 5.0, max_pan_cycles: int = 6):
        """
        初始化搜索策略

        Args:
            pan_angle: 每次平移的角度（度）
            max_pan_cycles: 最大平移周期数（左右各算一次）
        """
        self.pan_angle = pan_angle
        self.max_pan_cycles = max_pan_cycles
        self.current_cycle = 0
        self.pan_direction = 1  # 1 = 右, -1 = 左

    def execute(self, ctx: "AppContext") -> Action:
        """
        执行搜索策略

        Args:
            ctx: 应用上下文

        Returns:
            Action.NO_OP 如果检测到精灵
            Action.SEARCH_PAN 如果需要平移搜索
        """
        # 如果检测到精灵，停止搜索
        if ctx.detections and len(ctx.detections) > 0:
            ctx.logger.debug_msg("检测到精灵，停止搜索")
            self._reset_search_state()
            return Action.NO_OP

        # 如果已经平移了太多次，重置并暂停
        if self.current_cycle >= self.max_pan_cycles:
            ctx.logger.debug_msg(f"已完成 {self.max_pan_cycles} 个搜索周期，重置")
            self._reset_search_state()
            return Action.NO_OP

        # 执行平移搜索
        ctx.logger.debug_msg(
            f"执行平移搜索: 方向={'右' if self.pan_direction > 0 else '左'}, "
            f"角度={self.pan_angle}°, 周期={self.current_cycle}/{self.max_pan_cycles}"
        )

        # 切换方向（左右交替）
        self.pan_direction *= -1
        if self.pan_direction == 1:
            # 完成一个完整周期（左 + 右）
            self.current_cycle += 1

        return Action.SEARCH_PAN

    def _reset_search_state(self) -> None:
        """重置搜索状态"""
        self.current_cycle = 0
        self.pan_direction = 1

    def get_pan_parameters(self) -> tuple[float, int]:
        """
        获取平移参数（供状态机调用）

        Returns:
            (angle, direction) - 平移角度和方向
        """
        return self.pan_angle, self.pan_direction
