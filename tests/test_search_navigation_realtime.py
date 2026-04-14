#!/usr/bin/env python3
"""
SearchStrategy + NavigationStrategy 实机测试脚本

只覆盖两类动作：
1. 找不到目标时，执行小幅鼠标平移搜索
2. 检测到目标后，执行 WASD 靠近

不包含瞄准、投掷、战斗退出等后续流程。

运行方式：
    uv run python tests/test_search_navigation_realtime.py --model models/trained/luoke_pet.pt
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core import ObjectDetector, TargetScorer, WindowManager
from src.core.capabilities.interception_sim import (
    INTERCEPTION_AVAILABLE,
    InterceptionSimulator,
)
from src.core.capabilities.screen_cap import ScreenCaptureWithRegion
from src.core.context import AppContext
from src.logger import get_logger
from src.strategies.base import Action
from src.strategies.navigation_strategy import NavigationStrategy
from src.strategies.search_strategy import SearchStrategy


def _build_context(logger, width: int, height: int) -> AppContext:
    return AppContext(
        config={},
        logger=logger,
        window_region=(0, 0, width, height),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="SearchStrategy + NavigationStrategy 实机测试")
    parser.add_argument("--model", required=True, help="YOLO 模型路径")
    parser.add_argument("--process-name", default="NRC-Win64-Shipping.exe", help="游戏进程名")
    parser.add_argument("--fps", type=int, default=30, help="屏幕捕获帧率")
    parser.add_argument("--device", default="cuda", help="推理设备")
    parser.add_argument("--target-class", type=int, default=0, help="目标类别")
    parser.add_argument("--confidence", type=float, default=0.5, help="置信度阈值")
    parser.add_argument("--nms-iou", type=float, default=0.7, help="NMS IoU 阈值")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--search-step-px", type=int, default=40, help="搜索时每次鼠标平移像素")
    parser.add_argument("--max-iterations", type=int, default=0, help="最大循环次数，0 表示无限")
    parser.add_argument(
        "--auto-detect-mouse",
        dest="auto_detect_mouse",
        action="store_true",
        default=True,
        help="自动检测真实物理鼠标设备号（默认开启）",
    )
    parser.add_argument(
        "--no-auto-detect-mouse",
        dest="auto_detect_mouse",
        action="store_false",
        help="禁用自动检测真实物理鼠标",
    )
    parser.add_argument("--auto-detect-timeout", type=float, default=8.0, help="自动检测鼠标超时（秒）")
    args = parser.parse_args()

    logger = get_logger(debug=args.debug)

    print("=" * 72)
    print("  SearchStrategy + NavigationStrategy 实机测试")
    print("=" * 72)
    print("  范围：")
    print("  1. 无目标时执行鼠标小幅平移搜索")
    print("  2. 检测到目标后执行 WASD 靠近")
    print("  3. 不包含瞄准、投掷、战斗退出")
    print()
    print("  退出：Ctrl+C")
    print("=" * 72)

    if not INTERCEPTION_AVAILABLE:
        logger.error("Interception 驱动不可用，请先安装: pip install interception")
        return 1

    window_mgr = WindowManager(
        process_name=args.process_name,
        client_size=(1280, 720),
        debug=args.debug,
    )
    if not window_mgr.find_window():
        logger.error("未找到游戏窗口，请确认游戏已启动")
        return 1

    temp_region = window_mgr.get_screen_region()
    if temp_region is None:
        logger.error("无法获取窗口区域")
        return 1

    temp_cap = ScreenCaptureWithRegion(fps=5, debug=False, region=temp_region)
    with temp_cap:
        time.sleep(0.3)

    region = window_mgr.get_screen_region()
    if region is None:
        logger.error("重新获取窗口区域失败")
        return 1

    left, top, right, bottom = region
    width = right - left
    height = bottom - top

    logger.success(f"游戏客户区: ({left}, {top}, {width}x{height})")

    cap = ScreenCaptureWithRegion(fps=args.fps, debug=args.debug, region=region)
    detector = ObjectDetector(
        model_path=args.model,
        device=args.device,
        confidence_threshold=args.confidence,
        iou_threshold=args.nms_iou,
        debug=args.debug,
    )
    if not detector.load_model():
        logger.error("模型加载失败")
        return 1

    scorer = TargetScorer(
        screen_width=width,
        screen_height=height,
    )

    ctx = _build_context(logger, width, height)
    search_strategy = SearchStrategy(legacy_mouse_action=False)
    navigation_strategy = NavigationStrategy(center_tolerance=150, far_threshold=300, timeout_seconds=15.0)

    send_input = InterceptionSimulator(window_mgr=window_mgr, debug=args.debug)
    if args.auto_detect_mouse:
        try:
            detected = send_input.auto_detect_hardware_mouse(timeout_seconds=args.auto_detect_timeout)
            logger.success(f"已锁定真实物理鼠标设备号: {detected}")
        except Exception as exc:
            logger.warning(f"自动检测物理鼠标失败，将沿用当前设备: {exc}")

    logger.success("开始实机测试，只执行搜索与靠近动作")

    capture_interval = 1.0 / max(1, args.fps)
    iteration = 0

    try:
        with cap:
            while True:
                if args.max_iterations > 0 and iteration >= args.max_iterations:
                    logger.info(f"达到最大循环次数 {args.max_iterations}，退出")
                    return 0

                iteration += 1
                frame = cap.capture()
                if frame is None:
                    time.sleep(capture_interval * 0.1)
                    continue

                detections = detector.detect(frame, target_class=args.target_class)
                scored = scorer.score_detections(detections)

                ctx.detections = detections

                if scored:
                    ctx.verified_target = scored[0].detection
                    nav_action = navigation_strategy.execute(ctx)
                    move_params = navigation_strategy.get_movement_parameters(ctx)

                    if nav_action == Action.MOVE_WASD and move_params is not None:
                        direction, duration = move_params
                        logger.info(
                            f"[导航] 目标数={len(detections)} 方向={direction} 时长={duration:.2f}s"
                        )
                        send_input.press_key(direction, duration=duration)
                    elif nav_action == Action.NO_OP:
                        logger.info(f"[导航] 目标已足够近，目标数={len(detections)}")

                    # 有目标时，搜索策略应当让权并复位
                    search_action = search_strategy.execute(ctx)
                    if search_action != Action.NO_OP:
                        logger.warning(f"搜索策略在检测到目标时返回了异常动作: {search_action}")
                else:
                    ctx.verified_target = None
                    search_action = search_strategy.execute(ctx)
                    search_cmd = search_strategy.get_search_command()

                    if search_action in (Action.SEARCH_MOUSE, Action.SEARCH_PAN):
                        dx = int(search_cmd.params.get("dx", args.search_step_px))
                        dy = int(search_cmd.params.get("dy", 0))
                        pause_s = float(search_cmd.params.get("pause_s", capture_interval))
                        logger.info(f"[搜索-视角] dx={dx:+d}, dy={dy:+d}, pause={pause_s:.2f}s")
                        send_input.mouse_move(dx, dy)
                        time.sleep(min(1.5, max(0.02, pause_s)))
                    elif search_action == Action.SEARCH_MOVE:
                        direction = str(search_cmd.params.get("direction", "w"))
                        duration = float(search_cmd.params.get("duration", 0.3))
                        look_dx = int(search_cmd.params.get("look_dx", 0))
                        look_dy = int(search_cmd.params.get("look_dy", 0))
                        pause_s = float(search_cmd.params.get("pause_s", capture_interval))
                        logger.info(
                            f"[搜索-走位] key={direction}, duration={duration:.2f}s, "
                            f"look=({look_dx:+d},{look_dy:+d}), pause={pause_s:.2f}s"
                        )
                        if look_dx != 0 or look_dy != 0:
                            send_input.mouse_move(look_dx, look_dy)
                        send_input.press_key(direction, duration=duration)
                        time.sleep(min(1.5, max(0.02, pause_s)))
                    elif search_action == Action.NO_OP:
                        logger.info("[搜索] 达到周期上限，暂停一次")

                time.sleep(capture_interval)

    except KeyboardInterrupt:
        logger.info("收到中断信号，退出测试")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())