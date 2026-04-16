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
from typing import Optional, Tuple
from threading import Thread, Lock

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.core import (
    WindowManager,
    ScreenCapture,
    ObjectDetector,
    LayeredOverlay,
    CaptureModeDetector,
)
from src.core.capabilities.detection_overlay import DetectionOverlay
from src.core.capabilities.target_scoring import TargetScorer
from src.core.capabilities.interception_sim import (
    InterceptionSimulator,
    INTERCEPTION_AVAILABLE,
)
from src.actions.aim_and_throw import AimAndThrow
from src.logger import get_logger


def main():
    # 命令行参数解析
    parser = argparse.ArgumentParser(description="瞄准 + 投掷 实时测试")
    parser.add_argument("--model", help="YOLO模型路径（编辑配置时可选）")
    parser.add_argument("--process-name", default="NRC-Win64-Shipping.exe", help="游戏进程名")
    parser.add_argument("--resolution", default="auto", help="游戏分辨率 (默认auto自动检测)")
    parser.add_argument("--border-offset", type=int, default=0, help="边框裁剪偏移")
    parser.add_argument("--fps", type=int, default=30, help="屏幕捕获帧率")
    parser.add_argument("--device", default="cuda", help="推理设备")
    parser.add_argument("--target-class", type=int, default=0, help="目标类别")
    parser.add_argument("--confidence", type=float, default=0.5, help="置信度阈值")
    parser.add_argument("--nms-iou", type=float, default=0.7, help="NMS IoU 阈值（合并重叠框）")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--detection-interval", type=float, default=2.0, help="检测间隔(秒)")
    parser.add_argument("--max-distance", type=float, default=50.0, help="太远阈值")
    parser.add_argument("--near-threshold", type=float, default=100.0, help="靠近阈值")
    parser.add_argument("--capture-threshold", type=float, default=200.0, help="捕捉阈值")
    parser.add_argument("--center-offset-x", type=int, default=0, help="中心X偏移")
    parser.add_argument("--center-offset-y", type=int, default=0, help="中心Y偏移")
    parser.add_argument(
        "--auto-detect-mouse",
        dest="auto_detect_mouse",
        action="store_true",
        default=True,
        help="自动检测真实的物理鼠标设备号（默认开启）",
    )
    parser.add_argument(
        "--no-auto-detect-mouse",
        dest="auto_detect_mouse",
        action="store_false",
        help="禁用自动检测真实物理鼠标",
    )
    parser.add_argument(
        "--auto-detect-timeout",
        type=float,
        default=8.0,
        help="自动检测物理鼠标超时（秒）",
    )

    # 配置相关参数
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="指定配置文件路径",
    )
    parser.add_argument(
        "--edit-config",
        action="store_true",
        help="打开配置编辑器（无需其他参数）",
    )

    args = parser.parse_args()

    # 如果是编辑配置，则直接打开编辑器
    if args.edit_config:
        from src.tools.aim_config_editor import main as edit_main
        edit_main()
        sys.exit(0)

    # 检查必需的model参数
    if not args.model:
        parser.error("必须提供 --model 参数（除非使用 --edit-config）")

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
        iou_threshold=args.nms_iou,
        debug=args.debug,
    )
    if not detector.load_model():
        logger.error("模型加载失败")
        sys.exit(1)

    # 4. 捕捉模式检测器
    logger.info("[4/6] 初始化捕捉模式检测器...")
    # 使用绝对路径确保模板能正确加载
    template_path = str(Path(__file__).parent.parent / "config" / "templates" / "capture_mode.png")
    logger.info(f"  模板路径: {template_path}")
    try:
        capture_detector = CaptureModeDetector(
            template_path=template_path,
            frame_size=(width, height),
            debug=args.debug,
            match_threshold=0.70,  # 降低阈值避免波动导致捕捉状态不稳定
        )
        logger.success("捕捉模式检测器初始化成功")
    except Exception as e:
        logger.warning(f"捕捉模式检测器初始化失败: {e}，将跳过模式检测")
        capture_detector = None

    # 5. DetectionOverlay — 跳帧/跟踪/插值/绘框（复用模块）
    logger.info("[5/7] 初始化 DetectionOverlay...")
    overlay_det = DetectionOverlay(
        detector=detector,
        screen_width=width,
        screen_height=height,
        detect_interval=3,
        lerp_alpha=0.7,
        confirm_frames=3,
        lost_tolerance=5,
        iou_threshold=0.3,
        draw_boxes=True,
        min_confidence=args.confidence,
        debug=args.debug,
    )

    # 6. 目标评分器
    scorer = TargetScorer(
        screen_width=width,
        screen_height=height,
        center_offset_x=args.center_offset_x,
        center_offset_y=args.center_offset_y,
        far_threshold=args.max_distance,      # 使用 max-distance 作为远距离阈值
        near_threshold=args.near_threshold,   # 使用 near-threshold 作为近距离阈值
    )

    # 7. 加载瞄准配置
    logger.info("[6/7] 加载瞄准配置...")
    from src.config.aim_config import AimConfig

    # 加载配置文件，如果不存在则使用默认配置
    aim_config = AimConfig.from_file(args.config)

    # 命令行参数可以覆盖配置文件
    if args.debug:
        aim_config.debug = True

    logger.info("瞄准配置参数:")
    for key, value in aim_config.to_dict().items():
        logger.info(f"  {key}: {value}")

    # 8. 瞄准投掷器
    logger.info("[7/7] 初始化输入模拟（Interception 驱动）...")
    if not INTERCEPTION_AVAILABLE:
        logger.error("Interception 驱动不可用")
        logger.error("请运行: pip install interception")
        logger.error("并以管理员身份运行此脚本")
        sys.exit(1)

    send_input = InterceptionSimulator(window_mgr=window_mgr, debug=args.debug)

    # 可选：动态捕获真实物理鼠标设备号
    if args.auto_detect_mouse:
        try:
            detected = send_input.auto_detect_hardware_mouse(
                timeout_seconds=args.auto_detect_timeout
            )
            logger.success(f"已自动锁定真实物理鼠标设备号: {detected}")
        except Exception as e:
            logger.warning(f"自动检测物理鼠标失败，将沿用当前默认设备: {e}")

    aim_throw = AimAndThrow(send_input=send_input, config=aim_config)

    # 9. 分层覆盖窗口
    logger.info("[8/8] 创建分层覆盖窗口...")
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

    # 状态
    is_capture_mode = False      # 当前是否在捕捉模式
    has_target = False          # 当前是否有目标
    throw_executed_this_cycle = False  # 本次捕捉周期是否已执行投掷
    throw_thread: Optional[Thread] = None  # 瞄准投掷线程
    throw_result = None  # 投掷结果（在线程中设置）
    throw_lock = Lock()  # 保护线程共享变量的锁
    last_capture_state = False       # 上一次捕捉状态
    first_frame_logged = False        # 首帧是否已记录
    last_skip_warning_time = 0       # 上次警告时间（限制输出频率）

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
                capture_detected = False
                if capture_detector is not None:
                    capture_detected, confidence = capture_detector.is_capture_mode(frame)

                # 检测捕捉状态变化（上升沿）
                if capture_detected and not last_capture_state:
                    logger.info("【检测到捕捉状态切换】开始瞄准投掷...")
                    # 只在"真正开始新周期"时重置 — 即之前不在捕捉模式
                    # 避免捕捉状态抖动时反复触发 reset 把 candidate 清掉
                    if not is_capture_mode:
                        overlay_det.reset()  # 清空旧跟踪目标
                    is_capture_mode = True
                    throw_executed_this_cycle = False  # 重置投掷标志

                # 【新增】检测捕捉状态下降沿（用户离开捕捉界面）
                if not capture_detected and last_capture_state and is_capture_mode:
                    logger.info("【检测到捕捉状态结束】用户离开捕捉界面，重置状态...")
                    is_capture_mode = False
                    throw_executed_this_cycle = False  # 重置投掷标志
                    # 如果有线程在运行，不强制停止（让它自然完成）

                last_capture_state = capture_detected

                # ── DetectionOverlay 更新（跳帧/跟踪/插值） ──
                tracked = overlay_det.update(frame)

                # 提取需要绘框的目标（包括 candidate）
                draw_targets = [t for t in tracked if t.state in ("active", "lost", "candidate")]

                # 转换为 LayeredOverlay 需要的 DetectionResult 格式
                from src.core.capabilities.detection import DetectionResult
                det_results = []
                for t in draw_targets:
                    x1, y1, x2, y2 = map(int, t.bbox)
                    det = DetectionResult(x1, y1, x2, y2, t.confidence, t.class_id)
                    det_results.append(det)

                # 绘制到覆盖层
                overlay.draw(det_results if draw_targets else [])

                # ── 业务逻辑：从活跃目标中获取最佳目标 ──
                active = [t for t in tracked if t.state == "active"]
                has_target = len(active) > 0

                # ── 捕捉模式下的逻辑处理 ──
                if is_capture_mode and not throw_executed_this_cycle and throw_thread is None:
                    target = None  # 初始化 target 变量

                    if has_target:
                        logger.info(f"检测到 {len(active)} 个活跃目标")
                        # 对活跃目标进行评分排序
                        scored = scorer.score_detections([
                            DetectionResult(
                                *map(int, t.bbox),
                                t.confidence,
                                t.class_id,
                            )
                            for t in active
                        ])

                        # 确保有评分目标
                        if not scored:
                            logger.info("⚠️ 评分后无有效目标，跳过投掷")
                            continue

                        target = scored[0]

                        logger.info("=" * 50)
                        logger.info("【自动瞄准 + 投掷】")
                        logger.info(f"  目标中心: {target.detection.center}")
                        logger.info(f"  置信度: {target.detection.confidence:.3f}")
                        logger.info(f"  距离状态: {target.distance_state}")
                        logger.info("=" * 50)

                        # 将窗口放到前台
                        window_mgr.bring_to_foreground()
                        time.sleep(0.1)

                    # 定义实时目标获取函数（用于持续瞄准3秒期间）
                    def get_realtime_target() -> Optional[Tuple[int, int, float]]:
                        """从实时检测中获取当前活跃目标的中心位置及面积"""
                        current_frame = cap.capture()
                        if current_frame is None:
                            return None

                        # 直接进行 YOLO 检测，获取原始结果（不使用跟踪插值）
                        current_detections = detector.detect(current_frame, target_class=args.target_class)

                        if not current_detections:
                            return None

                        # 选择置信度最高的目标
                        current_target = max(current_detections, key=lambda d: d.confidence)

                        # 使用 DetectionResult.center 属性获取精确的中心点
                        cx, cy = current_target.center
                        bbox_area = float(current_target.area)

                        return cx, cy, bbox_area

                    # 定义线程执行的投掷函数
                    def execute_throw():
                        nonlocal throw_result, target
                        try:
                            success = aim_throw.aim_and_throw(
                                target=target,
                                screen_width=game_width,
                                screen_height=game_height,
                                fine_tune_ms=500,
                                get_target_func=get_realtime_target,
                            )
                            with throw_lock:
                                throw_result = success
                        except Exception as e:
                            logger.error(f"投掷线程异常: {e}")
                            with throw_lock:
                                throw_result = False

                    # 只有在有目标时才执行投掷
                    if target is not None:
                        # 启动独立线程执行瞄准投掷（不阻塞主循环）
                        throw_thread = Thread(target=execute_throw, daemon=True)
                        throw_thread.start()
                        logger.info("瞄准投掷线程已启动，主循环继续运行...")

                        # 标记本次周期已执行
                        throw_executed_this_cycle = True

                        # 重置捕捉模式（等待用户再次按 E）
                        is_capture_mode = False
                        logger.info("捕捉周期结束，等待再次进入捕捉模式...")

                # ── 检查线程是否完成 ──
                if throw_thread is not None and not throw_thread.is_alive():
                    with throw_lock:
                        result = throw_result
                        throw_result = None

                    if result is True:
                        logger.success("投掷线程执行成功")
                    elif result is False:
                        logger.error("投掷线程执行失败")
                    else:
                        logger.warning("投掷线程状态未知")
                    throw_thread = None

                # 打印检测信息（始终打印，方便调试）
                detect_mark = "YOLO" if overlay_det.is_detect_frame else "LERP"
                active_count = len([t for t in tracked if t.state == "active"])
                lost_count = len([t for t in tracked if t.state == "lost"])
                cand_count = len([t for t in tracked if t.state == "candidate"])
                capture_str = "【捕捉中】" if is_capture_mode else ""
                logger.debug_msg(
                    f"{capture_str} {detect_mark} | "
                    f"A:{active_count} L:{lost_count} C:{cand_count}"
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