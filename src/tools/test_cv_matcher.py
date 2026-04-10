#!/usr/bin/env python3
"""
CV 模式检测测试工具

测试战斗状态和精灵捕捉状态的模板匹配能力。

用法：
    # 自匹配测试（用模板本身验证）
    uv run python -m src.tools.test_cv_matcher self

    # 实时测试（从游戏窗口截图检测）
    uv run python -m src.tools.test_cv_matcher live
"""

import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.capture_mode_detector import CaptureModeDetector, ROI_X, ROI_Y, ROI_W, ROI_H, MATCH_THRESHOLD as CAPTURE_THRESHOLD
from src.core.battle_mode_detector import BattleModeDetector, ROI_X as BAT_ROI_X, ROI_Y as BAT_ROI_Y, ROI_W as BAT_ROI_W, ROI_H as BAT_ROI_H, MATCH_THRESHOLD as BATTLE_THRESHOLD
from src.core.screen_cap import ScreenCapture
from src.core.window_mgr import WindowManager
from src.logger import get_logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = PROJECT_ROOT / "data" / "templates"


def test_self_match() -> None:
    """自匹配测试：用模板本身作为输入，验证匹配置信度。"""
    print("=" * 60)
    print("CV 模式检测 - 自匹配测试")
    print("=" * 60)

    capture_template = TEMPLATES_DIR / "capture_mode.png"
    battle_template = TEMPLATES_DIR / "battle_mode.png"

    # ── 捕捉模式检测器测试 ──
    print(f"\n[1/2] 捕捉模式检测器")
    print(f"  模板: {capture_template}")
    if not capture_template.exists():
        print(f"  SKIP: 模板不存在")
    else:
        detector = CaptureModeDetector(str(capture_template), debug=True)
        raw = cv2.imread(str(capture_template))
        if raw is None:
            print("  FAIL: 无法读取模板")
        else:
            # 创建 1280x720 帧，把模板放到 ROI 区域内
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            th, tw = raw.shape[:2]
            frame[ROI_Y:ROI_Y + th, ROI_X:ROI_X + tw] = raw
            matched, conf = detector.is_capture_mode(frame)
            print(f"  置信度: {conf:.4f} (阈值 {CAPTURE_THRESHOLD})")
            print(f"  匹配: {matched}")
            print(f"  结果: {'PASS' if conf >= CAPTURE_THRESHOLD else 'FAIL'}")

    # ── 战斗模式检测器测试 ──
    print(f"\n[2/2] 战斗模式检测器")
    print(f"  模板: {battle_template}")
    if not battle_template.exists():
        print(f"  SKIP: 模板不存在")
    else:
        detector = BattleModeDetector(str(battle_template), debug=True)
        raw = cv2.imread(str(battle_template))
        if raw is None:
            print("  FAIL: 无法读取模板")
        else:
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            th, tw = raw.shape[:2]
            frame[BAT_ROI_Y:BAT_ROI_Y + th, BAT_ROI_X:BAT_ROI_X + tw] = raw
            matched, conf = detector.is_battle_mode(frame)
            print(f"  置信度: {conf:.4f} (阈值 {BATTLE_THRESHOLD})")
            print(f"  匹配: {matched}")
            print(f"  结果: {'PASS' if conf >= BATTLE_THRESHOLD else 'FAIL'}")

    # ── 交叉匹配测试（不应该匹配） ──
    print(f"\n[交叉测试] 交叉匹配验证")
    if capture_template.exists() and battle_template.exists():
        # 捕捉模板不应该匹配战斗检测器
        capture_raw = cv2.imread(str(capture_template))
        battle_raw = cv2.imread(str(battle_template))

        battle_detector = BattleModeDetector(str(battle_template), debug=False)
        capture_detector = CaptureModeDetector(str(capture_template), debug=False)

        # 捕捉模板 → 战斗检测器
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        ch, cw = capture_raw.shape[:2]
        frame[BAT_ROI_Y:BAT_ROI_Y + ch, BAT_ROI_X:BAT_ROI_X + cw] = capture_raw
        matched, conf = battle_detector.is_battle_mode(frame)
        print(f"  捕捉模板 → 战斗检测器: confidence={conf:.4f}, matched={matched}")
        cross_ok = not matched

        # 战斗模板 → 捕捉检测器
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        bh, bw = battle_raw.shape[:2]
        frame[ROI_Y:ROI_Y + bh, ROI_X:ROI_X + bw] = battle_raw
        matched, conf = capture_detector.is_capture_mode(frame)
        print(f"  战斗模板 → 捕捉检测器: confidence={conf:.4f}, matched={matched}")
        cross_ok = cross_ok and not matched

        print(f"  交叉匹配结果: {'PASS' if cross_ok else 'FAIL'}")

    print(f"\n{'=' * 60}")


