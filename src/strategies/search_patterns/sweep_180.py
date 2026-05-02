#!/usr/bin/env python3
"""
180 度水平来回扫模式：从左到右再从右到左。
用于固定镜头寻找模式。
"""

from __future__ import annotations

import random

from src.strategies.base import Action
from src.strategies.search_patterns.base_pattern import BaseSearchPattern, SearchCommand


class Sweep180Pattern(BaseSearchPattern):
    name = "sweep_180"

    def __init__(
        self,
        min_segments: int = 3,
        max_segments: int = 4,
        px_per_degree: float = 6.0,
    ) -> None:
        super().__init__()
        self.min_segments = min_segments
        self.max_segments = max_segments
        self.px_per_degree = px_per_degree
        self._commands: list[SearchCommand] = []
        self._index = 0

    def reset(self) -> None:
        super().reset()
        self._index = 0
        self._commands = []

        seg_count = random.randint(self.min_segments, self.max_segments)

        # 第一趟：从左到右 180 度
        raw = [random.uniform(40.0, 65.0) for _ in range(seg_count)]
        total = sum(raw)
        first_sweep = [x * (180.0 / total) for x in raw]

        # 第二趟：从右到左 180 度（反向）
        raw2 = [random.uniform(40.0, 65.0) for _ in range(seg_count)]
        total2 = sum(raw2)
        second_sweep = [x * (180.0 / total2) for x in raw2]

        # 构建命令列表
        for degrees in first_sweep:
            dx = int(degrees * self.px_per_degree)
            pause_s = random.uniform(0.3, 0.5)
            self._commands.append(SearchCommand(
                action=Action.SEARCH_MOUSE,
                params={"dx": dx, "dy": 0, "pause_s": pause_s},
                label="sweep_180_right",
            ))

        # 两趟之间短暂停顿
        self._commands.append(SearchCommand(
            action=Action.NO_OP,
            params={"pause_s": random.uniform(0.5, 1.0)},
            label="sweep_180_pause",
        ))

        for degrees in second_sweep:
            dx = -int(degrees * self.px_per_degree)  # 反向
            pause_s = random.uniform(0.3, 0.5)
            self._commands.append(SearchCommand(
                action=Action.SEARCH_MOUSE,
                params={"dx": dx, "dy": 0, "pause_s": pause_s},
                label="sweep_180_left",
            ))

    def next_command(self, ctx) -> SearchCommand:
        if not self._commands:
            self.reset()

        if self._index >= len(self._commands):
            self._finished = True
            return SearchCommand(action=Action.NO_OP, label="sweep_180_finished")

        cmd = self._commands[self._index]
        self._index += 1

        if hasattr(ctx, "logger") and ctx.logger:
            dx = cmd.params.get("dx", 0)
            ctx.logger.debug_msg(
                f"[Sweep180] {self._index}/{len(self._commands)}, dx={dx}"
            )

        return cmd
