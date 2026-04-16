#!/usr/bin/env python3
"""
摄像机导向巡逻模式：W前进 + 转向调整 + 简单回位。
基于洛克王国等游戏的移动机制，W始终朝向摄像机所指方向前进，
使用A/D键进行转向，避免了无意义的横向移动。
"""

from __future__ import annotations

import random
import time
from collections import deque
from typing import TYPE_CHECKING, Optional

from src.strategies.base import Action
from src.strategies.search_patterns.base_pattern import BaseSearchPattern, SearchCommand
from src.strategies.search_patterns.enhanced_move_controller import EnhancedMoveController

if TYPE_CHECKING:
    from src.core.context import AppContext


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
        self._move_controller: Optional[EnhancedMoveController] = None
        self._initialized = False

    def reset(self) -> None:
        super().reset()
        self._commands.clear()
        self._virtual_x = 0.0
        self._virtual_y = 0.0
        self._initialized = False
        self._build_patrol_commands()

    def _ensure_move_controller(self, ctx: "AppContext") -> None:
        """确保移动控制器已初始化"""
        if not self._initialized and hasattr(ctx, 'send_input') and ctx.send_input is not None:
            self._move_controller = EnhancedMoveController(ctx.send_input, debug=getattr(ctx, 'debug', False))
            self._initialized = True

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

    def next_command(self, ctx: "AppContext") -> SearchCommand:
        if not self._commands:
            self._finished = True
            return SearchCommand(action=Action.NO_OP, label="circular_patrol_finished")

        # 确保移动控制器已初始化
        self._ensure_move_controller(ctx)

        cmd = self._commands.popleft()
        if not self._commands:
            self._finished = True

        if hasattr(ctx, "logger") and ctx.logger:
            ctx.logger.debug_msg(f"[CircularPatrol] label={cmd.label}, params={cmd.params}")

        # 如果是移动命令且有移动控制器，直接执行
        if cmd.action == Action.SEARCH_MOVE and self._move_controller:
            direction = cmd.params.get("direction", "")
            duration = cmd.params.get("duration", 0.0)

            if direction == "w":
                # 前进
                self._move_controller.execute_direction_move("W", duration)
                # 同时处理视角调整
                look_dx = cmd.params.get("look_dx", 0)
                look_dy = cmd.params.get("look_dy", 0)
                if look_dx != 0 or look_dy != 0:
                    self._move_controller.execute_smooth_turn(look_dx, speed=30)

                # 暂停
                pause_s = cmd.params.get("pause_s", 0.1)
                if pause_s > 0:
                    time.sleep(pause_s)

            elif direction in ("a", "d"):
                # 转向
                turn_duration = duration
                angle = 30 if direction == "d" else -30
                self._move_controller.execute_smooth_turn(angle, speed=60)
                time.sleep(turn_duration)

            elif direction == "s":
                # 后退
                self._move_controller.execute_direction_move("S", duration)
                # 同时处理视角调整
                look_dx = cmd.params.get("look_dx", 0)
                look_dy = cmd.params.get("look_dy", 0)
                if look_dx != 0 or look_dy != 0:
                    self._move_controller.execute_smooth_turn(look_dx, speed=30)

                # 暂停
                pause_s = cmd.params.get("pause_s", 0.1)
                if pause_s > 0:
                    time.sleep(pause_s)

            # 返回 NO_OP，因为我们已经执行了移动
            return SearchCommand(action=Action.NO_OP, label=cmd.label + "_executed")

        return cmd
