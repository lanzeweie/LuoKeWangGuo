#!/usr/bin/env python3
"""
在游戏窗口截图上标注 ROI 区域

用法：
    # 实时截图并标注所有 ROI
    uv run python -m src.tools.annotate_roi

    # 标注已有图片
    uv run python -m src.tools.annotate_roi --image path/to/image.png
"""

import argparse
import cv2
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.capabilities.window_mgr import WindowManager
from src.core.capabilities.screen_cap import ScreenCaptureWithRegion
from src.core.capabilities.capture_mode_detector import CaptureModeDetector
from src.core.capabilities.battle_mode_detector import BattleModeDetector

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def annotate_roi_on_image(image_path: str, output_path: str, frame_size: tuple = (1280, 720)) -> None:
    """在游戏窗口截图上标注所有 ROI 区域。"""
    img = cv2.imread(image_path)
    if img is None:
        print(f"ERROR: 无法读取图片: {image_path}")
        return

    h, w = img.shape[:2]
    print(f"图片尺寸: {w}x{h}")

    # 加载检测器获取 ROI
    capture_detector = CaptureModeDetector(
        template_path=str(PROJECT_ROOT / "data" / "templates" / "capture_mode.png"),
        frame_size=(w, h),
        debug=False,
    )
    battle_detector = BattleModeDetector(
        template_path=str(PROJECT_ROOT / "data" / "templates" / "battle_mode.png"),
        debug=False,
    )

    # 获取 ROI
    capture_roi = capture_detector._get_roi()

    # 战斗模式使用全局变量
    from src.core.capabilities.battle_mode_detector import ROI_X, ROI_Y, ROI_W, ROI_H
    battle_roi = (ROI_X, ROI_Y, ROI_W, ROI_H)

    # 标注捕捉模式 ROI（红色）
    x1, y1, roi_w, roi_h = capture_roi
    x2, y2 = x1 + roi_w, y1 + roi_h
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
    cv2.putText(img, f"Capture ROI: {roi_w}x{roi_h}", (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    print(f"捕捉模式 ROI: ({x1}, {y1}, {roi_w}, {roi_h})")

    # 标注战斗模式 ROI（绿色）
    x1, y1, roi_w, roi_h = battle_roi
    x2, y2 = x1 + roi_w, y1 + roi_h
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(img, f"Battle ROI: {roi_w}x{roi_h}", (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    print(f"战斗模式 ROI: ({x1}, {y1}, {roi_w}, {roi_h})")

    # 保存标注后的图片
    cv2.imwrite(output_path, img)
    print(f"\n标注后的图片已保存到: {output_path}")


def capture_and_annotate() -> None:
    """实时截图并标注 ROI"""
    print("正在截取游戏窗口...")

    # 初始化窗口管理
    window_mgr = WindowManager(process_name="NRC-Win64-Shipping.exe", client_size=(1280, 720), debug=False)
    if not window_mgr.find_window():
        print("ERROR: 未找到游戏窗口")
        sys.exit(1)

    # dxcam 初始化
    temp_region = window_mgr.get_screen_region()
    temp_cap = ScreenCaptureWithRegion(fps=5, debug=False, region=temp_region)
    with temp_cap:
        time.sleep(0.3)

    region = window_mgr.get_screen_region()
    left, top, right, bottom = region
    game_width = right - left
    game_height = bottom - top

    print(f"游戏窗口尺寸: {game_width}x{game_height}")

    # 截图
    cap = ScreenCaptureWithRegion(fps=5, debug=False, region=region)
    with cap:
        # 等待前几帧稳定
        frame = None
        for _ in range(10):
            frame = cap.capture()
            if frame is not None:
                break
            time.sleep(0.1)

    if frame is None:
        print("ERROR: 截图失败")
        sys.exit(1)

    # 保存截图
    output_dir = PROJECT_ROOT / "data" / "templates"
    output_dir.mkdir(parents=True, exist_ok=True)

    screenshot_path = output_dir / "screenshot.png"
    annotated_path = output_dir / "screenshot_annotated.png"

    cv2.imwrite(str(screenshot_path), frame)
    print(f"原始截图已保存: {screenshot_path}")

    # 标注 ROI
    annotate_roi_on_image(str(screenshot_path), str(annotated_path), frame_size=(game_width, game_height))


def main() -> None:
    parser = argparse.ArgumentParser(description="标注 ROI 区域")
    parser.add_argument("--image", help="要标注的图片路径（不指定则实时截图）")
    args = parser.parse_args()

    if args.image:
        output_path = str(Path(args.image).with_stem(Path(args.image).stem + "_annotated"))
        annotate_roi_on_image(args.image, output_path)
    else:
        capture_and_annotate()


if __name__ == "__main__":
    main()
