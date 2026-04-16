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

from src.core import ObjectDetector, TargetScorer, WindowManager, LayeredOverlay
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
from src.strategies.search_patterns.enhanced_move_controller import EnhancedMoveController


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
    parser.add_argument("--max-radius", type=float, default=5.0, help="智能搜索最大活动半径")
    parser.add_argument("--scan-speed", type=float, default=30.0, help="智能搜索扫描速度（度/秒）")
    parser.add_argument("--scan-step", type=float, default=30.0, help="智能搜索每次扫描角度步长")
    parser.add_argument("--move-speed", type=float, default=3.0, help="智能搜索移动速度")
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
    parser.add_argument("--no-overlay", action="store_true", help="禁用覆盖层打框")
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

    # 伪距离阈值：< 40 执行捕捉，>= 40 靠近
    PSEUDO_DIST_CAPTURE_THRESHOLD = 40.0

    scorer = TargetScorer(
        screen_width=width,
        screen_height=height,
        far_threshold=40.0,   # 伪距离 > 40 → FAR（需靠近）
        near_threshold=15.0,  # 伪距离 15~40 → MEDIUM
    )

    ctx = _build_context(logger, width, height)
    search_strategy = SearchStrategy(
        pan_angle=5.0,
        max_pan_cycles=6,
        micro_cycles_before_upgrade=2,
        legacy_mouse_action=True,
    )
    navigation_strategy = NavigationStrategy(center_tolerance=80, far_threshold=300, timeout_seconds=15.0)

    # 分层覆盖窗口
    layered_overlay = None
    if not args.no_overlay:
        layered_overlay = LayeredOverlay(
            x=left, y=top,
            width=width, height=height,
            debug=args.debug,
        )
        if not layered_overlay.create_window():
            logger.error("分层窗口创建失败")
            return 1
        logger.success("分层覆盖窗口已创建")

    send_input = InterceptionSimulator(window_mgr=window_mgr, debug=args.debug)
    enhanced_move = EnhancedMoveController(send_input, debug=args.debug)
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

                # 绘制检测框
                if layered_overlay is not None:
                    layered_overlay.draw_scored(scored_detections=scored)

                ctx.detections = detections

                if scored:
                    top = scored[0]
                    pseudo_dist = top.estimated_distance
                    ctx.verified_target = top.detection

                    if pseudo_dist < PSEUDO_DIST_CAPTURE_THRESHOLD:
                        # 伪距离 < 40 → 执行捕捉
                        logger.info(
                            f"[捕捉] 伪距离={pseudo_dist:.1f} < {PSEUDO_DIST_CAPTURE_THRESHOLD}，"
                            f"执行捕捉！目标数={len(detections)}"
                        )
                        # TODO: 调用 aim_and_throw 执行捕捉
                    else:
                        # 伪距离 >= 40 → 持续按 W 前进（鼠标已对准目标）
                        nav_action = navigation_strategy.execute(ctx)

                        if nav_action == Action.MOVE_WASD:
                            # 持续前进，直到目标足够近或消失
                            logger.info(f"[靠近] 伪距离={pseudo_dist:.1f}，持续前进 W")
                            send_input.press_key('w', duration=0.3)
                        elif nav_action == Action.NO_OP:
                            # 目标已足够近
                            logger.info(f"[靠近] 目标已足够近（伪距离={pseudo_dist:.1f}），停止")

                    # 有目标时，搜索策略应当让权并复位
                    search_action = search_strategy.execute(ctx)
                    if search_action != Action.NO_OP:
                        logger.warning(f"搜索策略在检测到目标时返回了异常动作: {search_action}")
                else:
                    ctx.verified_target = None
                    search_action = search_strategy.execute(ctx)
                    search_cmd = search_strategy.get_search_command()

                    if search_action == Action.SEARCH_PAN:
                        # SearchStrategy 的扫描动作：带角度和停顿
                        angle = float(search_cmd.params.get("angle", args.scan_step))
                        speed = float(search_cmd.params.get("speed", args.scan_speed))
                        pause_s = float(search_cmd.params.get("pause_s", 0.1))
                        logger.info(f"[搜索-视角] 扫描角度={angle:.1f}°, 速度={speed:.1f}°/s, 停顿={pause_s:.2f}s")
                        enhanced_move.execute_scan_with_pause(angle, pause_s)
                    elif search_action == Action.SEARCH_MOVE:
                        # SearchStrategy 的 8 方向移动
                        direction = str(search_cmd.params.get("direction", "W"))
                        duration = float(search_cmd.params.get("duration", 0.5))
                        pause_s = float(search_cmd.params.get("pause_s", 0.0))
                        pan_angle, pan_dir = search_strategy.get_pan_parameters()
                        logger.info(
                            f"[搜索-走位] 方向={direction}, 时长={duration:.2f}s, "
                            f"停顿={pause_s:.2f}s"
                        )
                        enhanced_move.execute_direction_move(direction, duration)
                        if pause_s > 0:
                            time.sleep(min(1.5, max(0.02, pause_s)))
                    elif search_action in (Action.SEARCH_MOUSE,):
                        # 旧版鼠标平移搜索（兼容）
                        dx = int(search_cmd.params.get("dx", args.search_step_px))
                        dy = int(search_cmd.params.get("dy", 0))
                        pause_s = float(search_cmd.params.get("pause_s", capture_interval))
                        logger.info(f"[搜索-视角(旧)] dx={dx:+d}, dy={dy:+d}, pause={pause_s:.2f}s")
                        send_input.mouse_move(dx, dy)
                        time.sleep(min(1.5, max(0.02, pause_s)))
                    elif search_action == Action.NO_OP:
                        logger.info("[搜索] 达到周期上限，暂停一次")

                time.sleep(capture_interval)

    except KeyboardInterrupt:
        logger.info("收到中断信号，退出测试")
    finally:
        if layered_overlay is not None:
            layered_overlay.destroy()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())