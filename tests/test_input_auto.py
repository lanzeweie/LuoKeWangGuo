#!/usr/bin/env python3
"""
一键式输入测试工具

自动测试 Interception 驱动的键盘和鼠标功能：
1. 启动后等待 3 秒让用户切换到游戏窗口
2. 自动测试鼠标移动（视角移动，幅度大）
3. 自动测试 WASD 键盘移动

使用方法：
    uv run python -m src.tools.test_input_auto

测试流程：
    1. 等待 3 秒 → 切换到游戏窗口
    2. 鼠标移动测试（上下左右大幅度移动视角）
    3. WASD 键盘测试（前后左右移动）
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.capabilities.window_mgr import WindowManager
from src.core.capabilities.interception_sim import (
    InterceptionSimulator,
    INTERCEPTION_AVAILABLE,
)
from src.logger import get_logger


class AutoInputTester:
    """一键式自动输入测试器。"""

    def __init__(self, debug: bool = True):
        self.debug = debug
        self.logger = get_logger(debug=debug)

        # 检查 Interception 可用性
        if not INTERCEPTION_AVAILABLE:
            self.logger.error("Interception 驱动未安装！")
            self.logger.info("请运行: pip install interception")
            sys.exit(1)

        # 初始化窗口管理
        self.logger.info("初始化窗口管理...")
        self.window_mgr = WindowManager(
            process_name="NRC-Win64-Shipping.exe",
            client_size=(1280, 720),
            debug=debug,
        )

        if not self.window_mgr.find_window():
            self.logger.error("未找到游戏窗口！")
            self.logger.info("请确保游戏已运行（进程名: NRC-Win64-Shipping.exe）")
            sys.exit(1)

        region = self.window_mgr.get_region()
        if region is None:
            self.logger.error("无法获取窗口客户区")
            sys.exit(1)

        self.left, self.top, self.width, self.height = region
        self.logger.success(
            f"游戏窗口: ({self.left}, {self.top}), 尺寸: {self.width}x{self.height}"
        )

        # 初始化 Interception 模拟器
        self.logger.info("初始化 Interception 模拟器...")
        try:
            self.simulator = InterceptionSimulator(self.window_mgr, debug=debug)
            self.logger.success("Interception 模拟器初始化成功")
        except Exception as e:
            self.logger.error(f"Interception 初始化失败: {e}")
            self.logger.info("请确认：")
            self.logger.info("1. 已安装 Interception 驱动")
            self.logger.info("2. 以管理员身份运行")
            self.logger.info("3. 驱动服务已启动")
            sys.exit(1)

    def test_mouse_movement(self):
        """测试鼠标移动（视角移动，使用相对移动）。"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("  [1/2] 鼠标移动测试（视角移动 - 相对移动）")
        self.logger.info("=" * 60)
        self.logger.info("\n注意：游戏内视角控制使用鼠标相对移动（delta），不是绝对位置")

        # 大幅度相对移动测试（使用 mouse_move 相对移动）
        movements = [
            ("向右", 400, 0),
            ("向下", 0, 300),
            ("向左", -400, 0),
            ("向上", 0, -300),
            ("右下对角", 300, 200),
            ("左上对角", -300, -200),
            ("顺时针圆形", 200, 0),
            ("继续", 0, 200),
            ("继续", -200, 0),
            ("继续", 0, -200),
        ]

        for i, (direction, dx, dy) in enumerate(movements, 1):
            self.logger.info(f"\n[{i}/{len(movements)}] 测试 {direction} 移动 ({dx:+d}, {dy:+d})")
            self.simulator.mouse_move(dx, dy)
            self.logger.success(f"✓ {direction} 移动完成")
            time.sleep(0.4)  # 每次移动间隔

        self.logger.success("\n鼠标移动测试完成！")

    def test_keyboard_movement(self):
        """测试 WASD 键盘移动。"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("  [2/2] WASD 键盘测试")
        self.logger.info("=" * 60)

        keys = [
            ("W", "w", "向前"),
            ("A", "a", "向左"),
            ("S", "s", "向后"),
            ("D", "d", "向右"),
        ]

        for i, (key_name, key_code, description) in enumerate(keys, 1):
            self.logger.info(f"\n[{i}/{len(keys)}] 测试 {key_name} 键 ({description})")
            self.simulator.press_key(key_code, duration=0.3)
            self.logger.success(f"✓ {key_name} 键测试完成")
            time.sleep(0.5)  # 每次按键间隔

        self.logger.success("\nWASD 键盘测试完成！")

    def run(self):
        """运行自动测试。"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("  一键式输入测试工具")
        self.logger.info("=" * 60)
        self.logger.info("\n测试流程：")
        self.logger.info("  1. 等待 3 秒 → 请切换到游戏窗口")
        self.logger.info("  2. 鼠标移动测试（大幅度视角移动）")
        self.logger.info("  3. WASD 键盘测试")
        self.logger.info("\n" + "=" * 60)

        # 倒计时
        for i in range(3, 0, -1):
            self.logger.info(f"\n开始测试倒计时: {i} 秒...")
            time.sleep(1)

        self.logger.info("\n开始测试！\n")

        try:
            # 1. 鼠标移动测试
            self.test_mouse_movement()

            # 短暂暂停
            time.sleep(1)

            # 2. 键盘移动测试
            self.test_keyboard_movement()

            # 测试完成
            self.logger.info("\n" + "=" * 60)
            self.logger.success("  所有测试完成！")
            self.logger.info("=" * 60)
            self.logger.info("\n测试结果：")
            self.logger.info("  ✓ 鼠标移动测试 - 6 个方向")
            self.logger.info("  ✓ WASD 键盘测试 - 4 个按键")
            self.logger.info("\n如果游戏中视角和角色都有移动，说明测试成功！")
            self.logger.info("=" * 60 + "\n")

        except KeyboardInterrupt:
            self.logger.info("\n\n用户中断测试")
        except Exception as e:
            self.logger.error(f"\n\n测试过程中出错: {e}")
            import traceback
            traceback.print_exc()


def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="一键式输入测试工具")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试日志",
    )
    args = parser.parse_args()

    tester = AutoInputTester(debug=args.debug)
    tester.run()


if __name__ == "__main__":
    main()
