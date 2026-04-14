#!/usr/bin/env python3
"""
画圈徘徊模式：多边形短步 + 视线跟随 + 航位推算回位。
"""

from __future__ import annotations

import random
from collections import deque

from src.strategies.base import Action
from src.strategies.search_patterns.base_pattern import BaseSearchPattern, SearchCommand


class CircularPatrolPattern(BaseSearchPattern):
    name = "circular_patrol"

    def __init__(
        self,
        base_steps: int = 8,
        min_duration: float = 0.22,
        max_duration: float = 0.55,
    ) -> None:
        super().__init__()
        self.base_steps = base_steps
        self.min_duration = min_duration
        self.max_duration = max_duration
        self._commands: deque[SearchCommand] = deque()
        self._virtual_x = 0.0
        self._virtual_y = 0.0

    def reset(self) -> None:
        super().reset()
        self._commands.clear()
        self._virtual_x = 0.0
        self._virtual_y = 0.0
        self._build_patrol_commands()

    def _append_move(self, direction: str, duration: float, look_dx: int) -> None:
        if direction == "w":
            self._virtual_y += duration
        elif direction == "s":
            self._virtual_y -= duration
        elif direction == "d":
            self._virtual_x += duration
        elif direction == "a":
            self._virtual_x -= duration

        self._commands.append(
            SearchCommand(
                action=Action.SEARCH_MOVE,
                params={
                    "direction": direction,
                    "duration": duration,
                    "look_dx": look_dx,
                    "look_dy": 0,
                    "pause_s": random.uniform(0.10, 0.25),
                },
                label="circular_patrol_move",
            )
        )

    def _build_patrol_commands(self) -> None:
        sequence = ["w", "d", "d", "s", "s", "a", "a", "w"]
        steps = max(self.base_steps, len(sequence))

        for i in range(steps):
            direction = sequence[i % len(sequence)]
            duration = random.uniform(self.min_duration, self.max_duration)
            look_dx = random.randint(8, 24)
            if direction in ("a", "w"):
                look_dx = -look_dx
            self._append_move(direction=direction, duration=duration, look_dx=look_dx)

        # 回位：根据虚拟位移反向补偿
        if self._virtual_y > 0:
            self._commands.append(
                SearchCommand(
                    action=Action.SEARCH_MOVE,
                    params={
                        "direction": "s",
                        "duration": min(0.8, self._virtual_y),
                        "look_dx": 0,
                        "look_dy": 0,
                        "pause_s": random.uniform(0.10, 0.20),
                    },
                    label="return_origin_y",
                )
            )
        elif self._virtual_y < 0:
            self._commands.append(
                SearchCommand(
                    action=Action.SEARCH_MOVE,
                    params={
                        "direction": "w",
                        "duration": min(0.8, abs(self._virtual_y)),
                        "look_dx": 0,
                        "look_dy": 0,
                        "pause_s": random.uniform(0.10, 0.20),
                    },
                    label="return_origin_y",
                )
            )

        if self._virtual_x > 0:
            self._commands.append(
                SearchCommand(
                    action=Action.SEARCH_MOVE,
                    params={
                        "direction": "a",
                        "duration": min(0.8, self._virtual_x),
                        "look_dx": 0,
                        "look_dy": 0,
                        "pause_s": random.uniform(0.10, 0.20),
                    },
                    label="return_origin_x",
                )
            )
        elif self._virtual_x < 0:
            self._commands.append(
                SearchCommand(
                    action=Action.SEARCH_MOVE,
                    params={
                        "direction": "d",
                        "duration": min(0.8, abs(self._virtual_x)),
                        "look_dx": 0,
                        "look_dy": 0,
                        "pause_s": random.uniform(0.10, 0.20),
                    },
                    label="return_origin_x",
                )
            )

        self._commands.append(
            SearchCommand(
                action=Action.NO_OP,
                params={"pause_s": random.uniform(1.0, 2.0)},
                label="patrol_idle",
            )
        )

    def next_command(self, ctx) -> SearchCommand:
        if not self._commands:
            self._finished = True
            return SearchCommand(action=Action.NO_OP, label="circular_patrol_finished")

        cmd = self._commands.popleft()
        if not self._commands:
            self._finished = True

        if hasattr(ctx, "logger") and ctx.logger:
            ctx.logger.debug_msg(f"[CircularPatrol] label={cmd.label}, params={cmd.params}")

        return cmd
