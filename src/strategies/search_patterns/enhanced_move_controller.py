#!/usr/bin/env python3
"""
增强版移动控制器 - 支持智能搜索策略的移动模式
- 支持 8 方向移动（W, A, S, D, WA, WD, SA, SD）
- 集成航位推算功能
- 平滑的移动控制，避免卡墙
"""

from __future__ import annotations

import random
import time
from typing import Dict, Optional, Tuple

from src.core.capabilities.interception_sim import InterceptionSimulator
from src.logger import get_logger


class EnhancedMoveController:
    """
    增强版移动控制器
    支持智能搜索策略的各种移动需求
    """

    def __init__(self, send_input: InterceptionSimulator, debug: bool = False) -> None:
        self._send_input = send_input
        self._debug = debug
        self._logger = get_logger(debug=debug)

        # 当前按下的键状态（用于组合键）
        self._pressed_keys: set[str] = set()

    def execute_direction_move(self, direction: str, duration: float) -> bool:
        """执行方向移动，支持 8 个方向

        Args:
            direction: 方向字符串 ('W', 'A', 'S', 'D', 'WA', 'WD', 'SA', 'SD')
            duration: 移动时长（秒）

        Returns:
            是否成功执行
        """
        try:
            # 解析方向到按键组合
            keys = self._direction_to_keys(direction)

            # 按下所有需要的键
            for key in keys:
                if key not in self._pressed_keys:
                    self._send_input.key_down(key)
                    self._pressed_keys.add(key)
                    if self._debug:
                        self._logger.debug(f"按下 {key} 键")

            # 等待指定时长
            time.sleep(duration)

            # 释放所有按键
            for key in keys:
                if key in self._pressed_keys:
                    self._send_input.key_up(key)
                    self._pressed_keys.remove(key)
                    if self._debug:
                        self._logger.debug(f"释放 {key} 键")

            return True

        except Exception as e:
            self._logger.error(f"执行方向移动失败: {e}")
            # 确保释放所有按键
            self._release_all_keys()
            return False

    def _direction_to_keys(self, direction: str) -> Tuple[str, ...]:
        """将方向字符串转换为按键组合"""
        direction = direction.upper()

        # 8 个方向的映射
        direction_map: Dict[str, Tuple[str, ...]] = {
            "W": ("w",),
            "A": ("a",),
            "S": ("s",),
            "D": ("d",),
            "WA": ("w", "a"),
            "WD": ("w", "d"),
            "SA": ("s", "a"),
            "SD": ("s", "d"),
        }

        return direction_map.get(direction, ("w",))

    def _release_all_keys(self) -> None:
        """释放所有当前按下的键（紧急情况）"""
        for key in list(self._pressed_keys):
            try:
                self._send_input.key_up(key)
                self._pressed_keys.remove(key)
            except Exception as e:
                self._logger.error(f"释放键 {key} 失败: {e}")

    def execute_smooth_turn(self, angle: float, speed: float = 30.0) -> bool:
        """执行平滑的鼠标转动

        Args:
            angle: 转动角度（度），正值为右转，负值为左转
            speed: 转动速度（度/秒）

        Returns:
            是否成功执行
        """
        try:
            # 计算转动时间
            duration = abs(angle) / speed

            # 计算鼠标移动距离（基于屏幕分辨率估算）
            # 假设 1280x720 分辨率下，水平移动 640 像素约等于 180 度
            pixels_per_degree = 640 / 180.0
            mouse_dx = int(angle * pixels_per_degree)

            if self._debug:
                self._logger.debug(
                    f"平滑转动: 角度={angle:.1f}°, "
                    f"鼠标移动={mouse_dx}px, "
                    f"时长={duration:.2f}s"
                )

            # 执行鼠标移动
            self._send_input.mouse_move(mouse_dx, 0)
            time.sleep(duration)

        except Exception as e:
            self._logger.error(f"执行平滑转动失败: {e}")
            return False

    def execute_scan_with_pause(self, angle_step: float, pause_duration: float = 0.1) -> bool:
        """执行带停顿的扫描动作

        Args:
            angle_step: 每次扫描的角度步长（度）
            pause_duration: 每次扫描后的停顿时长（秒）

        Returns:
            是否成功执行
        """
        try:
            # 执行转动
            if not self.execute_smooth_turn(angle_step):
                return False

            # 停顿，让检测模块有时间处理画面
            time.sleep(pause_duration)

            return True

        except Exception as e:
            self._logger.error(f"执行扫描动作失败: {e}")
            return False

    def get_current_position_estimate(self) -> Tuple[float, float]:
        """
        获取当前位置估算（需要与航位推算系统集成）

        Returns:
            (x, y) 虚拟坐标
        """
        # 这个方法需要与 SmartSearchStrategy 的航位推算系统集成
        # 返回当前的虚拟位置估算
        return 0.0, 0.0

    def emergency_stop(self) -> None:
        """紧急停止，释放所有按键"""
        self._logger.warning("紧急停止：释放所有按键")
        self._release_all_keys()


