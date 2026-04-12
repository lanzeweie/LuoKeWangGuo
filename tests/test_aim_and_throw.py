#!/usr/bin/env python3
"""
aim_and_throw 实时测试脚本

测试内容：
1. 实时打框 - 持续显示检测到的目标边界框
2. 自动瞄准 - 鼠标移动到目标中心
3. 投掷执行 - mouse_down → 微调 → mouse_up

触发条件：检测到捕捉状态（精灵球界面）时自动执行

运行方式：
    uv run python tests.test_aim_and_throw --model models/trained/luoke_pet.pt
"""

import argparse
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent.parent))
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
    # 命令行参数解析
    parser = argparse.ArgumentParser(description="瞄准 + 投掷 实时测试")
    parser.add_argument("--model", required=True, help="YOLO模型路径")
    parser.add_argument("--process-name", default="NRC-Win64-Shipping.exe", help="游戏进程名")
    parser.add_argument("--resolution", default="auto", help="游戏分辨率 (默认auto自动检测)")
    parser.add_argument("--border-offset", type=int, default=0, help="边框裁剪偏移")
    parser.add_argument("--fps", type=int, default=30, help="屏幕捕获帧率")
    parser.add_argument("--device", default="cuda", help="推理设备")
    parser.add_argument("--target-class", type=int, default=0, help="目标类别")
    parser.add_argument("--confidence", type=float, default=0.5, help="置信度阈值")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--detection-interval", type=float, default=2.0, help="检测间隔(秒)")
    parser.add_argument("--max-distance", type=float, default=50.0, help="太远阈值")
    parser.add_argument("--near-threshold", type=float, default=100.0, help="靠近阈值")
    parser.add_argument("--capture-threshold", type=float, default=200.0, help="捕捉阈值")
    parser.add_argument("--center-offset-x", type=int, default=0, help="中心X偏移")
    parser.add_argument("--center-offset-y", type=int, default=0, help="中心Y偏移")
    args = parser.parse_args()

    # 解析分辨率 (auto 则从窗口动态获取)
    if args.resolution == "auto":
        width, height = None, None  # 待窗口管理器检测
    else:
        width, height = map(int, args.resolution.split("x"))

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
        client_size=(1280, 720),
        border_offset=args.border_offset,
        debug=args.debug,
    )
    if not window_mgr.find_window():
        logger.error("未找到游戏窗口，请确保游戏已运行")
        sys.exit(1)

    # 2. ScreenCapture 初始化（触发 dxcam 改变窗口尺寸）
    # ⚠️ dxcam 初始化后会改变窗口尺寸，需要先启动一次来触发变化
    logger.info("[2/6] 初始化屏幕捕获（触发窗口尺寸变化）...")
    from src.core.capabilities.screen_cap import ScreenCaptureWithRegion

    temp_region = window_mgr.get_screen_region()
    if temp_region is None:
        logger.error("获取捕获区域失败")
        sys.exit(1)

    # 临时启动 dxcam，触发窗口尺寸变化
    temp_cap = ScreenCaptureWithRegion(fps=5, debug=False, region=temp_region)
    with temp_cap:
        time.sleep(0.3)  # 等待 dxcam 初始化完成
        # dxcam 已改变窗口尺寸，现在重新获取 region
        pass

    # 退出 with 块后重新获取正确的 region
    region = window_mgr.get_screen_region()
    if region is None:
        logger.error("重新获取捕获区域失败")
        sys.exit(1)

    left, top, right, bottom = region
    game_width = right - left
    game_height = bottom - top
    width = game_width
    height = game_height

    logger.info(f"  region 参数: {region}")
    logger.info(f"  window_mgr.client_size: {window_mgr.client_size}")
    logger.info(f"  计算尺寸: {game_width}x{game_height}")
    logger.success(f"游戏客户区: ({left}, {top}, {game_width}x{game_height})")

    # 创建正式的 ScreenCapture 用于主循环
    cap = ScreenCaptureWithRegion(fps=args.fps, debug=args.debug, region=region)

    # 3. 目标检测
    logger.info("[3/6] 加载检测模型...")
    detector = ObjectDetector(
        model_path=args.model,
        device=args.device,
        confidence_threshold=args.confidence,
        debug=args.debug,
    )
    if not detector.load_model():
        logger.error("模型加载失败")
        sys.exit(1)

    # 4. 捕捉模式检测器
    logger.info("[4/6] 初始化捕捉模式检测器...")
    # 使用绝对路径确保模板能正确加载
    template_path = str(Path(__file__).parent.parent / "data" / "templates" / "capture_mode.png")
    logger.info(f"  模板路径: {template_path}")
    try:
        capture_detector = CaptureModeDetector(
            template_path=template_path,
            frame_size=(width, height),
            debug=args.debug,
        )
        logger.success("捕捉模式检测器初始化成功")
    except Exception as e:
        logger.warning(f"捕捉模式检测器初始化失败: {e}，将跳过模式检测")
        capture_detector = None

    # 5. 目标评分器
    scorer = TargetScorer(
        screen_width=width,
        screen_height=height,
        max_distance_threshold=args.max_distance,
        near_threshold=args.near_threshold,
        capture_threshold=args.capture_threshold,
        center_offset_x=args.center_offset_x,
        center_offset_y=args.center_offset_y,
    )

    # 6. 瞄准投掷器
    logger.info("[5/6] 初始化瞄准投掷器...")
    send_input = SendInputSimulator(window_mgr=window_mgr)
    aim_throw = AimAndThrow(send_input=send_input, debug=args.debug)

    # 7. 分层覆盖窗口
    logger.info("[6/6] 创建分层覆盖窗口...")
    overlay = LayeredOverlay(
        x=left, y=top,
        width=width, height=height,
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
    first_frame_logged = False        # 首帧是否已记录

    try:
        with cap:
            while True:
                loop_start = time.time()
                frame = cap.capture()

                # 等待捕获稳定（前几帧可能是 None）
                if frame is None:
                    time.sleep(capture_interval * 0.1)
                    continue

                # 首帧记录
                if not first_frame_logged:
                    h, w = frame.shape[:2]
                    logger.info(f"首帧尺寸: {w}x{h}")

                    # 打印当前 ROI 坐标
                    if capture_detector is not None:
                        roi_x, roi_y, roi_w, roi_h = capture_detector._get_roi()
                        logger.info(f"ROI 坐标: ({roi_x}, {roi_y}, {roi_w}, {roi_h})")

                    first_frame_logged = True

                # ── 检测捕捉状态 ──
                # 当用户按 E 键时，游戏会切换到捕捉状态
                # 我们通过 CV 检测来判断
                capture_detected = False
                if capture_detector is not None:
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
                        # 先将窗口置顶，确保 SendInput 正确工作
                        window_mgr.bring_to_foreground()
                        time.sleep(0.1)  # 等待窗口激活

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
                        logger.debug_msg(
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