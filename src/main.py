#!/usr/bin/env python3
"""
主程序入口
洛克王国自动宠物捕捉脚本 — 分层覆盖标注模式
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config import parse_args
from src.core import (
    WindowManager,
    ScreenCapture,
    ObjectDetector,
    LayeredOverlay,
    StateMachine,
)
from src.core.capabilities.target_scoring import TargetScorer
from src.core.capabilities.target_verifier import TargetVerifier
from src.detectors.config_loader import load_mask_regions, filter_masked_detections
from src.logger import get_logger


def run_live_detection(args):
    """实时检测标注主循环（DWM 分层覆盖窗口）"""
    logger = get_logger(debug=args.debug)

    # 1. 窗口管理
    logger.info("[1/4] 初始化窗口管理...")
    window_mgr = WindowManager(
        process_name=args.process_name,
        client_size=(args.width, args.height),
        border_offset=args.border_offset,
        debug=args.debug,
    )
    if not window_mgr.find_window():
        logger.error("未找到游戏窗口，程序退出")
        logger.info("请确保游戏已运行，进程名: NRC-Win64-Shipping.exe")
        sys.exit(1)

    region = window_mgr.get_screen_region()
    if region is None:
        logger.error("获取捕获区域失败")
        sys.exit(1)
    left, top, right, bottom = region
    logger.success(f"游戏客户区: ({left}, {top}, {right - left}x{bottom - top})")

    # 2. 屏幕捕获
    logger.info("[2/4] 初始化屏幕捕获...")
    cap = ScreenCapture(fps=args.fps, debug=args.debug)
    if not cap.start(region=region):
        logger.error("屏幕捕获启动失败")
        sys.exit(1)

    # 3. 目标检测
    logger.info("[3/4] 加载检测模型...")
    detector = ObjectDetector(
        model_path=args.model_path,
        device=args.device,
        confidence_threshold=args.confidence_threshold,
        iou_threshold=args.nms_iou_threshold,
        debug=args.debug,
    )
    if not detector.load_model():
        logger.error("模型加载失败")
        sys.exit(1)

    # 4. 分层覆盖窗口
    logger.info("[4/4] 创建分层覆盖窗口...")
    overlay = LayeredOverlay(
        x=left, y=top,
        width=args.width, height=args.height,
        debug=args.debug,
    )
    if not overlay.create_window():
        logger.error("分层窗口创建失败")
        sys.exit(1)

    logger.success("\n所有模块就绪！")
    logger.info("按 Ctrl+C 退出\n")

    # ── 主循环 ──
    capture_interval = 1.0 / args.fps

    # 目标评分器
    scorer = TargetScorer(
        screen_width=args.width,
        screen_height=args.height,
        max_distance_threshold=args.max_distance_threshold,
        near_threshold=args.near_threshold,
        capture_threshold=args.capture_threshold,
        center_offset_x=args.screen_center_offset_x,
        center_offset_y=args.screen_center_offset_y,
    )

    # 目标验证器
    verifier = TargetVerifier(
        required_cycles=args.verification_cycles,
        debug=args.debug,
    )

    # 遮蔽区域
    mask_regions = load_mask_regions()
    if mask_regions:
        logger.info(f"已加载 {len(mask_regions)} 个遮蔽区域")
    else:
        logger.info("未配置遮蔽区域")

    state_machine = StateMachine(
        verifier=verifier,
        debug=args.debug,
    )

    # 检测间隔（可配置）
    detect_interval = args.detection_interval
    last_detect_time = 0.0

    cached_scored: list = []
    last_log_time = time.time()
    frame_count = 0
    overlay_updates = 0
    first_frame_logged = False

    try:
        with cap:
            while True:
                loop_start = time.time()
                frame = cap.capture()
                if frame is None:
                    time.sleep(capture_interval * 0.1)
                    continue

                # 首帧打印
                if not first_frame_logged:
                    h, w = frame.shape[:2]
                    logger.info(f"首帧尺寸: {w}x{h} (期望 {args.width}x{args.height})")
                    if w != args.width or h != args.height:
                        logger.warning(f"尺寸不匹配！可能需要调整 --border-offset 参数")
                    first_frame_logged = True

                frame_count += 1

                # ── 检测（按可配置间隔，避免 GPU 过载） ──
                now = time.time()
                if (now - last_detect_time) >= detect_interval:
                    detections = detector.detect(frame, target_class=args.target_class)

                    # 过滤遮蔽区域内的检测结果
                    if mask_regions:
                        detections = filter_masked_detections(
                            detections, mask_regions, frame.shape[1], frame.shape[0]
                        )

                    last_detect_time = now

                    # ── 评分与排序 ──
                    scored = scorer.score_detections(detections)
                    cached_scored = scored

                    # ── 状态机驱动 ──
                    state_machine.update(scored)

                    # ── 更新覆盖层 ──
                    overlay.draw_scored(
                        scored,
                        verification_progress=state_machine._verifier.verification_progress,
                        verification_required=args.verification_cycles,
                        current_state=state_machine.current_state.value,
                    )
                    overlay_updates += 1

                # ── 每秒打印统计 ──
                if now - last_log_time >= 1.0:
                    state_info = state_machine.get_state_info()
                    logger.info(
                        f"状态: {state_info['current_state']} | "
                        f"捕获: {frame_count}/s | "
                        f"覆盖更新: {overlay_updates}/s | "
                        f"目标: {len(cached_scored)} | "
                        f"验证: {state_info.get('throw_count', 0)}"
                    )
                    frame_count = 0
                    overlay_updates = 0
                    last_log_time = now

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


def main():
    args = parse_args()
    logger = get_logger(debug=args.debug)

    print("=" * 60)
    print("  洛克王国自动宠物捕捉脚本 — 分层覆盖标注")
    print("=" * 60)
    print(f"  模型: {args.model_path}")
    print(f"  目标类别: {args.target_class}")
    print(f"  置信度阈值: {args.confidence_threshold}")
    print(f"  游戏进程: {args.process_name}")
    print(f"  捕获: {args.fps} FPS | 检测: 每 {args.detection_interval}s")
    print(f"  验证周期: {args.verification_cycles} 次")
    print(f"  距离阈值: FAR<{args.max_distance_threshold} | MEDIUM<{args.near_threshold} | CLOSE>={args.capture_threshold}")
    print(f"  调试模式: {'是' if args.debug else '否'}")
    print("=" * 60)

    run_live_detection(args)


if __name__ == "__main__":
    main()
