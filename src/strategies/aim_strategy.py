#!/usr/bin/env python3
"""
瞄准策略
处理鼠标瞄准精灵中心并触发投掷的逻辑
"""

from typing import TYPE_CHECKING, Optional, Tuple

from src.strategies.base import BaseStrategy, Action
from src.utils.math_utils import center_offset

if TYPE_CHECKING:
    from src.core.context import AppContext


class AimStrategy(BaseStrategy):
    """
    瞄准策略 — 鼠标怎么瞄准精灵中心并投掷

    核心逻辑：
    - 计算目标中心到屏幕中心的偏移量
    - 返回 THROW 动作，由 state_machine 调用 aim_and_throw()
    - 必须在精灵球界面下才能执行
    """

    def __init__(self, max_throws: int = 5):
        """
        初始化瞄准策略

        Args:
            max_throws: 最大投掷次数
        """
        self.max_throws = max_throws

    def execute(self, ctx: "AppContext") -> Action:
        """
        执行瞄准策略

        Args:
            ctx: 应用上下文

        Returns:
            Action.PRESS_E 如果需要按 E 进入捕捉模式
            Action.THROW 如果可以投掷
            Action.NO_OP 如果无法执行
        """
        # 检查是否有已验证的目标
        if not ctx.verified_target:
            ctx.logger.debug("没有已验证的目标，无法瞄准")
            return Action.NO_OP

        # 检查投掷次数
        if ctx.throw_count >= self.max_throws:
            ctx.logger.warning(f"已达到最大投掷次数（{self.max_throws}），停止")
            return Action.NO_OP

        # 检查是否在精灵球界面
        if not ctx.is_capture_mode:
            ctx.logger.debug("不在精灵球界面，需要按 E")
            return Action.PRESS_E

        # 获取目标中心点
        target_center = self._get_target_center(ctx.verified_target)
        if not target_center:
            ctx.logger.warning("无法获取目标中心点")
            return Action.NO_OP

        # 计算偏移
        offset_x, offset_y = center_offset(
            target_center,
            ctx.frame_width,
            ctx.frame_height
        )

        ctx.logger.debug(
            f"瞄准: 目标中心={target_center}, 偏移=({offset_x}, {offset_y}), "
            f"投掷次数={ctx.throw_count}/{self.max_throws}"
        )

        # 返回投掷动作
        return Action.THROW

    def get_aim_parameters(
        self,
        ctx: "AppContext"
    ) -> Optional[Tuple[int, int]]:
        """
        获取瞄准参数（供状态机调用）

        Args:
            ctx: 应用上下文

        Returns:
            (target_x, target_y) - 目标中心坐标
            None 如果无法计算
        """
        if not ctx.verified_target:
            return None

        target_center = self._get_target_center(ctx.verified_target)
        if not target_center:
            return None

        return target_center

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
