#!/usr/bin/env python3
"""
搜索策略调度器
将搜索行为升级为多模式调度：
- Micro Look: 原地小幅随机看
- Sweep 360: 分段环顾
- Circular Patrol: W前进+转向+回位（摄像机导向）
"""

import time
from typing import TYPE_CHECKING

from src.strategies.base import BaseStrategy, Action
from src.strategies.search_patterns.base_pattern import SearchCommand
from src.strategies.search_patterns.micro_look import MicroLookPattern
from src.strategies.search_patterns.sweep_360 import Sweep360Pattern
from src.strategies.search_patterns.circular_patrol import CircularPatrolPattern

if TYPE_CHECKING:
    from src.core.context import AppContext


class SearchStrategy(BaseStrategy):
    """多模式搜索调度器。"""

    def __init__(
        self,
        pan_angle: float = 5.0,
        max_pan_cycles: int = 6,
        micro_cycles_before_upgrade: int = 2,
        legacy_mouse_action: bool = True,
    ):
        self.micro_cycles_before_upgrade = micro_cycles_before_upgrade
        self.legacy_mouse_action = legacy_mouse_action

        self._patterns = [
            MicroLookPattern(),
            Sweep360Pattern(),
            CircularPatrolPattern(),
        ]
        self._pattern_index = 0
        self._micro_cycle_count = 0
        self._last_command = SearchCommand(action=Action.NO_OP, params={}, label="init")
        self._idle_until = 0.0

        # 兼容旧测试/调用方的字段
        self.pan_angle = pan_angle
        self.max_pan_cycles = max_pan_cycles
        self.current_cycle = 0
        self.pan_direction = 1
        self._legacy_toggle = 1

        self._patterns[self._pattern_index].reset()

    def execute(self, ctx: "AppContext") -> Action:
        # 检测到目标时立即让权，并重置搜索状态
        if ctx.detections and len(ctx.detections) > 0:
            ctx.logger.debug_msg("检测到精灵，停止搜索")
            self._reset_search_state()
            self._last_command = SearchCommand(action=Action.NO_OP, params={}, label="target_detected")
            return Action.NO_OP

        # 巡逻后的 idle 窗口
        now = time.time()
        if now < self._idle_until:
            self._last_command = SearchCommand(
                action=Action.NO_OP,
                params={"pause_s": max(0.0, self._idle_until - now)},
                label="idle",
            )
            return Action.NO_OP

        current = self._patterns[self._pattern_index]
        command = current.next_command(ctx)

        if current.is_finished():
            if current.name == "micro_look":
                self._micro_cycle_count += 1
                # micro 模式允许执行两轮再升级 sweep
                if self._micro_cycle_count < self.micro_cycles_before_upgrade:
                    current.reset()
                else:
                    self._pattern_index = 1
                    self._patterns[self._pattern_index].reset()
            elif current.name == "sweep_360":
                self._pattern_index = 2
                self._patterns[self._pattern_index].reset()
            else:
                # patrol 完成后 idle，再回到 micro
                pause_s = float(command.params.get("pause_s", 1.2)) if command.action == Action.NO_OP else 1.2
                self._idle_until = time.time() + min(2.0, max(1.0, pause_s))
                self._pattern_index = 0
                self._micro_cycle_count = 0
                self._patterns[self._pattern_index].reset()

        self._last_command = command

        action = command.action
        if action == Action.SEARCH_MOUSE and self.legacy_mouse_action:
            # 保留旧语义：鼠标搜索可映射为 SEARCH_PAN
            self._legacy_toggle *= -1
            self.pan_direction = self._legacy_toggle
            if self.pan_direction == 1:
                self.current_cycle += 1
            return Action.SEARCH_PAN

        return action

    def _reset_search_state(self) -> None:
        self._pattern_index = 0
        self._micro_cycle_count = 0
        self._idle_until = 0.0
        for pattern in self._patterns:
            pattern.reset()

        self.current_cycle = 0
        self.pan_direction = 1
        self._legacy_toggle = 1

    def get_pan_parameters(self) -> tuple[float, int]:
        # 兼容旧调用方：基于最近一次命令推导左右方向
        if self._last_command.action in (Action.SEARCH_MOUSE, Action.SEARCH_PAN):
            dx = int(self._last_command.params.get("dx", 0))
            if dx != 0:
                self.pan_direction = 1 if dx > 0 else -1
        return self.pan_angle, self.pan_direction

    def get_search_command(self) -> SearchCommand:
        """获取最近一次搜索命令参数。"""
        return self._last_command
