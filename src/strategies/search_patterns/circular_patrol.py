#!/usr/bin/env python3
"""
摄像机导向巡逻模式：W前进 + 转向调整 + 简单回位。
基于洛克王国等游戏的移动机制，W始终朝向摄像机所指方向前进，
使用A/D键进行转向，避免了无意义的横向移动。
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
        # 只记录W/S的前后位移，A/D用于转向不影响位置
        if direction == "w":
            self._virtual_y += duration
        elif direction == "s":
            self._virtual_y -= duration
        # A/D键用于转向，不记录位置变化

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
        # 基于摄像机方向的移动序列：W前进 + 转向调整
        # 这样更符合游戏的移动机制（W始终朝向摄像机方向）

        # 创建多种巡逻模式
        patterns = [
            # 模式1：简单的左右扫视
            ["w", "w", "turn_right", "w", "w", "turn_left", "w", "turn_left", "w", "w", "turn_right", "w"],
            # 模式2：小范围圆圈
            ["w", "turn_right", "w", "turn_right", "w", "turn_right", "w", "turn_right"],
            # 模式3：探索式前进
            ["w", "w", "turn_right", "w", "turn_left", "w", "w", "turn_left", "w", "turn_right", "w"],
        ]

        # 随机选择一种模式
        sequence = random.choice(patterns)
        steps = max(self.base_steps, len(sequence))

        for i in range(steps):
            action = sequence[i % len(sequence)]

            if action == "w":
                # W前进：朝当前摄像机方向前进
                duration = random.uniform(self.min_duration, self.max_duration)
                # 根据是否是连续的W决定视角调整
                look_dx = random.randint(-8, 8) if i > 0 and sequence[(i-1) % len(sequence)] != "w" else random.randint(-3, 3)
                self._append_move(direction="w", duration=duration, look_dx=look_dx)
                self._virtual_y += duration  # 记录前进距离

            elif action == "turn_right":
                # 右转：原地右转并调整视角
                turn_duration = random.uniform(0.15, 0.30)
                self._commands.append(
                    SearchCommand(
                        action=Action.SEARCH_MOVE,
                        params={
                            "direction": "d",  # 游戏中D通常是右转键
                            "duration": turn_duration,
                            "look_dx": int(turn_duration * 60),  # 根据转向时间调整视角移动
                            "look_dy": 0,
                            "pause_s": random.uniform(0.05, 0.15),
                        },
                        label="turn_right",
                    )
                )

            elif action == "turn_left":
                # 左转：原地左转并调整视角
                turn_duration = random.uniform(0.15, 0.30)
                self._commands.append(
                    SearchCommand(
                        action=Action.SEARCH_MOVE,
                        params={
                            "direction": "a",  # 游戏中A通常是左转键
                            "duration": turn_duration,
                            "look_dx": -int(turn_duration * 60),  # 根据转向时间调整视角移动
                            "look_dy": 0,
                            "pause_s": random.uniform(0.05, 0.15),
                        },
                        label="turn_left",
                    )
                )

        # 回位：基于摄像机方向的简单后退（S键）
        # 因为我们主要使用W前进，回位时只需要S后退
        if self._virtual_y > 0:
            # 使用S键后退，回到起点附近
            self._commands.append(
                SearchCommand(
                    action=Action.SEARCH_MOVE,
                    params={
                        "direction": "s",
                        "duration": min(1.0, self._virtual_y * 0.8),  # 稍微少退一点，避免过度
                        "look_dx": random.randint(-3, 3),  # 回位时小幅调整视角
                        "look_dy": 0,
                        "pause_s": random.uniform(0.10, 0.20),
                    },
                    label="return_to_origin",
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
