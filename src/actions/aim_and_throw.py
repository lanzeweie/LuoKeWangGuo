#!/usr/bin/env python3
"""
瞄准与投掷模块

实现目标中心瞄准 + 按住鼠标 + 松开鼠标的投掷逻辑。
- 使用 SendInputSimulator 的 mouse_move（分段轨迹 + 随机抖动）
- mouse_down / mouse_up 完成投掷
- 投掷时序：瞄准 → 稳定等待 → 按住 → 微调 → 松开
"""

from __future__ import annotations

import random
import time
from typing import Optional

from src.core.capabilities.target_scoring import TargetScore
from src.core.capabilities.sendinput_sim import SendInputSimulator
from src.logger import get_logger


class AimAndThrow:
    """瞄准目标并执行精灵球投掷。"""

    def __init__(self, send_input: SendInputSimulator, debug: bool = False) -> None:
        """
        Args:
            send_input: SendInputSimulator 实例（已注入）
            debug: 是否启用调试日志
        """
        self._send_input = send_input
        self.debug = debug
        self._log = get_logger(debug=debug)

    # ── public ──────────────────────────────────────────────────────

    def aim_and_throw(
        self,
        target: TargetScore,
        screen_width: int = 1280,
        screen_height: int = 720,
        fine_tune_ms: int = 500,
    ) -> bool:
        """
        瞄准目标中心并执行投掷。

        流程：
        1. 计算目标中心相对于屏幕中心的偏移
        2. mouse_move 移动到目标中心（分段轨迹 + ±3-8px 随机抖动）
        3. 等待 100-200ms 稳定
        4. mouse_down 按住鼠标左键
        5. fine_tune_ms 时长（300-600ms 随机）内可再微调一次（±5px）
        6. mouse_up 松开鼠标，完成投掷

        Args:
            target: 目标评分对象（含 detection.center）
            screen_width/height: 屏幕客户区尺寸
            fine_tune_ms: 按住后微调时长（毫秒），默认 500

        Returns:
            True 表示投掷操作完成，False 表示目标无效
        """
        if target is None:
            if self.debug:
                self._log.debug_msg("aim_and_throw: target 为 None")
            return False

        cx, cy = target.detection.center
        if not self._is_valid_coord(cx, cy, screen_width, screen_height):
            if self.debug:
                self._log.debug_msg(
                    f"aim_and_throw: 坐标无效 center=({cx},{cy}) "
                    f"size={screen_width}x{screen_height}"
                )
            return False

        # 计算相对于屏幕中心的偏移
        offset_x = cx - screen_width // 2
        offset_y = cy - screen_height // 2

        if self.debug:
            self._log.debug_msg(
                f"aim_and_throw: 目标 center=({cx},{cy}), "
                f"offset=({offset_x},{offset_y})"
            )

        # Step 1: 移动到目标中心
        try:
            self._send_input.mouse_move(offset_x, offset_y)
        except Exception as exc:
            if self.debug:
                self._log.debug_msg(f"aim_and_throw: mouse_move 失败: {exc}")
            return False

        # Step 2: 稳定等待 100-200ms
        time.sleep(random.uniform(0.10, 0.20))

        # Step 3: 按住鼠标
        try:
            self._send_input.mouse_down()
        except Exception as exc:
            if self.debug:
                self._log.debug_msg(f"aim_and_throw: mouse_down 失败: {exc}")
            return False

        # Step 4: 按住期间微调
        hold_duration = max(300, min(fine_tune_ms, 600)) / 1000.0  # clamp 300-600ms
        time.sleep(hold_duration * 0.6)  # 60% 时间后再微调

        # 小幅微调 ±5px
        try:
            micro_x = random.randint(-5, 5)
            micro_y = random.randint(-5, 5)
            if micro_x != 0 or micro_y != 0:
                self._send_input.mouse_move(micro_x, micro_y)
                if self.debug:
                    self._log.debug_msg(
                        f"aim_and_throw: 按住微调 ({micro_x},{micro_y})"
                    )
        except Exception as exc:
            if self.debug:
                self._log.debug_msg(f"aim_and_throw: 微调 mouse_move 失败: {exc}")
            # 微调失败不影响后续松开

        # 等完剩余时间
        time.sleep(hold_duration * 0.4)

        # Step 5: 松开鼠标
        try:
            self._send_input.mouse_up()
        except Exception as exc:
            if self.debug:
                self._log.debug_msg(f"aim_and_throw: mouse_up 失败: {exc}")
            return False

        if self.debug:
            self._log.debug_msg("aim_and_throw: 投掷完成")
        return True

    def aim_only(
        self,
        target: TargetScore,
        screen_width: int = 1280,
        screen_height: int = 720,
    ) -> bool:
        """
        仅瞄准不投掷，用于调试。

        Returns:
            True 表示瞄准成功
        """
        if target is None:
            if self.debug:
                self._log.debug_msg("aim_only: target 为 None")
            return False

        cx, cy = target.detection.center
        if not self._is_valid_coord(cx, cy, screen_width, screen_height):
            if self.debug:
                self._log.debug_msg(
                    f"aim_only: 坐标无效 center=({cx},{cy}) "
                    f"size={screen_width}x{screen_height}"
                )
            return False

        offset_x = cx - screen_width // 2
        offset_y = cy - screen_height // 2

        if self.debug:
            self._log.debug_msg(
                f"aim_only: 目标 center=({cx},{cy}), offset=({offset_x},{offset_y})"
            )

        try:
            self._send_input.mouse_move(offset_x, offset_y)
        except Exception as exc:
            if self.debug:
                self._log.debug_msg(f"aim_only: mouse_move 失败: {exc}")
            return False

        return True

    # ── private ─────────────────────────────────────────────────────

    @staticmethod
    def _is_valid_coord(x: int, y: int, width: int, height: int) -> bool:
        """检查坐标是否在客户区范围内。"""
        return 0 <= x < width and 0 <= y < height


