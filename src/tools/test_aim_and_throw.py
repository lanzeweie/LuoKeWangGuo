#!/usr/bin/env python3
"""
aim_and_throw 实时测试脚本

测试内容：
1. 实时打框 - 持续显示检测到的目标边界框
2. 自动瞄准 - 鼠标移动到目标中心
3. 投掷执行 - mouse_down → 微调 → mouse_up

触发条件：检测到捕捉状态（精灵球界面）时自动执行

运行方式：
    uv run python -m src.tools.test_aim_and_throw
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import parse_args
from src.core import (
    WindowManager,
    ScreenCapture,
    ObjectDetector,
    LayeredOverlay,
    CaptureModeDetector,
)
from src.core.capabilities.target_scoring import TargetScorer
from src.core.capabilities.sendinput_sim import SendInputSimulator
from src.actions.aim_and_throw import AimAndThrow
from src.logger import get_logger


def main():
    args = parse_args()
    logger = get_logger(debug=args.debug)

    print("=" * 60)
    print("  瞄准 + 投掷 实时测试")
    print("=" * 60)
    print("  测试内容:")
    print("  1. 实时打框 - 持续显示目标边界框")
    print("  2. 自动瞄准 - 鼠标移动到目标中心")
    print("  3. 投掷执行 - mouse_down → 微调 → mouse_up")
    print()
    print("  触发条件:")
    print("  - 检测到捕捉状态（精灵球界面）+ 有目标")
    print("  - 每次捕捉状态切换仅执行一次投掷")
    print()
    print("  操作步骤:")
    print("  1. 确保游戏窗口已打开并获取焦点")
    print("  2. 走到有精灵的位置")
    print("  3. 按 E 键进入捕捉模式 → 自动瞄准投掷")
    print("  4. 再次按 E 重试")
    print("  5. 按 Ctrl+C 退出")
    print("=" * 60)

    # 1. 窗口管理
    logger.info("[1/6] 初始化窗口管理...")
    window_mgr = WindowManager(
        process_name=args.process_name,
        client_size=(args.width, args.height),
        border_offset=args.border_offset,
        debug=args.debug,
    )
    if not window_mgr.find_window():
        logger.error("未找到游戏窗口，请确保游戏已运行")
        sys.exit(1)

    region = window_mgr.get_screen_region()
    if region is None:
        logger.error("获取捕获区域失败")
        sys.exit(1)
    left, top, right, bottom = region
    game_width = right - left
    game_height = bottom - top
    logger.success(f"游戏客户区: ({left}, {top}, {game_width}x{game_height})")

    # 2. 屏幕捕获
    logger.info("[2/6] 初始化屏幕捕获...")
    cap = ScreenCapture(fps=args.fps, debug=args.debug)
    if not cap.start(region=region):
        logger.error("屏幕捕获启动失败")
        sys.exit(1)

    # 3. 目标检测
    logger.info("[3/6] 加载检测模型...")
    detector = ObjectDetector(
        model_path=args.model_path,
        device=args.device,
        confidence_threshold=args.confidence_threshold,
        debug=args.debug,
    )
    if not detector.load_model():
        logger.error("模型加载失败")
        sys.exit(1)

    # 4. 捕捉模式检测器
    logger.info("[4/6] 初始化捕捉模式检测器...")
    capture_detector = CaptureModeDetector(
        template_path="data/templates/capture_mode.png",
        debug=args.debug,
    )
    if not capture_detector.load_template():
        logger.warning("捕捉模式模板加载失败，将跳过模式检测")

    # 5. 目标评分器
    scorer = TargetScorer(
        screen_width=args.width,
        screen_height=args.height,
        max_distance_threshold=args.max_distance_threshold,
        near_threshold=args.near_threshold,
        capture_threshold=args.capture_threshold,
        center_offset_x=args.screen_center_offset_x,
        center_offset_y=args.screen_center_offset_y,
    )

    # 6. 瞄准投掷器
    logger.info("[5/6] 初始化瞄准投掷器...")
    send_input = SendInputSimulator(window_handle=window_mgr.handle)
    aim_throw = AimAndThrow(send_input=send_input, debug=args.debug)

    # 7. 分层覆盖窗口
    logger.info("[6/6] 创建分层覆盖窗口...")
    overlay = LayeredOverlay(
        x=left, y=top,
        width=args.width, height=args.height,
        debug=args.debug,
    )
    if not overlay.create_window():
        logger.error("分层窗口创建失败")
        sys.exit(1)

    logger.success("\n" + "=" * 60)
    logger.success("所有模块就绪！")
    logger.success("=" * 60)
    logger.info("等待捕捉状态 + 目标...")
    logger.info("按 Ctrl+C 退出\n")

    # ── 主循环 ──
    capture_interval = 1.0 / args.fps
    detect_interval = args.detection_interval
    last_detect_time = 0.0

    # 状态
    is_capture_mode = False      # 当前是否在捕捉模式
    has_target = False          # 当前是否有目标
    throw_executed_this_cycle = False  # 本次捕捉周期是否已执行投掷
    last_capture_state = False       # 上一次捕捉状态

    try:
        with cap:
            while True:
                loop_start = time.time()
                frame = cap.capture()
                if frame is None:
                    time.sleep(capture_interval * 0.1)
                    continue

                # ── 检测捕捉状态 ──
                # 当用户按 E 键时，游戏会切换到捕捉状态
                # 我们通过 CV 检测来判断
                capture_detected = False
                if capture_detector.is_ready():
                    capture_detected, confidence = capture_detector.is_capture_mode(frame)
                else:
                    # 如果没有模板，假设always in capture mode for testing
                    # 用户可以通过按 E 来模拟
                    pass

                # 检测捕捉状态变化（上升沿）
                if capture_detected and not last_capture_state:
                    logger.info("【检测到捕捉状态切换】开始瞄准投掷...")
                    is_capture_mode = True
                    throw_executed_this_cycle = False  # 重置投掷标志

                last_capture_state = capture_detected

                # ── 检测（按可配置间隔） ──
                now = time.time()
                if (now - last_detect_time) >= detect_interval:
                    detections = detector.detect(frame, target_class=args.target_class)
                    last_detect_time = now

                    # 评分与排序
                    scored = scorer.score_detections(detections)

                    # 更新状态
                    has_target = len(scored) > 0
                    target = scored[0] if has_target else None

                    # ── 实时打框（持续显示） ──
                    state_text = "捕捉中" if is_capture_mode else "SEARCH"
                    overlay.draw_scored(
                        scored,
                        verification_progress=1 if is_capture_mode else 0,
                        verification_required=1,
                        current_state=state_text,
                    )

                    # ── 自动瞄准 + 投掷执行 ──
                    # 触发条件：捕捉模式激活 + 有目标 + 本次周期未执行
                    if is_capture_mode and has_target and not throw_executed_this_cycle:
                        logger.info("=" * 50)
                        logger.info("【自动瞄准 + 投掷】")
                        logger.info(f"  目标中心: {target.detection.center}")
                        logger.info(f"  置信度: {target.detection.confidence:.3f}")
                        logger.info(f"  距离状态: {target.distance_state}")
                        logger.info("=" * 50)

                        # 执行瞄准投掷
                        success = aim_throw.aim_and_throw(
                            target=target,
                            screen_width=game_width,
                            screen_height=game_height,
                            fine_tune_ms=500,
                        )

                        if success:
                            logger.success("✓ 投掷执行成功")
                        else:
                            logger.error("✗ 投掷执行失败")

                        # 标记本次周期已执行
                        throw_executed_this_cycle = True

                        # 重置捕捉模式（等待用户再次按 E）
                        is_capture_mode = False
                        logger.info("捕捉周期结束，等待再次进入捕捉模式...")

                    # 打印检测信息
                    if has_target:
                        t = target.detection
                        capture_str = "【捕捉中】" if is_capture_mode else ""
                        logger.debug(
                            f"{capture_str} "
                            f"目标={t.center}, 置信度={t.confidence:.2f}, "
                            f"距离={target.distance_state}"
                        )
                else:
                    # 没有检测时也更新 overlay
                    state_text = "捕捉中" if is_capture_mode else "SEARCH"
                    overlay.draw_scored(
                        [],
                        verification_progress=1 if is_capture_mode else 0,
                        verification_required=1,
                        current_state=state_text,
                    )

                # ── 帧率限制 ──
                elapsed = time.time() - loop_start
                if elapsed < capture_interval:
                    time.sleep(capture_interval - elapsed)

    except KeyboardInterrupt:
        logger.info("\n用户中断，退出")
    finally:
        overlay.destroy()
        detector.unload_model()
        logger.info("已清理资源")


if __name__ == "__main__":
    main()