def test_live() -> None:
    """实时测试：从游戏窗口截图，实时检测模式。"""
    print("=" * 60)
    print("CV 模式检测 - 实时测试")
    print("=" * 60)
    print("按 Ctrl+C 退出")
    print()

    capture_template = TEMPLATES_DIR / "capture_mode.png"
    battle_template = TEMPLATES_DIR / "battle_mode.png"

    if not capture_template.exists() or not battle_template.exists():
        print("ERROR: 模板文件不存在")
        return

    cap_detector = CaptureModeDetector(str(capture_template), debug=False)
    bat_detector = BattleModeDetector(str(battle_template), debug=False)

    # 初始化窗口管理器和屏幕捕获
    wm = WindowManager(debug=True)

    if not wm.find_window():
        print("ERROR: 未找到游戏窗口")
        return

    screen_region = wm.get_screen_region()
    if screen_region is None:
        print("ERROR: 无法获取屏幕区域")
        return

    sl, st, sr, sb = screen_region
    print(f"游戏窗口屏幕区域: ({sl}, {st}, {sr}, {sb})")

    sc = ScreenCapture(debug=True)
    sc.start(region=screen_region)
    time.sleep(1.0)

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            frame = sc.capture()
            if frame is None:
                continue

            # 模式检测
            cap_matched, cap_conf = cap_detector.is_capture_mode(frame)
            bat_matched, bat_conf = bat_detector.is_battle_mode(frame)

            frame_count += 1
            elapsed = time.time() - start_time

            # 每秒打印一次
            if frame_count % 30 == 0:
                fps = frame_count / elapsed
                print(
                    f"FPS={fps:.1f} | "
                    f"捕捉: {'是' if cap_matched else '否'} ({cap_conf:.4f}) | "
                    f"战斗: {'是' if bat_matched else '否'} ({bat_conf:.4f})"
                )

            time.sleep(1 / 30)

    except KeyboardInterrupt:
        print("\n退出实时测试")
    finally:
        sc.stop()


def test_full_window_debug() -> None:
    """完整窗口调试：截取整个游戏窗口并保存。"""
    print("=" * 60)
    print("CV 模式检测 - 完整窗口调试")
    print("=" * 60)

    wm = WindowManager(debug=True)

    if not wm.find_window():
        print("ERROR: 未找到游戏窗口")
        return

    screen_region = wm.get_screen_region()
    if screen_region is None:
        print("ERROR: 无法获取屏幕区域")
        return

    sl, st, sr, sb = screen_region
    sw, sh = sr - sl, sb - st
    print(f"\n游戏窗口屏幕区域: ({sl}, {st}, {sr}, {sb}) 尺寸: {sw}x{sh}")

    sc = ScreenCapture(debug=True)
    if not sc.start(region=screen_region):
        print("ERROR: 无法启动屏幕捕获")
        return

    time.sleep(1.0)
    frame = sc.capture()
    sc.stop()

    if frame is None:
        print("ERROR: 无法获取帧")
        return

    # 保存完整窗口截图
    output_path = PROJECT_ROOT / "data" / "templates" / "full_window.png"
    cv2.imwrite(str(output_path), frame)
    print(f"\n完整窗口已保存到: {output_path}")
    print(f"窗口大小: {sw}x{sh}")
    print(f"\nROI 区域标注: x={ROI_X}, y={ROI_Y}, w={ROI_W}, h={ROI_H}")
    print(f"（请在截图中检查 ROI 区域是否正确）")


def test_roi_debug() -> None:
    """ROI 调试：截取 ROI 区域并保存，用于验证 ROI 位置是否正确。"""
    print("=" * 60)
    print("CV 模式检测 - ROI 调试")
    print("=" * 60)

    wm = WindowManager(debug=True)

    if not wm.find_window():
        print("ERROR: 未找到游戏窗口")
        return

    # 获取屏幕区域（游戏窗口的屏幕绝对坐标）
    screen_region = wm.get_screen_region()
    if screen_region is None:
        print("ERROR: 无法获取屏幕区域")
        return

    sl, st, sr, sb = screen_region
    sw, sh = sr - sl, sb - st
    print(f"\n游戏窗口屏幕区域: ({sl}, {st}, {sr}, {sb}) 尺寸: {sw}x{sh}")

    # 初始化屏幕捕获，截取整个游戏窗口
    sc = ScreenCapture(debug=True)
    if not sc.start(region=screen_region):
        print("ERROR: 无法启动屏幕捕获")
        return

    time.sleep(1.0)
    frame = sc.capture()
    sc.stop()

    if frame is None:
        print("ERROR: 无法获取帧")
        return

    # 截取 ROI（相对于游戏窗口客户区）
    h, w = frame.shape[:2]
    x1 = max(0, ROI_X)
    y1 = max(0, ROI_Y)
    x2 = min(w, ROI_X + ROI_W)
    y2 = min(h, ROI_Y + ROI_H)

    roi = frame[y1:y2, x1:x2]

    # 保存 ROI 截图
    output_path = PROJECT_ROOT / "data" / "templates" / "roi_screenshot.png"
    cv2.imwrite(str(output_path), roi)
    print(f"\nROI 区域已保存到: {output_path}")
    print(f"ROI (客户区相对): x={x1}, y={y1}, w={x2-x1}, h={y2-y1}")
    print(f"ROI (屏幕绝对): x={sl+x1}, y={st+y1}")
    print(f"客户区大小: {w}x{h}")
    print(f"\n请检查保存的图片，确认 ROI 区域是否正确。")


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: uv run python -m src.tools.test_cv_matcher [self|live|roi|full]")
        print()
        print("  self - 自匹配测试（用模板本身验证）")
        print("  live - 实时测试（从游戏窗口截图检测）")
        print("  roi  - ROI 调试（截取 ROI 区域保存）")
        print("  full - 完整窗口调试（截取整个游戏窗口）")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "self":
        test_self_match()
    elif mode == "live":
        test_live()
    elif mode == "roi":
        test_roi_debug()
    elif mode == "full":
        test_full_window_debug()
    else:
        print(f"未知模式: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
