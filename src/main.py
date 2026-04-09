#!/usr/bin/env python3
"""
主程序入口
洛克王国自动宠物捕捉脚本
"""

import argparse
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config import parse_args
from src.core import (
    WindowManager,
    ScreenCapture,
    ObjectDetector,
    InputSimulator,
    GameLogic,
    StateMachine,
)
from src.logger import get_logger


def main():
    args = parse_args()
    logger = get_logger(debug=args.debug)

    print("=" * 60)
    print("  洛克王国自动宠物捕捉脚本")
    print("=" * 60)
    print(f"  模型: {args.model_path}")
    print(f"  目标类别: {args.target_class}")
    print(f"  置信度阈值: {args.confidence_threshold}")
    print(f"  游戏进程: {args.process_name}")
    print(f"  帧率: {args.fps} FPS")
    print(f"  调试模式: {'是' if args.debug else '否'}")
    print(f"  试运行: {'是' if args.dry_run else '否'}")
    print("=" * 60)

    try:
        # 初始化模块
        logger.info("\n初始化模块...")

        # 1. 窗口管理
        logger.info("[1/5] 窗口管理...")
        window_mgr = WindowManager(process_name=args.process_name, debug=args.debug)
        if not window_mgr.find_window():
            logger.error("未找到游戏窗口，程序退出")
            sys.exit(1)

        # 2. 屏幕捕获
        logger.info("[2/5] 屏幕捕获...")
        region = window_mgr.get_screen_region()
        cap = ScreenCapture(region=region, fps=args.fps, debug=args.debug)

        # 3. 目标检测
        logger.info("[3/5] 目标检测...")
        detector = ObjectDetector(
            model_path=args.model_path,
            device=args.device,
            confidence_threshold=args.confidence_threshold,
            debug=args.debug,
        )
        detector.load_model()

        # 4. 游戏逻辑
        logger.info("[4/5] 游戏逻辑...")
        game_logic = GameLogic(
            frame_width=args.width,
            frame_height=args.height,
            debug=args.debug,
        )

        # 5. 状态机
        logger.info("[5/5] 状态机...")
        state_machine = StateMachine(debug=args.debug)

        logger.success("\n所有模块初始化完成！")
        logger.info("程序正在运行...")
        logger.info("按 Ctrl+C 退出")

        # 主循环（占位符 - 需要后续实现完整逻辑）
        with cap:
            while True:
                frame = cap.capture()
                if frame is None:
                    continue

                # 执行检测
                detections = detector.detect(frame, target_class=args.target_class)

                # 更新状态机
                new_state = state_machine.update(detections)

                if new_state.value != state_machine.current_state.value:
                    logger.info(f"当前状态: {new_state.value}")

                time.sleep(1.0 / args.fps)

    except KeyboardInterrupt:
        logger.info("\n\n✓ 用户中断，程序退出")
    except Exception as e:
        logger.error(f"\n✗ 错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
