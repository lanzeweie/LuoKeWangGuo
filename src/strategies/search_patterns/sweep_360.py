#!/usr/bin/env python3
"""
360 分段环顾模式：分扇区转头 + 停顿。
"""

from __future__ import annotations

import random

from src.strategies.base import Action
from src.strategies.search_patterns.base_pattern import BaseSearchPattern, SearchCommand


class Sweep360Pattern(BaseSearchPattern):
    name = "sweep_360"

    def __init__(
        self,
        min_segments: int = 4,
        max_segments: int = 6,
        px_per_degree: float = 6.0,
    ) -> None:
        super().__init__()
        self.min_segments = min_segments
        self.max_segments = max_segments
        self.px_per_degree = px_per_degree
        self._segments: list[float] = []
        self._index = 0

    def reset(self) -> None:
        super().reset()
        self._index = 0
        seg_count = random.randint(self.min_segments, self.max_segments)
        # 先随机分配，再归一化到 360 度
        raw = [random.uniform(35.0, 95.0) for _ in range(seg_count)]
        total = sum(raw)
        self._segments = [x * (360.0 / total) for x in raw]

    def next_command(self, ctx) -> SearchCommand:
        if not self._segments:
            self.reset()

        if self._index >= len(self._segments):
            self._finished = True
            return SearchCommand(action=Action.NO_OP, label="sweep_360_finished")

        degrees = self._segments[self._index]
        dx = int(degrees * self.px_per_degree)
        pause_s = random.uniform(0.3, 0.7)
        self._index += 1

        if hasattr(ctx, "logger") and ctx.logger:
            ctx.logger.debug_msg(
                f"[Sweep360] seg={self._index}/{len(self._segments)}, deg={degrees:.1f}, dx={dx}, pause={pause_s:.2f}s"
            )

        return SearchCommand(
            action=Action.SEARCH_MOUSE,
            params={"dx": dx, "dy": 0, "pause_s": pause_s},
            label="sweep_360",
        )
