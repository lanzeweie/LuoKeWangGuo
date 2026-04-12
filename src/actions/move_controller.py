#!/usr/bin/env python3
"""
WASD 移动控制模块

根据目标在画面中的偏移方向，控制角色小范围靠近目标精灵。
- 方向判断：比较目标中心与屏幕中心
- 优先移动偏移量更大的轴
- 每次按键 200-500ms 随机，间隔 300-800ms 随机
- 达到 ±150px 精度或超时后停止
"""

from __future__ import annotations

import random
import time
from typing import Optional, Tuple

from src.core.capabilities.interception_sim import InterceptionSimulator
from src.core.capabilities.target_scoring import TargetScore
from src.logger import get_logger


# ── Constants ──────────────────────────────────────────────────────────

# 目标中心到屏幕中心的容差半径（px）
CENTER_TOLERANCE = 150.0

# 单次按键时长范围（秒）
KEY_PRESS_MIN = 0.20
KEY_PRESS_MAX = 0.50

# 移动间隔范围（秒）
MOVE_INTERVAL_MIN = 0.30
MOVE_INTERVAL_MAX = 0.80


# ── MoveController ─────────────────────────────────────────────────────

class MoveController:
    """WASD 小范围移动控制器。

    根据目标精灵在画面中的像素偏移，决定按哪个方向键以及按多久，
    使角色逐步靠近目标，直到目标中心落在画面中心 ±150px 范围内。
    """

    def __init__(self, send_input: InterceptionSimulator, debug: bool = False) -> None:
        """
        Args:
            send_input: InterceptionSimulator 实例（已注入）
            debug: 是否启用调试日志
        """
        self._send_input = send_input
        self._debug = debug
        self._logger = get_logger(debug=debug)

    # ── helpers ─────────────────────────────────────────────────────

    def _compute_offset(
        self,
        target_center: Tuple[int, int],
        screen_center: Tuple[float, float],
    ) -> Tuple[float, float]:
        """计算目标中心相对于屏幕中心的偏移。

        Returns:
            (dx, dy) 正值表示目标在屏幕中心右/下方。
        """
        tx, ty = target_center
        sx, sy = screen_center
        return tx - sx, ty - sy

    def _determine_key(self, dx: float, dy: float) -> Optional[str]:
        """根据偏移量决定按哪个键。

        优先移动偏移量更大的轴（绝对值比较）。
        返回按键字符，若两个方向都在容差内则返回 None。
        """
        abs_dx = abs(dx)
        abs_dy = abs(dy)

        in_x_tolerance = abs_dx <= CENTER_TOLERANCE
        in_y_tolerance = abs_dy <= CENTER_TOLERANCE

        if in_x_tolerance and in_y_tolerance:
            return None  # 已足够近

        # 两个方向都超出容差，优先偏移更大的轴
        if abs_dx >= abs_dy:
            return "a" if dx < 0 else "d"
        else:
            return "w" if dy < 0 else "s"

    def _random_press_duration(self) -> float:
        """返回 200-500ms 随机按键时长。"""
        return random.uniform(KEY_PRESS_MIN, KEY_PRESS_MAX)

    def _random_interval(self) -> float:
        """返回 300-800ms 随机间隔。"""
        return random.uniform(MOVE_INTERVAL_MIN, MOVE_INTERVAL_MAX)

    # ── public API ──────────────────────────────────────────────────

    def move_forward(self, duration: float = 0.3) -> int:
        """按 W 键向前移动。

        Args:
            duration: 按键时长（秒）

        Returns:
            成功发送的事件数
        """
        return self._send_input.press_key("w", duration=duration)

    def move_backward(self, duration: float = 0.3) -> int:
        """按 S 键向后移动。

        Args:
            duration: 按键时长（秒）

        Returns:
            成功发送的事件数
        """
        return self._send_input.press_key("s", duration=duration)

    def move_left(self, duration: float = 0.3) -> int:
        """按 A 键向左移动。

        Args:
            duration: 按键时长（秒）

        Returns:
            成功发送的事件数
        """
        return self._send_input.press_key("a", duration=duration)

    def move_right(self, duration: float = 0.3) -> int:
        """按 D 键向右移动。

        Args:
            duration: 按键时长（秒）

        Returns:
            成功发送的事件数
        """
        return self._send_input.press_key("d", duration=duration)

    def move_toward_target(
        self,
        target: Optional[TargetScore],
        screen_width: int = 1280,
        screen_height: int = 720,
        max_iterations: int = 5,
        max_duration: float = 15.0,
    ) -> bool:
        """向目标移动，直到目标中心在画面中心 ±150px 范围内。

        Args:
            target: 目标评分对象（含 detection.center）
            screen_width: 屏幕客户区宽度
            screen_height: 屏幕客户区高度
            max_iterations: 最大移动迭代次数
            max_duration: 最大持续时间（秒），超时返回 False

        Returns:
            True 表示已足够近，False 表示超时或丢失目标
        """
        if target is None:
            self._logger.warning("move_toward_target: target 为 None，跳过移动")
            return False

        screen_center = (screen_width / 2.0, screen_height / 2.0)
        start_time = time.time()
        iteration = 0

        while iteration < max_iterations:
            # 超时检查
            elapsed = time.time() - start_time
            if elapsed >= max_duration:
                self._logger.warning(
                    f"move_toward_target: 超时 ({elapsed:.1f}s >= {max_duration:.1f}s)"
                )
                return False

            # 获取目标中心
            center = target.detection.center
            if center is None:
                self._logger.warning("move_toward_target: 无法获取目标中心坐标")
                return False

            dx, dy = self._compute_offset(center, screen_center)
            distance = (dx * dx + dy * dy) ** 0.5

            self._logger.info(
                f"移动迭代 {iteration + 1}/{max_iterations}: "
                f"偏移=({dx:+.0f}, {dy:+.0f}) 距离={distance:.0f}px"
            )

            key = self._determine_key(dx, dy)
            if key is None:
                self._logger.success(
                    f"目标已在中心容差内 (距离={distance:.0f}px < {CENTER_TOLERANCE:.0f}px)"
                )
                return True

            # 执行按键
            press_duration = self._random_press_duration()
            self._logger.info(f"  按 {key.upper()} 键 {press_duration * 1000:.0f}ms")
            self._send_input.press_key(key, duration=press_duration)

            # 移动间隔（非阻塞式检查：先 sleep，但每次短片段检查超时）
            interval = self._random_interval()
            interval_start = time.time()
            while time.time() - interval_start < interval:
                if time.time() - start_time >= max_duration:
                    self._logger.warning(
                        f"move_toward_target: 间隔中超时 ({time.time() - start_time:.1f}s)"
                    )
                    return False
                time.sleep(0.05)  # 50ms 轮询

            iteration += 1

        # 达到最大迭代次数，检查最终是否足够近
        center = target.detection.center
        dx, dy = self._compute_offset(center, screen_center)
        distance = (dx * dx + dy * dy) ** 0.5

        if distance <= CENTER_TOLERANCE:
            self._logger.success(f"达到最大迭代次数，目标已足够近 (距离={distance:.0f}px)")
            return True

        self._logger.warning(
            f"达到最大迭代次数 ({max_iterations})，目标仍偏远 (距离={distance:.0f}px)"
        )
        return False


