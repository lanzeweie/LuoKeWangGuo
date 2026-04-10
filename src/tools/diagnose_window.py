#!/usr/bin/env python3
"""
窗口 + 截图诊断工具

功能：
1. 获取 WindowManager 报告的窗口信息
2. 实际捕获一帧截图
3. 报告真实帧尺寸
4. 把截图保存到当前目录供检查

运行：
    uv run python -m src.tools.diagnose_window
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
from src.core.capabilities.window_mgr import WindowManager
from src.core.capabilities.screen_cap import ScreenCaptureWithRegion
from src.logger import get_logger


def main():
    parser = argparse.ArgumentParser(description="窗口 + 截图诊断工具")
    parser.add_argument("--process-name", default="NRC-Win64-Shipping.exe")
    parser.add_argument("--resolution", default="1280x720")
    parser.add_argument("--border-offset", type=int, default=0)
    parser.add_argument("--fps", type=int, default=5)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    width, height = map(int, args.resolution.split("x"))
    logger = get_logger(debug=args.debug)

    print("=" * 60)
    print("  窗口 + 截图诊断")
    print("=" * 60)

    # 1. WindowManager
    logger.info("[1] WindowManager")
    window_mgr = WindowManager(
        process_name=args.process_name,
        client_size=(width, height),
        border_offset=args.border_offset,
        debug=args.debug,
    )
    if not window_mgr.find_window():
        logger.error("未找到游戏窗口")
        sys.exit(1)

    region = window_mgr.get_screen_region()
    left, top, right, bottom = region
    wm_width = right - left
    wm_height = bottom - top

    print(f"  WindowManager 报告:")
    print(f"    客户区左上角: ({left}, {top})")
    print(f"    客户区宽高:   {wm_width} x {wm_height}")
    print(f"    期望尺寸:     {width} x {height}")
    print(f"    hwnd:         {window_mgr.hwnd}")
    print()

    # 2. 实际捕获一帧
    logger.info("[2] 实际截图")
    cap = ScreenCaptureWithRegion(fps=5, debug=True, region=region)

    with cap:
        if cap.camera is None:
            logger.error("相机未初始化")
            sys.exit(1)

        # 多取几帧，看尺寸是否稳定
        last_frame = None
        for i in range(5):
            frame = cap.capture()
            if frame is None:
                print(f"  帧 {i+1}: None")
                time.sleep(0.2)
                continue
            h, w = frame.shape[:2]
            print(f"  帧 {i+1}: {w} x {h} (shape={frame.shape})")
            last_frame = frame

            time.sleep(0.1)

        # 保存最后一帧
        if last_frame is not None:
            out_path = Path(__file__).parent.parent / "screenshot_debug.png"
            cv2.imwrite(str(out_path), last_frame)
            print(f"  -> 截图已保存到: {out_path}")
        else:
            print("  -> 警告: 未捕获到有效帧，无法保存截图")

    print()

    # 3. 对比
    print("=" * 60)
    print("  结论")
    print("=" * 60)

    if wm_width == width and wm_height == height:
        print("  窗口尺寸与期望值一致")
    else:
        print(f"  警告: WindowManager 报告的尺寸 ({wm_width}x{wm_height})")
        print(f"       与期望值 ({width}x{height}) 不一致")

    # 检查 dxcam region
    if hasattr(cap.camera, "region") and cap.camera.region is not None:
        dx_region = cap.camera.region
        print(f"  dxcam 实际 region: {dx_region}")
    else:
        print(f"  dxcam 无 region 信息")

    print()
    print("请把截图和上面的输出发给我，我来排查 ROI 问题。")


if __name__ == "__main__":
    main()
