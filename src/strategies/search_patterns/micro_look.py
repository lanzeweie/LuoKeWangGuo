#!/usr/bin/env python3
"""
小范围搜寻模式：原地随机看。
"""

from __future__ import annotations

import math
import random

from src.strategies.base import Action
from src.strategies.search_patterns.base_pattern import BaseSearchPattern, SearchCommand


class MicroLookPattern(BaseSearchPattern):
    name = "micro_look"

    def __init__(
        self,
        max_steps: int = 5,
        max_radius: int = 50,
        pause_mu: float = 0.4,
        pause_sigma: float = 0.1,
    ) -> None:
        super().__init__()
        self.max_steps = max_steps
        self.max_radius = max_radius
        self.pause_mu = pause_mu
        self.pause_sigma = pause_sigma
        self._step = 0

    def reset(self) -> None:
        super().reset()
        self._step = 0

    def next_command(self, ctx) -> SearchCommand:
        if self._step >= self.max_steps:
            self._finished = True
            return SearchCommand(action=Action.NO_OP, label="micro_look_finished")

        # 极坐标随机采样，模拟人眼跳视
        radius = random.uniform(self.max_radius * 0.35, self.max_radius)
        theta = random.uniform(0.0, 6.28318530718)
        dx = int(radius * math.cos(theta))
        dy = int(radius * math.sin(theta))

        pause_s = max(0.05, random.gauss(self.pause_mu, self.pause_sigma))
        self._step += 1

        if hasattr(ctx, "logger") and ctx.logger:
            ctx.logger.debug_msg(
                f"[MicroLook] step={self._step}/{self.max_steps}, dx={dx}, dy={dy}, pause={pause_s:.2f}s"
            )

        return SearchCommand(
            action=Action.SEARCH_MOUSE,
            params={"dx": dx, "dy": dy, "pause_s": pause_s},
            label="micro_look",
        )