# ── Tests ──────────────────────────────────────────────────────────────

class _MockSendInputSimulator:
    """Mock SendInputSimulator for unit testing without actual input."""

    def __init__(self) -> None:
        self.key_presses: list[tuple[str, float]] = []  # (key, duration)

    def press_key(self, key: str, duration: float = 0.2) -> int:
        self.key_presses.append((key, duration))
        return 2


class _MockDetectionResult:
    """Mock DetectionResult for testing."""

    def __init__(self, center: Tuple[int, int]) -> None:
        self._center = center

    @property
    def center(self) -> Tuple[int, int]:
        return self._center


class _MockTargetScore:
    """Mock TargetScore for testing."""

    def __init__(self, center: Tuple[int, int]) -> None:
        self.detection = _MockDetectionResult(center)


def test_move_controller() -> bool:
    """测试 MoveController 移动逻辑。

    使用 Mock 对象验证：
    - 方向判断正确
    - 容差检查正确
    - 超时处理正确
    - 目标丢失处理正确
    - 最大迭代次数限制
    """
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

    # ── Test 1: _compute_offset ────────────────────────────────────
    print("\n[Test 1] _compute_offset calculation...")
    mock_input = _MockSendInputSimulator()
    controller = MoveController(mock_input, debug=False)

    # Target at (400, 300), screen center (640, 360)
    dx, dy = controller._compute_offset((400, 300), (640.0, 360.0))
    check("dx = 400 - 640 = -240", dx == -240.0)
    check("dy = 300 - 360 = -60", dy == -60.0)

    # ── Test 2: _determine_key — target to the left ────────────────
    print("\n[Test 2] _determine_key — direction decisions...")
    check("target far left (dx=-300, dy=0) → 'a'",
          controller._determine_key(-300.0, 0.0) == "a")
    check("target far right (dx=300, dy=0) → 'd'",
          controller._determine_key(300.0, 0.0) == "d")
    check("target far up (dx=0, dy=-300) → 'w'",
          controller._determine_key(0.0, -300.0) == "w")
    check("target far down (dx=0, dy=300) → 's'",
          controller._determine_key(0.0, 300.0) == "s")

    # Within tolerance
    check("target within tolerance (dx=100, dy=100) → None",
          controller._determine_key(100.0, 100.0) is None)
    check("target at exact tolerance (dx=150, dy=0) → None",
          controller._determine_key(150.0, 0.0) is None)

    # Priority: larger axis wins
    check("both exceed, dx larger (dx=-400, dy=-200) → 'a'",
          controller._determine_key(-400.0, -200.0) == "a")
    check("both exceed, dy larger (dx=100, dy=-300) → 'w'",
          controller._determine_key(100.0, -300.0) == "w")
    check("both exceed, equal (dx=-300, dy=-300) → 'a' (dx wins on tie)",
          controller._determine_key(-300.0, -300.0) == "a")

    # ── Test 3: None target returns False ──────────────────────────
    print("\n[Test 3] None target handling...")
    result = controller.move_toward_target(target=None)
    check("None target returns False", result is False)

    # ── Test 4: Target already centered returns True ───────────────
    print("\n[Test 4] Target already within tolerance...")
    mock_input2 = _MockSendInputSimulator()
    controller2 = MoveController(mock_input2, debug=False)
    centered_target = _MockTargetScore(center=(640, 360))  # exact center
    result = controller2.move_toward_target(
        target=centered_target,
        screen_width=1280,
        screen_height=720,
    )
    check("centered target returns True", result is True)
    check("no keys pressed for centered target", len(mock_input2.key_presses) == 0)

    # ── Test 5: Target slightly off-center, should press key ───────
    print("\n[Test 5] Target needs movement (far left)...")
    mock_input3 = _MockSendInputSimulator()
    controller3 = MoveController(mock_input3, debug=False)
    # Target at x=200, screen center x=640, dx=-440, needs multiple iterations
    left_target = _MockTargetScore(center=(200, 360))
    # Use max_iterations=1 to avoid real input spamming; but we need to verify key pressed
    # Since the mock doesn't change target position, it will keep pressing 'a' until max_iterations
    result = controller3.move_toward_target(
        target=left_target,
        screen_width=1280,
        screen_height=720,
        max_iterations=1,
        max_duration=5.0,
    )
    check("far target with 1 iteration returns False (still far after 1 press)", result is False)
    check("pressed 'a' key exactly once", len(mock_input3.key_presses) == 1)
    check("pressed key is 'a'", mock_input3.key_presses[0][0] == "a")
    check("press duration in valid range",
          0.20 <= mock_input3.key_presses[0][1] <= 0.50)

    # ── Test 6: Target far right ───────────────────────────────────
    print("\n[Test 6] Target far right...")
    mock_input4 = _MockSendInputSimulator()
    controller4 = MoveController(mock_input4, debug=False)
    right_target = _MockTargetScore(center=(1100, 360))
    controller4.move_toward_target(
        target=right_target,
        screen_width=1280,
        screen_height=720,
        max_iterations=1,
        max_duration=5.0,
    )
    check("pressed 'd' key for right target",
          len(mock_input4.key_presses) >= 1 and mock_input4.key_presses[0][0] == "d")

    # ── Test 7: Timeout handling ───────────────────────────────────
    print("\n[Test 7] Timeout handling...")
    mock_input5 = _MockSendInputSimulator()
    controller5 = MoveController(mock_input5, debug=False)
    far_target = _MockTargetScore(center=(100, 100))
    result = controller5.move_toward_target(
        target=far_target,
        screen_width=1280,
        screen_height=720,
        max_iterations=100,
        max_duration=0.001,  # 1ms timeout — should trigger immediately
    )
    check("timeout returns False", result is False)

    # ── Summary ────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed == 0:
        print("All tests passed!")
    else:
        print(f"WARNING: {failed} test(s) failed!")
    print(f"{'=' * 50}")
    return failed == 0


if __name__ == "__main__":
    test_move_controller()
