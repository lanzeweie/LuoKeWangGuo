#!/usr/bin/env python3
"""
战斗退出模块

当检测到战斗状态时，通过 SendInput 发送 ESC 键退出战斗界面，
并通过 BattleModeDetector 轮询确认是否回到正常界面。
"""

import time
from typing import Callable, Optional

import numpy as np

from src.core.battle_mode_detector import BattleModeDetector
from src.core.sendinput_sim import SendInputSimulator
from src.logger import get_logger

# ── 配置常量 ──────────────────────────────────────────────────────────
DEFAULT_MAX_RETRIES = 3
DEFAULT_WAIT_AFTER_ESC = 1.5
WAIT_INCREMENT = 0.5  # 每次重试递增的等待时间（秒）
FRAME_RETRY_DELAY = 0.2  # 帧获取失败后的重试等待（秒）


class BattleExit:
    """通过按 ESC 退出战斗状态。"""

    def __init__(
        self,
        send_input: SendInputSimulator,
        battle_detector: BattleModeDetector,
        debug: bool = False,
    ) -> None:
        """
        Args:
            send_input: SendInputSimulator 实例（已注入）
            battle_detector: BattleModeDetector 实例（用于检测是否还在战斗状态）
            debug: 是否启用调试日志
        """
        self._send_input = send_input
        self._battle_detector = battle_detector
        self.debug = debug
        self.logger = get_logger(debug=debug)

    def exit_battle(
        self,
        frame_provider: Callable[[], Optional[np.ndarray]],
        max_retries: int = DEFAULT_MAX_RETRIES,
        wait_after_esc: float = DEFAULT_WAIT_AFTER_ESC,
    ) -> bool:
        """按 ESC 退出战斗状态，检测是否回到正常界面。

        流程：
        1. 发送 ESC 键
        2. 等待递增时间
        3. 获取当前帧，检测是否还在战斗
        4. 不在战斗 → 返回 True；还在战斗 → 重试

        Args:
            frame_provider: 可调用对象，返回当前帧（numpy array 或 None）
            max_retries: 最大重试次数
            wait_after_esc: 首次按 ESC 后等待时间（秒）

        Returns:
            True 表示成功退出战斗，False 表示重试后仍在战斗中
        """
        self.logger.info(f"开始退出战斗流程 (max_retries={max_retries})")

        for attempt in range(1, max_retries + 1):
            # 计算当前重试的等待时间（递增）
            current_wait = wait_after_esc + (attempt - 1) * WAIT_INCREMENT

            self.logger.info(
                f"第 {attempt}/{max_retries} 次尝试: 发送 ESC，"
                f"等待 {current_wait:.1f}s"
            )

            # 发送 ESC 键
            try:
                self._send_input.press_key("esc", duration=0.1)
            except Exception as exc:
                self.logger.error(f"发送 ESC 键失败: {exc}")
                return False

            # 等待游戏响应
            time.sleep(current_wait)

            # 检测是否还在战斗
            still_in_battle = self.is_still_in_battle(frame_provider)

            if not still_in_battle:
                self.logger.success("成功退出战斗状态")
                return True

            self.logger.warning(
                f"第 {attempt} 次尝试后仍在战斗中，准备重试..."
            )

        self.logger.error(
            f"退出战斗失败: 已重试 {max_retries} 次，仍在战斗中"
        )
        return False

    def is_still_in_battle(
        self, frame_provider: Callable[[], Optional[np.ndarray]]
    ) -> bool:
        """快速检测当前是否还在战斗状态。

        Args:
            frame_provider: 可调用对象，返回当前帧

        Returns:
            True 表示还在战斗，False 表示已不在战斗或无法获取帧
        """
        # 获取当前帧，失败时重试一次
        frame = frame_provider()
        if frame is None:
            self.logger.warning("无法获取当前帧，等待重试...")
            time.sleep(FRAME_RETRY_DELAY)
            frame = frame_provider()

        if frame is None:
            self.logger.warning("无法获取当前帧，视为不在战斗（保守处理）")
            return False

        try:
            is_battle, confidence = self._battle_detector.is_battle_mode(frame)
            if self.debug:
                self.logger.debug_msg(
                    f"战斗状态检测: {'在战斗' if is_battle else '不在战斗'} "
                    f"(confidence={confidence:.4f})"
                )
            return is_battle
        except Exception as exc:
            self.logger.error(f"战斗检测异常: {exc}，视为不在战斗")
            return False


