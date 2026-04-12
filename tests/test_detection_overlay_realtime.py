#!/usr/bin/env python3
"""
detection_overlay 实时测试脚本

测试内容：
1. 跳帧检测 - 每 N 帧运行一次 YOLO 推理
2. 目标跟踪 - IoU 匹配 + 匈牙利算法
3. 状态机 - Candidate → Active → Lost → Destroy
4. 插值平滑 - Lerp 平滑框体位置
5. 实时打框 - 在分层窗口显示检测框

运行方式：
    uv run python -m tests.test_detection_overlay_realtime --model models/trained/luoke_pet.pt
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.core import (
    WindowManager,
    ScreenCapture,
    ObjectDetector,
    LayeredOverlay,
)
from src.core.capabilities.detection_overlay import DetectionOverlay
from src.logger import get_logger


def main():
    parser = argparse.ArgumentParser(description="DetectionOverlay 实时测试")
    parser.add_argument("--model", required=True, help="YOLO模型路径")
    parser.add_argument("--process-name", default="NRC-Win64-Shipping.exe", help="游戏进程名")
    parser.add_argument("--fps", type=int, default=30, help="屏幕捕获帧率")
    parser.add_argument("--device", default="cuda", help="推理设备")
    parser.add_argument("--confidence", type=float, default=0.5, help="置信度阈值")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--detect-interval", type=int, default=3, help="跳帧间隔(每N帧检测一次)")
    parser.add_argument("--lerp-alpha", type=float, default=0.3, help="插值平滑系数")
    parser.add_argument("--confirm-frames", type=int, default=3, help="候选确认帧数")
    parser.add_argument("--lost-tolerance", type=int, default=5, help="丢失容错帧数")
    parser.add_argument("--iou-threshold", type=float, default=0.3, help="IoU 匹配阈值")
    parser.add_argument("--no-draw", action="store_true", help="禁用打框")
    args = parser.parse_args()

    logger = get_logger(debug=args.debug)

    print("=" * 60)
    print("  DetectionOverlay 实时测试")
    print("=" * 60)
    print(f"  跳帧间隔: {args.detect_interval}")
    print(f"  插值平滑: {args.lerp_alpha}")
    print(f"  候选确认: {args.confirm_frames}")
    print(f"  丢失容错: {args.lost_tolerance}")
    print(f"  IoU 阈值: {args.iou_threshold}")
    print("=" * 60)

    # 1. 窗口管理
    logger.info("[1/5] 初始化窗口管理...")
    window_mgr = WindowManager(
        process_name=args.process_name,
        client_size=(1280, 720),
        debug=args.debug,
    )
    if not window_mgr.find_window():
        logger.error("未找到游戏窗口")
        sys.exit(1)

    # 2. ScreenCapture
    logger.info("[2/5] 初始化屏幕捕获...")
    from src.core.capabilities.screen_cap import ScreenCaptureWithRegion

    temp_region = window_mgr.get_screen_region()
    temp_cap = ScreenCaptureWithRegion(fps=5, debug=False, region=temp_region)
    with temp_cap:
        time.sleep(0.3)

    region = window_mgr.get_screen_region()
    left, top, right, bottom = region
    game_width, game_height = right - left, bottom - top
    logger.info(f"  客户区: {game_width}x{game_height}")

    cap = ScreenCaptureWithRegion(fps=args.fps, debug=args.debug, region=region)

    # 3. 目标检测器
    logger.info("[3/5] 加载检测模型...")
    detector = ObjectDetector(
        model_path=args.model,
        device=args.device,
        confidence_threshold=args.confidence,
        debug=args.debug,
    )
    if not detector.load_model():
        logger.error("模型加载失败")
        sys.exit(1)

    # 4. DetectionOverlay
    logger.info("[4/5] 初始化 DetectionOverlay...")
    overlay_det = DetectionOverlay(
        detector=detector,
        screen_width=game_width,
        screen_height=game_height,
        detect_interval=args.detect_interval,
        lerp_alpha=args.lerp_alpha,
        confirm_frames=args.confirm_frames,
        lost_tolerance=args.lost_tolerance,
        iou_threshold=args.iou_threshold,
        draw_boxes=not args.no_draw,
        min_confidence=args.confidence,
        debug=args.debug,
    )

    # 5. 分层覆盖窗口
    logger.info("[5/5] 创建分层覆盖窗口...")
    layered_overlay = LayeredOverlay(
        x=left, y=top,
        width=game_width, height=game_height,
        debug=args.debug,
    )
    if not layered_overlay.create_window():
        logger.error("分层窗口创建失败")
        sys.exit(1)

    logger.success("就绪！观察分层窗口中的检测框，按 Ctrl+C 退出\n")

    # 先测试一下检测器
    test_frame = cap.capture()
    if test_frame is not None:
        h, w = test_frame.shape[:2]
        logger.info(f"测试帧尺寸: {w}x{h}")
        test_dets = detector.detect(test_frame)
        logger.info(f"直接检测结果: {len(test_dets)} 个目标")
        for i, d in enumerate(test_dets):
            logger.info(f"  [{i}] 置信度={d.confidence:.3f} 位置=({d.x1},{d.y1},{d.x2},{d.y2})")

    capture_interval = 1.0 / args.fps
    frame_count = 0

    try:
        with cap:
            while True:
                loop_start = time.time()
                frame = cap.capture()

                if frame is None:
                    logger.warning("frame is None")
                    time.sleep(capture_interval * 0.1)
                    continue

                frame_count += 1

                # 更新 DetectionOverlay
                targets = overlay_det.update(frame)

                # 打印检测信息
                if frame_count % 30 == 0 or targets:
                    detect_mark = "YOLO" if overlay_det.is_detect_frame else "LERP"
                    active_count = len([t for t in targets if t.state == "active"])
                    lost_count = len([t for t in targets if t.state == "lost"])
                    cand_count = len([t for t in targets if t.state == "candidate"])
                    # 打印每个目标的详细信息
                    target_info = []
                    for t in targets:
                        target_info.append(f"ID{t.track_id}({t.state}):({t.bbox[0]:.0f},{t.bbox[1]:.0f})")
                    logger.info(
                        f"帧{frame_count:4d} | {detect_mark} | "
                        f"总目标: {len(targets)} | "
                        f"A:{active_count} L:{lost_count} C:{cand_count}"
                    )
                    if targets and overlay_det.is_detect_frame:
                        logger.info(f"  -> {', '.join(target_info)}")

                # 提取需要绘框的目标（包括 candidate）
                draw_targets = [t for t in targets if t.state in ("active", "lost", "candidate")]

                # 绘制
                if draw_targets:
                    # 转换为 LayeredOverlay 需要的 DetectionResult 格式
                    from src.core.capabilities.detection import DetectionResult
                    det_results = []
                    for t in draw_targets:
                        x1, y1, x2, y2 = map(int, t.bbox)
                        det = DetectionResult(x1, y1, x2, y2, t.confidence, t.class_id)
                        det_results.append(det)
                    layered_overlay.draw(det_results)
                else:
                    # 无目标时传入空列表（自动清屏）
                    layered_overlay.draw([])

                elapsed = time.time() - loop_start
                if elapsed < capture_interval:
                    time.sleep(capture_interval - elapsed)

    except KeyboardInterrupt:
        logger.info("\n退出")
    finally:
        layered_overlay.destroy()
        detector.unload_model()


if __name__ == "__main__":
    main()