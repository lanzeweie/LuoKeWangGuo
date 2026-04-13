#!/usr/bin/env python3
"""
瞄准与投掷模块

实现目标中心瞄准 + 按住鼠标 + 松开鼠标的投掷逻辑。
集成阶段2算法：距离补偿、动量预测、平滑滤波。
- 使用 InterceptionSimulator 的 mouse_move_to（贝塞尔曲线 + 拟人化算法）
- mouse_down / mouse_up 完成投掷
- 投掷时序：平滑 → 补偿 → 预测 → 快速定位 → 按住 → 持续瞄准3秒 → 微调 → 松开
"""

from __future__ import annotations

import random
import time
from typing import Optional

from src.core.capabilities.target_scoring import TargetScore
from src.core.capabilities.interception_sim import InterceptionSimulator
from src.core.capabilities.aim_algorithms import (
    calculate_drop_compensation,
    MovementPredictor,
    SmoothFilter,
)
from src.logger import get_logger


class AimAndThrow:
    """瞄准目标并执行精灵球投掷。"""

    # 瞄准参数
    AIM_TOLERANCE = 40  # 目标中心与准心最大允许偏差（像素）
    AIM_DURATION = 3.0  # 瞄准持续时间（秒）
    MOUSE_TO_VIEW_RATIO = 1.0  # 鼠标移动与视角移动比例 (1:1)

    def __init__(
        self,
        send_input: InterceptionSimulator,
        debug: bool = False,
        use_compensation: bool = True,
        use_prediction: bool = True,
        use_smoothing: bool = True,
        smoothing_alpha: float = 0.3,
        flight_time: float = 0.5,
    ) -> None:
        """
        Args:
            send_input: InterceptionSimulator 实例（已注入）
            debug: 是否启用调试日志
            use_compensation: 是否启用距离补偿
            use_prediction: 是否启用动量预测
            use_smoothing: 是否启用平滑滤波
            smoothing_alpha: 平滑系数（越小越平滑）
            flight_time: 精灵球预估飞行时间（秒）
        """
        self._send_input = send_input
        self.debug = debug
        self._log = get_logger(debug=debug)

        # 算法开关
        self._use_compensation = use_compensation
        self._use_prediction = use_prediction
        self._use_smoothing = use_smoothing
        self._flight_time = flight_time

        # 算法实例
        self._smooth_filter = SmoothFilter(alpha=smoothing_alpha)
        self._movement_predictor = MovementPredictor()

    def reset_algorithms(self) -> None:
        """重置所有算法状态（切换目标时调用）。"""
        self._smooth_filter.reset()
        self._movement_predictor.reset()

    # ── public ──────────────────────────────────────────────────────

    def _get_aim_offset(
        self,
        target_x: int,
        target_y: int,
        screen_width: int,
        screen_height: int,
    ) -> tuple[int, int]:
        """计算目标中心与屏幕准心的偏差。

        Args:
            target_x, target_y: 目标中心坐标
            screen_width, screen_height: 屏幕客户区尺寸

        Returns:
            (offset_x, offset_y) - 鼠标需要移动的偏移量
           正值表示需要向右/下移动鼠标（让目标往左/上移）
        """
        center_x = screen_width // 2
        center_y = screen_height // 2

        # 计算偏差：目标在准心右/下，需要向左/上移动鼠标
        # 但游戏控制可能是反向的，这里假设正向（向右移鼠标，视角向右）
        offset_x = (center_x - target_x) * self.MOUSE_TO_VIEW_RATIO
        offset_y = (center_y - target_y) * self.MOUSE_TO_VIEW_RATIO

        return int(offset_x), int(offset_y)

    def _is_aimed(
        self,
        target_x: int,
        target_y: int,
        screen_width: int,
        screen_height: int,
    ) -> bool:
        """检查目标是否已在准心范围内。"""
        center_x = screen_width // 2
        center_y = screen_height // 2

        dx = abs(target_x - center_x)
        dy = abs(target_y - center_y)

        return dx <= self.AIM_TOLERANCE and dy <= self.AIM_TOLERANCE

    def _apply_aim_algorithms(
        self,
        cx: int,
        cy: int,
        screen_width: int,
        screen_height: int,
        bbox_area: float,
    ) -> tuple[int, int]:
        """应用阶段2算法流水线：平滑 → 预测 → 补偿。

        Args:
            cx: 目标中心 X
            cy: 目标中心 Y
            screen_width/height: 屏幕客户区尺寸
            bbox_area: 目标边界框面积

        Returns:
            (aim_x, aim_y) - 最终瞄准坐标
        """
        # Step A: 平滑滤波
        if self._use_smoothing:
            smooth_x, smooth_y = self._smooth_filter.process(float(cx), float(cy))
            if self.debug:
                self._log.debug_msg(
                    f"平滑滤波: ({cx},{cy}) -> ({smooth_x:.1f},{smooth_y:.1f})"
                )
        else:
            smooth_x, smooth_y = float(cx), float(cy)

        # Step B: 动量预测（只在启用时更新历史）
        if self._use_prediction:
            self._movement_predictor.update(smooth_x, smooth_y)
            pred_x, pred_y = self._movement_predictor.predict(self._flight_time)
            if self.debug:
                self._log.debug_msg(
                    f"动量预测: ({smooth_x:.1f},{smooth_y:.1f}) -> ({pred_x:.1f},{pred_y:.1f})"
                )
        else:
            pred_x, pred_y = smooth_x, smooth_y

        # Step C: 距离补偿
        if self._use_compensation:
            screen_area = screen_width * screen_height
            y_comp = calculate_drop_compensation(
                bbox_area=bbox_area,
                screen_area=screen_area,
            )
            aim_x = int(pred_x)
            aim_y = int(pred_y) + y_comp
            if self.debug:
                self._log.debug_msg(
                    f"距离补偿: area={bbox_area:.0f}, "
                    f"y_comp={y_comp}, aim=({aim_x},{aim_y})"
                )
        else:
            aim_x = int(pred_x)
            aim_y = int(pred_y)

        # 钳制到屏幕范围内
        aim_x = max(0, min(aim_x, screen_width - 1))
        aim_y = max(0, min(aim_y, screen_height - 1))

        return aim_x, aim_y

    def aim_and_throw(
        self,
        target: TargetScore,
        screen_width: int = 1280,
        screen_height: int = 720,
        fine_tune_ms: int = 500,
        get_target_func: Optional[callable] = None,
    ) -> bool:
        """
        瞄准目标中心并执行投掷。

        流程（新逻辑）：
        1. 快速定位：鼠标快速移动让目标接近准心
        2. 按住左键进入投掷瞄准状态
        3. 持续瞄准3秒：根据 YOLO 实时检测结果调整鼠标，让目标保持在准心附近
        4. 微调：小幅微调增加拟人化
        5. 松开鼠标完成投掷

        Args:
            target: 初始目标评分对象（含 detection.center, bbox_area, distance_state）
            screen_width/height: 屏幕客户区尺寸
            fine_tune_ms: 微调时长（毫秒），默认 500
            get_target_func: 可选的回调函数，用于获取实时目标位置。
                            签名: () -> Optional[tuple[int, int]]
                            返回 YOLO 检测的目标中心 (cx, cy)，或 None

        Returns:
            True 表示投掷操作完成，False 表示目标无效或失败
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

        # ── Step 1: 快速定位：让目标接近准心 ──

        # 应用算法流水线（平滑 → 预测 → 补偿）
        aim_x, aim_y = self._apply_aim_algorithms(
            cx=cx,
            cy=cy,
            screen_width=screen_width,
            screen_height=screen_height,
            bbox_area=target.bbox_area,
        )

        if self.debug:
            self._log.debug_msg(
                f"aim_and_throw: 初始目标=({cx},{cy}), 算法处理=({aim_x},{aim_y})"
            )

        # 计算初始偏移并快速移动
        offset_x, offset_y = self._get_aim_offset(
            aim_x, aim_y, screen_width, screen_height
        )

        if abs(offset_x) > 10 or abs(offset_y) > 10:
            try:
                # 使用相对移动进行快速定位
                self._send_input.mouse_move(offset_x, offset_y)
                if self.debug:
                    self._log.debug_msg(
                        f"aim_and_throw: 快速定位 offset=({offset_x},{offset_y})"
                    )
            except Exception as exc:
                if self.debug:
                    self._log.debug_msg(f"aim_and_throw: 快速定位失败: {exc}")
                return False

        # 短暂等待让视角稳定
        time.sleep(random.uniform(0.05, 0.10))

        # ── Step 2: 按住左键进入投掷瞄准状态 ──

        try:
            self._send_input.mouse_down()
        except Exception as exc:
            if self.debug:
                self._log.debug_msg(f"aim_and_throw: mouse_down 失败: {exc}")
            return False

        if self.debug:
            self._log.debug_msg("aim_and_throw: 已按住左键，开始持续瞄准...")

        # ── Step 3: 持续瞄准 3 秒 ──

        aim_start_time = time.time()
        aim_end_time = aim_start_time + self.AIM_DURATION

        # 瞄准循环参数
        check_interval = 0.050  # 每 50ms 检查一次
        max_move_per_check = 30  # 每次检查最大移动像素数（避免过快）

        while time.time() < aim_end_time:
            # 获取实时目标位置
            if get_target_func is not None:
                current_target = get_target_func()
                if current_target is None:
                    # 目标丢失，继续使用最后已知位置
                    if self.debug:
                        self._log.debug_msg("aim_and_throw: 实时目标丢失，使用最后位置")
                    continue
                cx, cy = current_target

            # 检查目标是否在准心范围内
            if self._is_aimed(cx, cy, screen_width, screen_height):
                # 已瞄准，无需调整
                if self.debug and random.random() < 0.05:  # 偶尔记录
                    self._log.debug_msg(f"aim_and_throw: 目标已瞄准 ({cx},{cy})")
            else:
                # 计算需要的调整量
                offset_x, offset_y = self._get_aim_offset(
                    cx, cy, screen_width, screen_height
                )

                # 限制单次移动量
                offset_x = max(-max_move_per_check, min(max_move_per_check, offset_x))
                offset_y = max(-max_move_per_check, min(max_move_per_check, offset_y))

                # 应用调整
                if abs(offset_x) > 2 or abs(offset_y) > 2:
                    try:
                        self._send_input.mouse_move(offset_x, offset_y)
                        if self.debug:
                            self._log.debug_msg(
                                f"aim_and_throw: 调整 offset=({offset_x},{offset_y}) "
                                f"目标=({cx},{cy})"
                            )
                    except Exception as exc:
                        if self.debug:
                            self._log.debug_msg(f"aim_and_throw: 调整失败: {exc}")

            # 等待下一次检查
            time.sleep(check_interval)

        if self.debug:
            self._log.debug_msg(f"aim_and_throw: 瞄准完成，耗时 {self.AIM_DURATION}秒")

        # ── Step 4: 微调（拟人化） ──

        if fine_tune_ms > 0:
            hold_duration = max(300, min(fine_tune_ms, 600)) / 1000.0  # clamp 300-600ms
            time.sleep(hold_duration * 0.5)

            # 小幅微调 ±5px
            try:
                micro_x = random.randint(-5, 5)
                micro_y = random.randint(-5, 5)
                if micro_x != 0 or micro_y != 0:
                    self._send_input.mouse_move(micro_x, micro_y)
                    if self.debug:
                        self._log.debug_msg(
                            f"aim_and_throw: 微调 ({micro_x},{micro_y})"
                        )
            except Exception as exc:
                if self.debug:
                    self._log.debug_msg(f"aim_and_throw: 微调失败: {exc}")

            time.sleep(hold_duration * 0.5)

        # ── Step 5: 松开鼠标完成投掷 ──

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

        同样经过平滑 → 预测 → 补偿的算法流水线。

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

        # 应用算法流水线
        aim_x, aim_y = self._apply_aim_algorithms(
            cx=cx,
            cy=cy,
            screen_width=screen_width,
            screen_height=screen_height,
            bbox_area=target.bbox_area,
        )

        if self.debug:
            self._log.debug_msg(
                f"aim_only: 原始=({cx},{cy}), 瞄准=({aim_x},{aim_y})"
            )

        try:
            self._send_input.mouse_move_to(aim_x, aim_y)
        except Exception as exc:
            if self.debug:
                self._log.debug_msg(f"aim_only: mouse_move_to 失败: {exc}")
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

    def mouse_move_to(self, abs_x: int, abs_y: int) -> int:
        self.calls.append(("mouse_move_to", (abs_x, abs_y)))
        return 1

    def mouse_down(self) -> int:
        self.calls.append(("mouse_down", ()))
        return 1

    def mouse_up(self) -> int:
        self.calls.append(("mouse_up", ()))
        return 1


def _make_target(cx: int, cy: int) -> TargetScore:
    """Helper to construct a minimal TargetScore for tests.

    bbox_area 设为 15000 (约 122x122 的框)，处于 CLOSE 范围
    （> 1.5% 屏幕面积 = 13824），补偿为 0。
    """
    from src.core.capabilities.detection import DetectionResult

    half = 61  # 122x122 -> area = 14884 (> 13824, CLOSE)
    det = DetectionResult(
        x1=cx - half,
        y1=cy - half,
        x2=cx + half,
        y2=cy + half,
        confidence=0.95,
        class_id=0,
    )
    return TargetScore(
        detection=det,
        distance_to_center=0.0,
        bbox_area=float(half * 2 * half * 2),  # 14884
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

    print("[Test 1] aim_only calls mouse_move_to with correct coordinates...")
    mock = _MockSendInput()
    thrower = AimAndThrow(send_input=mock, debug=False)
    target = _make_target(cx=640, cy=360)  # center of 1280x720
    result = thrower.aim_only(target, screen_width=1280, screen_height=720)
    check("returns True", result is True)
    check("calls mouse_move_to once", len([c for c in mock.calls if c[0] == "mouse_move_to"]) == 1)
    check("coordinates are (640, 360) for center target",
          mock.calls[0] == ("mouse_move_to", (640, 360)))

    # Off-center target
    mock2 = _MockSendInput()
    thrower2 = AimAndThrow(send_input=mock2, debug=False)
    target2 = _make_target(cx=740, cy=410)  # off-center position
    result2 = thrower2.aim_only(target2, screen_width=1280, screen_height=720)
    check("off-center returns True", result2 is True)
    check("coordinates are (740, 410)",
          mock2.calls[0] == ("mouse_move_to", (740, 410)))

    print("\n[Test 2] aim_and_throw call order: move (if needed) -> down -> up...")
    mock3 = _MockSendInput()
    thrower3 = AimAndThrow(send_input=mock3, debug=False)
    target3 = _make_target(cx=640, cy=360)
    # 使用极短的瞄准时间进行测试
    thrower3.AIM_DURATION = 0.1
    result3 = thrower3.aim_and_throw(
        target3, screen_width=1280, screen_height=720, fine_tune_ms=100
    )
    check("returns True", result3 is True)

    call_names = [c[0] for c in mock3.calls]
    check("mouse_down present", "mouse_down" in call_names)
    check("mouse_up present", "mouse_up" in call_names)
    check("mouse_down before mouse_up",
          call_names.index("mouse_down") < call_names.index("mouse_up"))

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

    print("\n[Test 5] _get_aim_offset calculates correctly...")
    thrower6 = AimAndThrow(send_input=_MockSendInput(), debug=False)
    # 目标在中心右下，需要向左上移动鼠标
    ox, oy = thrower6._get_aim_offset(700, 400, 1280, 720)
    check("center (640,360), target (700,400), offset x negative", ox < 0)
    check("center (640,360), target (700,400), offset y negative", oy < 0)
    # 目标在中心左上，需要向右下移动鼠标
    ox2, oy2 = thrower6._get_aim_offset(500, 300, 1280, 720)
    check("center (640,360), target (500,300), offset x positive", ox2 > 0)
    check("center (640,360), target (500,300), offset y positive", oy2 > 0)

    print("\n[Test 6] _is_aimed checks tolerance correctly...")
    thrower7 = AimAndThrow(send_input=_MockSendInput(), debug=False)
    check("center target is aimed",
          thrower7._is_aimed(640, 360, 1280, 720))
    check("target within tolerance is aimed",
          thrower7._is_aimed(650, 350, 1280, 720))  # offset 10,10
    check("target at tolerance edge is aimed",
          thrower7._is_aimed(680, 360, 1280, 720))  # offset 40,0
    check("target outside tolerance is not aimed",
          not thrower7._is_aimed(700, 360, 1280, 720))  # offset 60,0

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