# ── 测试用 Mock 类 ──────────────────────────────────────────────────────

class _MockInterceptionSimulator:
    """Mock InterceptionSimulator for testing"""

    def __init__(self) -> None:
        self.key_down_calls: list[str] = []
        self.key_up_calls: list[str] = []
        self.mouse_moves: list[Tuple[int, int]] = []

    def key_down(self, key: str) -> None:
        self.key_down_calls.append(key)

    def key_up(self, key: str) -> None:
        self.key_up_calls.append(key)

    def mouse_move(self, rel_x: int, rel_y: int) -> int:
        self.mouse_moves.append((rel_x, rel_y))
        return 2


def test_enhanced_move_controller() -> bool:
    """测试增强版移动控制器"""
    passed = 0
    failed = 0

    def check(name: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")

    print("\n[测试] 增强版移动控制器")

    # 测试方向解析
    mock_sim = _MockInterceptionSimulator()
    controller = EnhancedMoveController(mock_sim, debug=False)

    # 测试 8 个方向
    test_cases = [
        ("W", ("w",)),
        ("A", ("a",)),
        ("S", ("s",)),
        ("D", ("d",)),
        ("WA", ("w", "a")),
        ("WD", ("w", "d")),
        ("SA", ("s", "a")),
        ("SD", ("s", "d")),
    ]

    for direction, expected_keys in test_cases:
        actual_keys = controller._direction_to_keys(direction)
        check(f"方向 {direction} 解析为 {expected_keys}", actual_keys == expected_keys)

    # 测试执行方向移动（模拟）
    controller.execute_direction_move("WA", 0.5)

    # 检查按键按下和释放
    check("W 键被按下", "w" in mock_sim.key_down_calls)
    check("A 键被按下", "a" in mock_sim.key_down_calls)
    check("W 键被释放", "w" in mock_sim.key_up_calls)
    check("A 键被释放", "a" in mock_sim.key_up_calls)

    # 测试平滑转动
    mock_sim.mouse_moves.clear()
    controller.execute_smooth_turn(90, speed=45)

    check("鼠标移动被调用", len(mock_sim.mouse_moves) > 0)
    if mock_sim.mouse_moves:
        dx, dy = mock_sim.mouse_moves[0]
        check(f"鼠标 X 轴移动 {dx}px", dx > 0)

    # 测试紧急停止
    controller._pressed_keys = {"w", "a"}
    controller.emergency_stop()
    check("紧急停止后按键状态为空", len(controller._pressed_keys) == 0)
    check("W 键被释放（紧急停止）", "w" in mock_sim.key_up_calls)
    check("A 键被释放（紧急停止）", "a" in mock_sim.key_up_calls)

    # 总结
    print(f"\n{'=' * 50}")
    print(f"测试结果: {passed} 通过, {failed} 失败")
    if failed == 0:
        print("所有测试通过！")
    else:
        print(f"警告: {failed} 个测试失败！")
    print(f"{'=' * 50}")

    return failed == 0


if __name__ == "__main__":
    test_enhanced_move_controller()