def test_battle_exit() -> bool:
    """测试 BattleExit 类。

    使用 Mock 对象验证 exit_battle 和 is_still_in_battle 的行为。
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

    # ── Mock classes ────────────────────────────────────────────────
    class MockSendInputSimulator:
        def __init__(self) -> None:
            self.press_key_calls: list = []

        def press_key(self, key: str, duration: float = 0.2) -> int:
            self.press_key_calls.append((key, duration))
            return 2

    class MockBattleModeDetector:
        def __init__(self, battle_results: list[tuple[bool, float]]) -> None:
            self.battle_results = battle_results
            self.call_index = 0

        def is_battle_mode(self, frame) -> tuple[bool, float]:
            if self.call_index < len(self.battle_results):
                result = self.battle_results[self.call_index]
                self.call_index += 1
                return result
            return False, 0.0

    class MockScreenCap:
        def __init__(self, frames: list) -> None:
            self.frames = frames
            self.index = 0

        def capture(self) -> Optional[np.ndarray]:
            if self.index < len(self.frames):
                frame = self.frames[self.index]
                self.index += 1
                return frame
            return None

    # 创建测试用帧
    dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    # ── Test 1: 第一次按 ESC 就退出成功 ─────────────────────────────
    print("[Test 1] 第一次按 ESC 后不在战斗 → 返回 True")
    mock_send_input = MockSendInputSimulator()
    mock_battle_detector = MockBattleModeDetector(battle_results=[(False, 0.1)])
    battle_exit = BattleExit(mock_send_input, mock_battle_detector, debug=False)

    # 使用极短等待以加快测试
    result = battle_exit.exit_battle(
        frame_provider=lambda: dummy_frame,
        max_retries=3,
        wait_after_esc=0.01,
    )
    check("exit_battle 返回 True", result is True)
    check("调用 press_key 1 次", len(mock_send_input.press_key_calls) == 1)
    check("press_key 参数为 esc", mock_send_input.press_key_calls[0][0] == "esc")

    # ── Test 2: 需要重试 2 次才退出 ──────────────────────────────────
    print("\n[Test 2] 需要重试 2 次才退出 → 返回 True")
    mock_send_input2 = MockSendInputSimulator()
    # 第 1 次检测: 还在战斗; 第 2 次检测: 不在战斗
    mock_battle_detector2 = MockBattleModeDetector(
        battle_results=[(True, 0.95), (False, 0.1)]
    )
    battle_exit2 = BattleExit(mock_send_input2, mock_battle_detector2, debug=False)

    result2 = battle_exit2.exit_battle(
        frame_provider=lambda: dummy_frame,
        max_retries=3,
        wait_after_esc=0.01,
    )
    check("exit_battle 返回 True", result2 is True)
    check("调用 press_key 2 次", len(mock_send_input2.press_key_calls) == 2)

    # ── Test 3: 3 次重试后仍在战斗 ───────────────────────────────────
    print("\n[Test 3] 3 次重试后仍在战斗 → 返回 False")
    mock_send_input3 = MockSendInputSimulator()
    mock_battle_detector3 = MockBattleModeDetector(
        battle_results=[(True, 0.95), (True, 0.90), (True, 0.85)]
    )
    battle_exit3 = BattleExit(mock_send_input3, mock_battle_detector3, debug=False)

    result3 = battle_exit3.exit_battle(
        frame_provider=lambda: dummy_frame,
        max_retries=3,
        wait_after_esc=0.01,
    )
    check("exit_battle 返回 False", result3 is False)
    check("调用 press_key 3 次", len(mock_send_input3.press_key_calls) == 3)

    # ── Test 4: is_still_in_battle 正常工作 ──────────────────────────
    print("\n[Test 4] is_still_in_battle 正常工作")
    mock_send_input4 = MockSendInputSimulator()
    mock_battle_detector4 = MockBattleModeDetector(battle_results=[(True, 0.95)])
    battle_exit4 = BattleExit(mock_send_input4, mock_battle_detector4, debug=False)

    still = battle_exit4.is_still_in_battle(frame_provider=lambda: dummy_frame)
    check("检测到在战斗", still is True)

    # 测试不在战斗的情况
    mock_battle_detector5 = MockBattleModeDetector(battle_results=[(False, 0.1)])
    battle_exit5 = BattleExit(mock_send_input4, mock_battle_detector5, debug=False)

    still2 = battle_exit5.is_still_in_battle(frame_provider=lambda: dummy_frame)
    check("检测到不在战斗", still2 is False)

    # 测试帧获取返回 None 的情况
    mock_battle_detector6 = MockBattleModeDetector(battle_results=[])
    battle_exit6 = BattleExit(mock_send_input4, mock_battle_detector6, debug=False)

    still3 = battle_exit6.is_still_in_battle(frame_provider=lambda: None)
    check("帧获取失败 → 视为不在战斗", still3 is False)

    # ── Test 5: frame_provider 首次返回 None，重试后成功 ─────────────
    print("\n[Test 5] frame_provider 首次返回 None，重试后获取到帧")
    mock_send_input7 = MockSendInputSimulator()
    mock_battle_detector7 = MockBattleModeDetector(battle_results=[(True, 0.9)])
    battle_exit7 = BattleExit(mock_send_input7, mock_battle_detector7, debug=False)

    frame_call_count = [0]

    def flaky_provider() -> Optional[np.ndarray]:
        frame_call_count[0] += 1
        if frame_call_count[0] == 1:
            return None
        return dummy_frame

    still4 = battle_exit7.is_still_in_battle(frame_provider=flaky_provider)
    check("重试后成功检测到在战斗", still4 is True)
    check("frame_provider 被调用 2 次", frame_call_count[0] == 2)

    # ── Summary ─────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed == 0:
        print("All tests passed!")
    else:
        print(f"WARNING: {failed} test(s) failed!")
    print(f"{'=' * 50}")
    return failed == 0


if __name__ == "__main__":
    test_battle_exit()
