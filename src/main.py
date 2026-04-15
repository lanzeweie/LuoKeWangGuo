#!/usr/bin/env python3
"""
洛克王国半自动指定精灵捕捉工具 — 主入口

整合功能：
1. 搜索策略（鼠标平移 + 小范围走位）
2. 导航策略（WASD 靠近目标）
3. 瞄准投掷（Interception 驱动 + YOLO 实时检测）
4. 战斗退出（ESC + CV 确认框点击）

控制：
- 按 [ 键：开启/暂停捕捉流程
- 开启时覆盖层显示绿色边框，暂停时边框消失
- Ctrl+C：退出程序
"""

import argparse
import sys
import time
import threading
from pathlib import Path
from typing import Optional, Tuple

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

# ── 核心模块 ──
from src.core import (
    WindowManager,
    ObjectDetector,
    LayeredOverlay,
    InterceptionSimulator,
)
from src.core.capabilities.interception_sim import INTERCEPTION_AVAILABLE
from src.core.capabilities.screen_cap import ScreenCaptureWithRegion
from src.core.capabilities.detection_overlay import DetectionOverlay
from src.core.capabilities.detection import DetectionResult
from src.core.capabilities.target_scoring import TargetScorer

# ── CV 检测器 ──
from src.detectors import CaptureModeDetector, BattleModeDetector, BattleExitConfirmDetector

# ── 策略 ──
from src.strategies.base import Action
from src.strategies.search_strategy import SearchStrategy
from src.strategies.navigation_strategy import NavigationStrategy

# ── 动作 ──
from src.actions.aim_and_throw import AimAndThrow
from src.actions.battle_exit import BattleExit

# ── 工具 ──
from src.logger import get_logger

# ── Windows API（键盘监听） ──
import ctypes

# VK_KEY_CODE for '['
VK_BRACKET_OPEN = 0xDB

# ── 配置常量 ──
CAPTURE_INTERVAL = 1.0 / 30  # 30 FPS
FIRST_FRAME_RETRIES = 10     # 首帧等待最大重试次数


def _check_key_press(vk_code: int) -> bool:
    """检查指定虚拟键是否被按下（非阻塞）。"""
    return ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000 != 0


def _wait_for_key_press(vk_code: int, timeout: float = 0.3) -> bool:
    """等待按键事件（轮询，带超时）。"""
    start = time.time()
    while time.time() - start < timeout:
        if _check_key_press(vk_code):
            # 等待松开（防抖）
            time.sleep(0.1)
            return True
        time.sleep(0.02)
    return False


class KeyToggle:
    """简单的键盘开关：监听指定键，切换 on/off 状态。"""

    def __init__(self, vk_code: int):
        self._vk = vk_code
        self._on = False
        self._lock = threading.Lock()
        self._stop = False
        self._thread: Optional[threading.Thread] = None

    @property
    def is_on(self) -> bool:
        return self._on

    def start(self):
        """启动后台监听线程。"""
        self._stop = False
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self):
        """停止监听。"""
        self._stop = True

    def _listen(self):
        """后台轮询按键。"""
        last_pressed_time = 0.0
        debounce = 0.5  # 防抖间隔（秒）
        while not self._stop:
            now = time.time()
            if _check_key_press(self._vk) and (now - last_pressed_time) > debounce:
                last_pressed_time = now
                with self._lock:
                    self._on = not self._on
                time.sleep(0.2)  # 等松开
            time.sleep(0.05)


