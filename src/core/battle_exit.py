#!/usr/bin/env python3
"""
战斗退出模块

当检测到战斗状态时，通过 SendInput 发送 ESC 键退出战斗界面，
然后使用 CV 检测是否出现战斗逃跑同意框，确认后再点击按钮，
最后通过 BattleModeDetector 轮询确认是否已退出战斗。

确认按钮坐标使用相对坐标 (rel_x, rel_y) 存储，
运行时根据当前帧尺寸换算为绝对坐标。
"""

import json
import os
import time
from typing import Callable, Optional, Tuple

import cv2
import numpy as np

from src.core.battle_mode_detector import BattleModeDetector
from src.core.sendinput_sim import SendInputSimulator
from src.logger import get_logger

# ── 配置常量 ──────────────────────────────────────────────────────────
DEFAULT_MAX_RETRIES = 3
DEFAULT_WAIT_AFTER_ESC = 1.5
WAIT_INCREMENT = 0.5  # 每次重试递增的等待时间（秒）
FRAME_RETRY_DELAY = 0.2  # 帧获取失败的重试等待（秒）

# 确认按钮默认位置（配置缺失时的 fallback）
DEFAULT_CONFIRM_REL_X = 0.5
DEFAULT_CONFIRM_REL_Y = 0.55

# 战斗逃跑同意框默认 ROI（配置缺失时的 fallback）
DEFAULT_EXIT_CONF_REL_X = 0.3
DEFAULT_EXIT_CONF_REL_Y = 0.35
DEFAULT_EXIT_CONF_REL_W = 0.4
DEFAULT_EXIT_CONF_REL_H = 0.3

# 配置路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "templates", "templates_config.json")

# 同意框匹配阈值
EXIT_CONFIRM_THRESH = 0.65