# ── Tests ─────────────────────────────────────────────────────────────


class _MockSendInput:
    """Fake SendInputSimulator for unit testing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def mouse_move(self, rel_x: int, rel_y: int) -> int:
        self.calls.append(("mouse_move", (rel_x, rel_y)))
        return 1

    def mouse_down(self) -> int:
        self.calls.append(("mouse_down", ()))
        return 1

    def mouse_up(self) -> int:
        self.calls.append(("mouse_up", ()))
        return 1


def _make_target(cx: int, cy: int) -> TargetScore:
    """Helper to construct a minimal TargetScore for tests."""
    from src.core.capabilities.detection import DetectionResult

    det = DetectionResult(
        x1=cx - 20,
        y1=cy - 20,
        x2=cx + 20,
        y2=cy + 20,
        confidence=0.95,
        class_id=0,
    )
    return TargetScore(
        detection=det,
        distance_to_center=0.0,
        bbox_area=1600.0,
        distance_state="CLOSE",
        priority_rank=1,
    )


def test_aim_and_throw() -> bool:
    """测试 AimAndThrow 的瞄准和投掷逻辑（Mock）。"""
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

    print("[Test 1] aim_only calls mouse_move with correct offset...")
    mock = _MockSendInput()
    thrower = AimAndThrow(send_input=mock, debug=False)
    target = _make_target(cx=640, cy=360)  # center of 1280x720
    result = thrower.aim_only(target, screen_width=1280, screen_height=720)
    check("returns True", result is True)
    check("calls mouse_move once", len([c for c in mock.calls if c[0] == "mouse_move"]) == 1)
    check("offset is (0, 0) for center target",
          mock.calls[0] == ("mouse_move", (0, 0)))

    # Off-center target
    mock2 = _MockSendInput()
    thrower2 = AimAndThrow(send_input=mock2, debug=False)
    target2 = _make_target(cx=740, cy=410)  # +100, +50 from center
    result2 = thrower2.aim_only(target2, screen_width=1280, screen_height=720)
    check("off-center returns True", result2 is True)
    check("offset is (100, 50)",
          mock2.calls[0] == ("mouse_move", (100, 50)))

    print("\n[Test 2] aim_and_throw call order: move -> down -> up...")
    mock3 = _MockSendInput()
    thrower3 = AimAndThrow(send_input=mock3, debug=False)
    target3 = _make_target(cx=640, cy=360)
    result3 = thrower3.aim_and_throw(
        target3, screen_width=1280, screen_height=720, fine_tune_ms=300
    )
    check("returns True", result3 is True)

    # Extract non-micro-move calls (the main sequence)
    call_names = [c[0] for c in mock3.calls]
    # First call should be mouse_move, last two should be mouse_down, mouse_up
    # (micro-adjust mouse_move may appear between down and up)
    check("first call is mouse_move", call_names[0] == "mouse_move")
    check("mouse_down present", "mouse_down" in call_names)
    check("mouse_up present", "mouse_up" in call_names)
    check("mouse_down before mouse_up",
          call_names.index("mouse_down") < call_names.index("mouse_up"))
    check("mouse_move before mouse_down",
          call_names.index("mouse_move") < call_names.index("mouse_down"))

    print("\n[Test 3] None target returns False...")
    mock4 = _MockSendInput()
    thrower4 = AimAndThrow(send_input=mock4, debug=False)
    result4a = thrower4.aim_and_throw(None)  # type: ignore[arg-type]
    result4b = thrower4.aim_only(None)  # type: ignore[arg-type]
    check("aim_and_throw(None) == False", result4a is False)
    check("aim_only(None) == False", result4b is False)
    check("no input calls for None target", len(mock4.calls) == 0)

    print("\n[Test 4] Out-of-bounds coordinate returns False...")
    mock5 = _MockSendInput()
    thrower5 = AimAndThrow(send_input=mock5, debug=False)
    bad_target = _make_target(cx=2000, cy=360)  # x > 1280
    result5 = thrower5.aim_only(bad_target, screen_width=1280, screen_height=720)
    check("out-of-bounds returns False", result5 is False)
    check("no input calls for bad coord", len(mock5.calls) == 0)

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed == 0:
        print("All tests passed!")
    else:
        print(f"WARNING: {failed} test(s) failed!")
    print(f"{'=' * 50}")
    return failed == 0


if __name__ == "__main__":
    test_aim_and_throw()