def main():
    # ── 命令行参数 ──
    parser = argparse.ArgumentParser(description="洛克王国半自动精灵捕捉工具")
    parser.add_argument("--model", required=True, help="YOLO 模型路径")
    parser.add_argument("--process-name", default="NRC-Win64-Shipping.exe", help="游戏进程名")
    parser.add_argument("--fps", type=int, default=30, help="屏幕捕获帧率")
    parser.add_argument("--device", default="cuda", help="推理设备")
    parser.add_argument("--target-class", type=int, default=0, help="目标类别")
    parser.add_argument("--confidence", type=float, default=0.5, help="置信度阈值")
    parser.add_argument("--nms-iou", type=float, default=0.7, help="NMS IoU 阈值")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--auto-detect-mouse", dest="auto_detect_mouse", action="store_true", default=True)
    parser.add_argument("--no-auto-detect-mouse", dest="auto_detect_mouse", action="store_false")
    parser.add_argument("--auto-detect-timeout", type=float, default=8.0)
    parser.add_argument("--search-step-px", type=int, default=40, help="搜索时每次鼠标平移像素")
    parser.add_argument("--max-distance", type=float, default=50.0)
    parser.add_argument("--near-threshold", type=float, default=100.0)
    parser.add_argument("--capture-threshold", type=float, default=200.0)
    parser.add_argument("--center-offset-x", type=int, default=0)
    parser.add_argument("--center-offset-y", type=int, default=0)
    parser.add_argument("--aim-config", type=str, default=None, help="瞄准配置文件路径")

    args = parser.parse_args()

    logger = get_logger(debug=args.debug)

    print("=" * 60)
    print("  洛克王国半自动指定精灵捕捉工具")
    print("=" * 60)
    print("  控制：")
    print("  - 按 [ 键：开启/暂停捕捉流程")
    print("  - 开启时覆盖层显示绿色边框，暂停时边框消失")
    print("  - Ctrl+C：退出程序")
    print()
    print("  功能：")
    print("  1. 搜索策略（鼠标平移 + 小范围走位）")
    print("  2. 导航策略（WASD 靠近目标）")
    print("  3. 瞄准投掷（Interception 驱动 + YOLO 实时检测）")
    print("  4. 战斗退出（ESC + CV 确认框点击）")
    print("=" * 60)

    # ── 检查 Interception ──
    if not INTERCEPTION_AVAILABLE:
        logger.error("Interception 驱动不可用")
        logger.error("请运行: pip install interception")
        logger.error("并以管理员身份运行此脚本")
        sys.exit(1)

    # ── 1. 窗口管理 ──
    logger.info("[1/8] 初始化窗口管理...")
    window_mgr = WindowManager(
        process_name=args.process_name,
        client_size=(1280, 720),
        border_offset=0,
        debug=args.debug,
    )
    if not window_mgr.find_window():
        logger.error("未找到游戏窗口，请确保游戏已运行")
        sys.exit(1)

    # ── 2. ScreenCapture 初始化（触发 dxcam 改变窗口尺寸） ──
    logger.info("[2/8] 初始化屏幕捕获...")
    temp_region = window_mgr.get_screen_region()
    if temp_region is None:
        logger.error("获取捕获区域失败")
        sys.exit(1)

    temp_cap = ScreenCaptureWithRegion(fps=5, debug=False, region=temp_region)
    with temp_cap:
        time.sleep(0.3)

    region = window_mgr.get_screen_region()
    if region is None:
        logger.error("重新获取捕获区域失败")
        sys.exit(1)

    left, top, right, bottom = region
    game_width = right - left
    game_height = bottom - top

    logger.success(f"游戏客户区: ({left}, {top}, {game_width}x{game_height})")

    cap = ScreenCaptureWithRegion(fps=args.fps, debug=args.debug, region=region)

    # ── 3. 目标检测 ──
    logger.info("[3/8] 加载检测模型...")
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

    # ── 4. CV 模式检测器 ──
    logger.info("[4/8] 初始化 CV 模式检测器...")
    template_root = Path(__file__).parent.parent / "config" / "templates"

    capture_detector = None
    try:
        capture_detector = CaptureModeDetector(
            template_path=str(template_root / "capture_mode.png"),
            frame_size=(game_width, game_height),
            debug=args.debug,
            match_threshold=0.70,
        )
        logger.success("捕捉模式检测器初始化成功")
    except Exception as e:
        logger.warning(f"捕捉模式检测器初始化失败: {e}")

    battle_detector = None
    try:
        battle_detector = BattleModeDetector(
            template_path=str(template_root / "battle_mode.png"),
            debug=args.debug,
        )
        logger.success("战斗模式检测器初始化成功")
    except Exception as e:
        logger.warning(f"战斗模式检测器初始化失败: {e}")

    battle_exit_confirm_detector = None
    try:
        battle_exit_confirm_detector = BattleExitConfirmDetector(
            template_path=str(template_root / "battle_exit_confirm.png"),
            debug=args.debug,
        )
        logger.success("战斗退出确认框检测器初始化成功")
    except Exception as e:
        logger.warning(f"战斗退出确认框检测器初始化失败: {e}")

    # ── 5. DetectionOverlay ──
    logger.info("[5/8] 初始化 DetectionOverlay...")
    overlay_det = DetectionOverlay(
        detector=detector,
        screen_width=game_width,
        screen_height=game_height,
        detect_interval=3,
        lerp_alpha=0.7,
        confirm_frames=1,
        lost_tolerance=5,
        iou_threshold=0.3,
        draw_boxes=False,  # 由 LayeredOverlay 负责绘框
        min_confidence=args.confidence,
        debug=args.debug,
    )

    # ── 6. 目标评分器 ──
    scorer = TargetScorer(
        screen_width=game_width,
        screen_height=game_height,
        max_distance_threshold=args.max_distance,
        near_threshold=args.near_threshold,
        capture_threshold=args.capture_threshold,
        center_offset_x=args.center_offset_x,
        center_offset_y=args.center_offset_y,
    )

    # ── 7. 输入模拟 ──
    logger.info("[6/8] 初始化输入模拟（Interception 驱动）...")
    send_input = InterceptionSimulator(window_mgr=window_mgr, debug=args.debug)

    if args.auto_detect_mouse:
        try:
            detected = send_input.auto_detect_hardware_mouse(
                timeout_seconds=args.auto_detect_timeout
            )
            logger.success(f"已自动锁定真实物理鼠标设备号: {detected}")
        except Exception as e:
            logger.warning(f"自动检测物理鼠标失败，将沿用当前默认设备: {e}")

    # ── 8. 策略 ──
    search_strategy = SearchStrategy(legacy_mouse_action=False)
    navigation_strategy = NavigationStrategy(center_tolerance=150, far_threshold=300, timeout_seconds=15.0)

    # ── 9. 瞄准投掷 ──
    from src.config.aim_config import AimConfig
    aim_config = AimConfig.from_file(args.aim_config)
    if args.debug:
        aim_config.debug = True

    aim_throw = AimAndThrow(send_input=send_input, config=aim_config)

    # ── 10. 战斗退出 ──
    battle_exit = None
    if battle_detector is not None:
        battle_exit = BattleExit(
            send_input=send_input,
            battle_detector=battle_detector,
            exit_confirm_detector=battle_exit_confirm_detector,
            debug=args.debug,
        )

    # ── 11. 分层覆盖窗口 ──
    logger.info("[7/8] 创建分层覆盖窗口...")
    overlay = LayeredOverlay(
        x=left, y=top,
        width=game_width, height=game_height,
        debug=args.debug,
        class_names=["奇丽草群组"],
    )
    if not overlay.create_window():
        logger.error("分层窗口创建失败")
        sys.exit(1)

    # ── 12. 键盘开关 ──
    logger.info("[8/8] 初始化键盘控制...")
    key_toggle = KeyToggle(VK_BRACKET_OPEN)
    key_toggle.start()

    logger.success("\n" + "=" * 60)
    logger.success("所有模块就绪！")
    logger.success("=" * 60)
    logger.info("按 [ 键开始捕捉流程，再次按 [ 暂停")
    logger.info("按 Ctrl+C 退出\n")

    # ── 主循环 ──
    capture_interval = 1.0 / args.fps
    first_frame_logged = False

    # 状态变量
    is_capture_mode = False          # 当前是否在捕捉模式（精灵球界面）
    is_battle_mode = False           # 当前是否在战斗模式
    throw_triggered = False  # 本次捕捉周期是否已执行投掷
    throw_thread: Optional[threading.Thread] = None
    throw_result = None
    throw_lock = threading.Lock()

    # 搜索状态
    search_cooldown_until = 0.0

    # 自动进入捕捉状态
    auto_e_pressed = False           # 是否已按 E 等待捕捉界面
    auto_e_cooldown = 0.0            # 按 E 冷却时间（防止重复按）

    # 捕捉模式超时（无目标时自动退出）
    capture_mode_timeout = 10.0      # 捕捉模式无目标超时时间（秒）
    capture_mode_timeout_until = 0.0 # 超时截止时间（0 表示未设置）

    # ── 检测线程共享状态 ──
    detect_lock = threading.Lock()
    latest_frame = None           # 最新帧（用于主线程的 CV 检测）
    latest_tracked: list = []     # 通过锁保护的最新跟踪结果
    latest_det_results: list = []
    latest_capture_detected = False   # 捕捉模式检测结果
    latest_conf_cap = 0.0             # 捕捉模式匹配度
    latest_battle_detected = False    # 战斗模式检测结果
    detect_seq = 0                    # 检测序列号，主循环用它来确认已读到最新结果
    detect_thread_stop = False

    # 捕捉模式滞回：防止单帧漏检导致状态闪烁
    capture_mode_streak = 0           # 连续匹配计数（正=检测中，负=未检测）
    CAPTURE_STREAK_HYSTERESIS = 3     # 连续 N 帧确认

    def detection_worker():
        """后台检测线程：截图 + YOLO 检测 + CV 模式检测，不阻塞主循环"""
        nonlocal latest_tracked, latest_det_results, latest_frame
        nonlocal latest_capture_detected, latest_conf_cap, latest_battle_detected
        nonlocal detect_seq
        while not detect_thread_stop:
            frame = cap.capture()
            if frame is None:
                time.sleep(capture_interval * 0.1)
                continue

            # ── YOLO 检测 ──
            tracked = overlay_det.update(frame)

            # 提取需要绘框的目标
            draw_targets = [t for t in tracked if t.state in ("active", "lost", "candidate")]
            det_results = []
            for t in draw_targets:
                x1, y1, x2, y2 = map(int, t.bbox)
                det = DetectionResult(x1, y1, x2, y2, t.confidence, t.class_id)
                det_results.append(det)

            # ── CV 模式检测（同一线程，避免 dxcam 并发冲突） ──
            cap_detected = False
            conf_val = 0.0
            if capture_detector is not None:
                cap_detected, conf_val = capture_detector.is_capture_mode(frame)

            batt_detected = False
            if battle_detector is not None:
                batt_detected, _ = battle_detector.is_battle_mode(frame)

            with detect_lock:
                latest_frame = frame
                latest_tracked = tracked
                latest_det_results = det_results
                latest_capture_detected = cap_detected
                latest_conf_cap = conf_val
                latest_battle_detected = batt_detected
                detect_seq += 1

            time.sleep(capture_interval * 0.1)

    detect_thread = threading.Thread(target=detection_worker, daemon=True)
    detect_thread.start()

    try:
        with cap:
            # 等待有效首帧
            for _ in range(FIRST_FRAME_RETRIES):
                frame = cap.capture()
                if frame is not None:
                    break
                time.sleep(0.1)
            else:
                logger.error("截图失败：等待首帧超时")
                sys.exit(1)

            if not first_frame_logged:
                h, w = frame.shape[:2]
                logger.info(f"首帧尺寸: {w}x{h}")
                first_frame_logged = True

            while True:
                loop_start = time.time()

                enabled = key_toggle.is_on

                # ── 暂停：不做检测、不打框 ──
                if not enabled:
                    overlay.draw_scored(
                        scored_detections=[],
                        current_state="已暂停",
                        border_color=None,
                    )
                    # 重置自动进入捕捉的状态
                    auto_e_pressed = False
                    auto_e_cooldown = 0.0
                    time.sleep(capture_interval * 2)  # 暂停时降低帧率
                    continue

                # ── 开启：执行全部流程 ──
                # 从检测线程获取最新结果（所有检测在同一线程，避免 dxcam 并发冲突）
                with detect_lock:
                    tracked = list(latest_tracked)
                    det_results = latest_det_results
                    capture_detected = latest_capture_detected
                    conf_cap = latest_conf_cap
                    battle_detected = latest_battle_detected

                now = time.time()

                # ── 搜索 / 导航 ──
                # 使用 active + candidate 作为有效目标
                valid_targets = [t for t in tracked if t.state in ("active", "candidate")]
                if not is_capture_mode and not is_battle_mode and not throw_thread:
                    if valid_targets:
                        # 有目标 → 评分 + 导航/靠近决策
                        scored = scorer.score_detections([
                            DetectionResult(*map(int, t.bbox), t.confidence, t.class_id)
                            for t in valid_targets
                        ])
                        if scored:
                            best = scored[0]
                            from src.core.context import AppContext
                            ctx = AppContext(
                                config={},
                                logger=logger,
                                window_region=(0, 0, game_width, game_height),
                                detections=[best.detection],
                                verified_target=best.detection,
                            )

                            # 根据 TargetScorer 的距离状态决定行为
                            if best.distance_state == "CLOSE":
                                # 足够近 → 自动按 E 进入捕捉
                                if not auto_e_pressed and now > auto_e_cooldown:
                                    logger.info(f"【自动进入捕捉】目标 CLOSE(bbox_area={best.bbox_area:.0f})，按 E 键...")
                                    window_mgr.bring_to_foreground()
                                    time.sleep(0.2)
                                    send_input.press_key("e", duration=0.3)
                                    auto_e_pressed = True
                                    auto_e_cooldown = now + 3.0  # 3秒冷却
                            elif best.distance_state == "MEDIUM":
                                # 中等距离 → WASD 精细靠近
                                nav_action = navigation_strategy.execute(ctx)
                                move_params = navigation_strategy.get_movement_parameters(ctx)
                                if nav_action == Action.MOVE_WASD and move_params is not None:
                                    direction, duration = move_params
                                    # 中距离缩短移动时长
                                    duration = min(duration, 0.2)
                                    logger.info(f"[导航-中距] 方向={direction} 时长={duration:.2f}s area={best.bbox_area:.0f}")
                                    send_input.press_key(direction, duration=duration)
                                    auto_e_pressed = False
                            else:
                                # FAR → WASD 快速靠近
                                nav_action = navigation_strategy.execute(ctx)
                                move_params = navigation_strategy.get_movement_parameters(ctx)
                                if nav_action == Action.MOVE_WASD and move_params is not None:
                                    direction, duration = move_params
                                    logger.info(f"[导航-远距] 方向={direction} 时长={duration:.2f}s area={best.bbox_area:.0f}")
                                    send_input.press_key(direction, duration=duration)
                                    auto_e_pressed = False
                    else:
                        # 无目标 → 搜索
                        from src.core.context import AppContext
                        ctx = AppContext(
                            config={},
                            logger=logger,
                            window_region=(0, 0, game_width, game_height),
                            detections=[],
                        )
                        auto_e_pressed = False
                        search_action = search_strategy.execute(ctx)
                        search_cmd = search_strategy.get_search_command()

                        if search_action in (Action.SEARCH_MOUSE, Action.SEARCH_PAN):
                            dx = int(search_cmd.params.get("dx", args.search_step_px))
                            dy = int(search_cmd.params.get("dy", 0))
                            pause_s = float(search_cmd.params.get("pause_s", capture_interval))
                            logger.debug_msg(f"[搜索-视角] dx={dx:+d}, dy={dy:+d}")
                            send_input.mouse_move(dx, dy)
                            time.sleep(min(1.5, max(0.02, pause_s)))
                        elif search_action == Action.SEARCH_MOVE:
                            direction = str(search_cmd.params.get("direction", "w"))
                            duration = float(search_cmd.params.get("duration", 0.3))
                            look_dx = int(search_cmd.params.get("look_dx", 0))
                            look_dy = int(search_cmd.params.get("look_dy", 0))
                            pause_s = float(search_cmd.params.get("pause_s", capture_interval))
                            logger.debug_msg(f"[搜索-走位] key={direction}")
                            if look_dx != 0 or look_dy != 0:
                                send_input.mouse_move(look_dx, look_dy)
                            send_input.press_key(direction, duration=duration)
                            time.sleep(min(1.5, max(0.02, pause_s)))

                # ── 捕捉模式 → 瞄准投掷（带滞回，防止单帧漏检导致状态闪烁） ──
                if capture_detected:
                    capture_mode_streak = max(capture_mode_streak + 1, 1)
                else:
                    capture_mode_streak = min(capture_mode_streak - 1, -1)

                # 连续 N 帧检测到 且 有有效目标 → 进入捕捉模式
                if capture_mode_streak >= CAPTURE_STREAK_HYSTERESIS and not is_capture_mode and valid_targets:
                    logger.info(f"【检测到捕捉状态】匹配度={conf_cap:.3f}，连续{CAPTURE_STREAK_HYSTERESIS}帧确认，目标数={len(valid_targets)}，开始瞄准投掷...")
                    overlay_det.reset()
                    is_capture_mode = True
                    throw_triggered = False
                elif capture_mode_streak >= CAPTURE_STREAK_HYSTERESIS and not is_capture_mode and not valid_targets:
                    # 检测到捕捉界面但无目标，保持搜索模式继续寻找
                    logger.debug_msg(f"[捕捉界面] 检测到界面但无目标，继续搜索...")

                # 连续 N 帧未检测到 → 退出捕捉模式
                if capture_mode_streak <= -CAPTURE_STREAK_HYSTERESIS and is_capture_mode:
                    logger.info("【捕捉状态结束】用户离开捕捉界面")
                    is_capture_mode = False
                    throw_triggered = False
                    auto_e_pressed = False  # 重置 E 标志
                    capture_mode_timeout_until = 0.0

                # 打印捕捉模式匹配度（调试用）
                if conf_cap > 0.1:
                    logger.debug_msg(f"[捕捉模式] 匹配度={conf_cap:.4f}, 滞回={capture_mode_streak:+d}")

                # ── 捕捉模式无目标超时：自动退出到搜索模式 ──
                # 注意：auto_e_pressed 时不超时（等待用户进入捕捉界面）
                if is_capture_mode and not valid_targets and not throw_thread and not throw_triggered and not auto_e_pressed:
                    if capture_mode_timeout_until == 0.0:
                        capture_mode_timeout_until = now + capture_mode_timeout
                        logger.info(f"【捕捉模式】无目标，{capture_mode_timeout:.0f}s 后自动退出...")
                    elif now >= capture_mode_timeout_until:
                        logger.warning("【捕捉模式超时】自动退出到搜索模式")
                        is_capture_mode = False
                        throw_triggered = False
                        auto_e_pressed = False
                        capture_mode_timeout_until = 0.0
                        capture_mode_streak = 0  # 重置滞回计数器
                        overlay_det.reset()
                else:
                    # 有目标或投掷已执行，重置超时
                    capture_mode_timeout_until = 0.0

                if is_capture_mode and not throw_triggered and valid_targets and throw_thread is None:
                    scored = scorer.score_detections([
                        DetectionResult(*map(int, t.bbox), t.confidence, t.class_id)
                        for t in valid_targets
                    ])
                    if scored:
                        target = scored[0]
                        logger.info(f"【瞄准投掷】目标中心={target.detection.center}, 置信度={target.detection.confidence:.3f}")

                        window_mgr.bring_to_foreground()
                        time.sleep(0.1)

                        def get_realtime_target() -> Optional[Tuple[int, int, float]]:
                            current_frame = cap.capture()
                            if current_frame is None:
                                return None
                            current_tracked = overlay_det.update(current_frame)
                            current_valid = [t for t in current_tracked if t.state in ("active", "candidate")]
                            if not current_valid:
                                return None
                            ct = current_valid[0]
                            x1, y1, x2, y2 = ct.bbox
                            return int((x1 + x2) / 2), int((y1 + y2) / 2), float((x2 - x1) * (y2 - y1))

                        def execute_throw():
                            nonlocal throw_result
                            try:
                                success = aim_throw.aim_and_throw(
                                    target=target,
                                    screen_width=game_width,
                                    screen_height=game_height,
                                    get_target_func=get_realtime_target,
                                )
                                with throw_lock:
                                    throw_result = success
                            except Exception as e:
                                logger.error(f"投掷线程异常: {e}")
                                with throw_lock:
                                    throw_result = False

                        throw_thread = threading.Thread(target=execute_throw, daemon=True)
                        throw_thread.start()
                        throw_triggered = True
                        is_capture_mode = False

                # ── 战斗模式 → 退出 ──
                if battle_detected and not is_battle_mode:
                    logger.info("【检测到战斗模式】执行退出流程...")
                    is_battle_mode = True

                if not battle_detected and is_battle_mode:
                    logger.info("【战斗模式结束】")
                    is_battle_mode = False
                    auto_e_pressed = False

                if is_battle_mode and battle_exit is not None:
                    def frame_provider():
                        return cap.capture()

                    exit_success = battle_exit.exit_battle(
                        frame_provider=frame_provider,
                        max_retries=3,
                        wait_after_esc=1.0,
                    )
                    if exit_success:
                        is_battle_mode = False
                        overlay_det.reset()
                        auto_e_pressed = False
                    else:
                        logger.warning("战斗退出失败，稍后重试")
                        time.sleep(2.0)

                # ── 检查投掷线程 ──
                if throw_thread is not None and not throw_thread.is_alive():
                    with throw_lock:
                        result = throw_result
                        throw_result = None
                    if result is True:
                        logger.success("投掷成功")
                    elif result is False:
                        logger.error("投掷失败")
                    throw_thread = None

                # ── 构建状态行（最多3条） ──
                status_lines = []

                # 第1行：当前主状态
                if is_capture_mode:
                    status_lines.append("状态: 瞄准投掷")
                elif throw_thread:
                    status_lines.append("状态: 投掷执行中")
                elif auto_e_pressed:
                    status_lines.append("状态: 等待捕捉界面")
                elif is_battle_mode:
                    status_lines.append("状态: 战斗退出")
                elif valid_targets:
                    status_lines.append("状态: 导航靠近")
                else:
                    status_lines.append("状态: 搜索中")

                # 第2行：目标信息
                if valid_targets:
                    t = valid_targets[0]
                    x1, y1, x2, y2 = map(int, t.bbox)
                    cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                    area = (x2 - x1) * (y2 - y1)
                    status_lines.append(f"目标: 中心({cx},{cy}) 面积{area:.0f}")
                else:
                    status_lines.append("目标: 无")

                # 第3行：当前帧检测源
                detect_mark = "YOLO(线程)" if overlay_det.is_detect_frame else "插值"
                status_lines.append(f"帧源: {detect_mark}")

                # ── 覆盖层绘制（绿框 + 状态行） ──
                overlay.draw_scored(
                    scored_detections=[],
                    current_state="运行中",
                    border_color=(0, 255, 0, 255),
                    status_lines=status_lines,
                )

                # ── 终端打印当前任务（最多3行，每帧更新） ──
                capture_str = "捕捉" if is_capture_mode else ("战斗" if is_battle_mode else "")
                active_count = len([t for t in tracked if t.state == "active"])
                cand_count = len([t for t in tracked if t.state == "candidate"])
                valid_count = len(valid_targets)
                print(f"\r[运行中] {capture_str} 目标:{valid_count}(A:{active_count} C:{cand_count})  |  {status_lines[0]}  |  {status_lines[1]}  |  {status_lines[2]}   ", end="", flush=True)

                # ── 帧率限制 ──
                elapsed = time.time() - loop_start
                if elapsed < capture_interval:
                    time.sleep(capture_interval - elapsed)

    except KeyboardInterrupt:
        logger.info("\n用户中断，退出")
    finally:
            detect_thread_stop = True
            key_toggle.stop()
            overlay.destroy()
            detector.unload_model()
            logger.info("已清理资源")


if __name__ == "__main__":
    main()