def _load_config() -> dict:
    """加载统一配置文件"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"templates": {}, "click_points": {}}


def _load_confirm_button() -> Tuple[float, float]:
    """从配置加载确认按钮的相对坐标。

    Returns:
        (rel_x, rel_y)
    """
    config = _load_config()
    btn = config.get("click_points", {}).get("confirm_button", {})
    return (
        btn.get("rel_x", DEFAULT_CONFIRM_REL_X),
        btn.get("rel_y", DEFAULT_CONFIRM_REL_Y),
    )


def _load_exit_confirm_roi() -> Tuple[float, float, float, float]:
    """从配置加载战斗逃跑同意框的 ROI。

    Returns:
        (rel_x, rel_y, rel_w, rel_h)
    """
    config = _load_config()
    roi = config.get("templates", {}).get("battle_exit_confirm", {})
    return (
        roi.get("rel_x", DEFAULT_EXIT_CONF_REL_X),
        roi.get("rel_y", DEFAULT_EXIT_CONF_REL_Y),
        roi.get("rel_w", DEFAULT_EXIT_CONF_REL_W),
        roi.get("rel_h", DEFAULT_EXIT_CONF_REL_H),
    )


def load_exit_confirm_template() -> Optional[np.ndarray]:
    """加载战斗逃跑同意框模板图片"""
    template_path = os.path.join(PROJECT_ROOT, "data", "templates", "battle_exit_confirm.png")
    if not os.path.exists(template_path):
        return None
    return cv2.imread(template_path)


class BattleExit:
    """通过按 ESC + CV 检测同意框 + 点击确认按钮退出战斗状态。"""

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
        self._exit_confirm_template: Optional[np.ndarray] = None
        self._exit_confirm_gray: Optional[np.ndarray] = None
        # 每次实例化时加载最新配置
        self._confirm_rel_x, self._confirm_rel_y = _load_confirm_button()
        self._exit_rel_x, self._exit_rel_y, self._exit_rel_w, self._exit_rel_h = _load_exit_confirm_roi()

    def _load_exit_template_once(self):
        """加载一次同意框模板，缓存灰度后结果"""
        if self._exit_confirm_template is None:
            self._exit_confirm_template = load_exit_confirm_template()
            if self._exit_confirm_template is None:
                self.logger.warning("未找到 battle_exit_confirm.png 模板，将跳过同意框 CV 检测")
            else:
                self._exit_confirm_gray = cv2.cvtColor(
                    self._exit_confirm_template, cv2.COLOR_BGR2GRAY
                )

    def _compute_click_pos(self, frame_w: int, frame_h: int) -> Tuple[int, int]:
        """根据当前帧尺寸，将相对坐标转为绝对坐标。"""
        return (
            int(self._confirm_rel_x * frame_w),
            int(self._confirm_rel_y * frame_h),
        )

    def _compute_roi(self, frame_w: int, frame_h: int) -> Tuple[int, int, int, int]:
        """根据当前帧尺寸，将相对 ROI 转为绝对坐标。"""
        return (
            int(self._exit_rel_x * frame_w),
            int(self._exit_rel_y * frame_h),
            int(self._exit_rel_w * frame_w),
            int(self._exit_rel_h * frame_h),
        )

    def _detect_exit_confirm_box(self, frame: np.ndarray) -> Tuple[bool, float]:
        """检测当前帧中是否出现了战斗逃跑同意框（使用缓存的灰度模板）。

        Args:
            frame: 当前帧 (BGR)

        Returns:
            (detected, confidence) — 是否检测到同意框及匹配置信度
        """
        if self._exit_confirm_gray is None:
            return False, 0.0

        frame_h, frame_w = frame.shape[:2]
        rx, ry, rw, rh = self._compute_roi(frame_w, frame_h)

        # 边界检查
        if rx < 0 or ry < 0 or rx + rw > frame_w or ry + rh > frame_h or rw <= 0 or rh <= 0:
            return False, 0.0

        roi = frame[ry:ry + rh, rx:rx + rw]
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        result = cv2.matchTemplate(roi_gray, self._exit_confirm_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)

        confidence = round(max_val, 4)
        detected = confidence >= EXIT_CONFIRM_THRESH

        return detected, confidence

    def exit_battle(
        self,
        frame_provider: Callable[[], Optional[np.ndarray]],
        max_retries: int = DEFAULT_MAX_RETRIES,
        wait_after_esc: float = DEFAULT_WAIT_AFTER_ESC,
    ) -> bool:
        """按 ESC + CV 检测同意框 + 点击确认按钮退出战斗状态。

        流程：
        1. 发送 ESC 键
        2. 等待确认按钮出现
        3. 获取当前帧，CV 检测是否出现战斗逃跑同意框
        4. 检测到同意框 → 点击确认按钮
        5. 检测是否还在战斗
        6. 不在战斗 → 返回 True；还在战斗 → 重试

        Args:
            frame_provider: 可调用对象，返回当前帧（numpy array 或 None）
            max_retries: 最大重试次数
            wait_after_esc: 首次按 ESC 后等待时间（秒）

        Returns:
            True 表示成功退出战斗状态，False 表示重试后仍在战斗中
        """
        self.logger.info(f"开始退出战斗流程 (max_retries={max_retries})")
        self._load_exit_template_once()

        for attempt in range(1, max_retries + 1):
            current_wait = wait_after_esc + (attempt - 1) * WAIT_INCREMENT

            self.logger.info(
                f"第 {attempt}/{max_retries} 次尝试:"
            )

            # 1. 发送 ESC 键
            self.logger.info("  发送 ESC...")
            try:
                self._send_input.press_key("esc", duration=0.1)
            except Exception as exc:
                self.logger.error(f"发送 ESC 键失败: {exc}")
                return False

            # 2. 等待确认按钮出现
            self.logger.info(f"  等待 {current_wait:.1f}s 让确认按钮出现...")
            time.sleep(current_wait)

            # 3. 获取当前帧
            frame = frame_provider()
            if frame is None:
                self.logger.warning("  无法获取帧，跳过本次重试")
                continue

            # 4. CV 检测战斗逃跑同意框
            if self._exit_confirm_template is not None:
                box_detected, box_conf = self._detect_exit_confirm_box(frame)
                self.logger.info(
                    f"  战斗逃跑同意框检测: {'检测到' if box_detected else '未检测到'} "
                    f"(confidence={box_conf:.4f}, threshold={EXIT_CONFIRM_THRESH})"
                )

                if not box_detected:
                    self.logger.warning("  未检测到同意框，可能 ESC 未生效，继续重试...")
                    continue
            else:
                self.logger.warning("  跳过同意框 CV 检测（模板未加载）")

            # 5. 点击确认按钮
            click_x, click_y = self._compute_click_pos(frame.shape[1], frame.shape[0])
            self.logger.info(f"  点击确认按钮 (客户区坐标: {click_x}, {click_y})...")
            try:
                self._send_input.mouse_move(click_x, click_y)
                time.sleep(0.1)
                self._send_input.mouse_click()
            except Exception as exc:
                self.logger.error(f"点击确认按钮失败: {exc}")
                return False

            # 6. 等待点击生效
            time.sleep(0.5)

            # 7. 检测是否还在战斗
            still_in_battle = self.is_still_in_battle(frame_provider)

            if not still_in_battle:
                self.logger.success("成功退出战斗状态")
                return True

            self.logger.warning(
                f"第 {attempt} 次后仍在战斗中，准备重试..."
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
            self.mouse_move_calls: list = []
            self.mouse_click_calls: list = []

        def press_key(self, key: str, duration: float = 0.2) -> int:
            self.press_key_calls.append((key, duration))
            return 2

        def mouse_move(self, rel_x: int, rel_y: int) -> int:
            self.mouse_move_calls.append((rel_x, rel_y))
            return 1

        def mouse_click(self) -> int:
            self.mouse_click_calls.append(())
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
