#!/usr/bin/env python3
"""
一键式输入测试工具

自动测试 Interception 驱动的键盘和鼠标功能：
1. 启动后等待 3 秒让用户切换到游戏窗口
2. 自动测试鼠标移动（视角移动，考虑边界限制）
3. 自动测试 WASD 键盘移动

使用方法：
    uv run python -m tests.test_input_auto

测试流程：
    1. 等待 3 秒 → 切换到游戏窗口
    2. 鼠标移动测试（安全幅度，避免边界截断）
    3. WASD 键盘测试（前后左右移动）
"""

import sys
import ctypes

# 强制 Python 进程感知 DPI
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

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

        # 游戏窗口安全移动限制
        # X轴：窗口宽度的一半（640px）是中心，安全上限设为 500px
        # Y轴：避免低头/看天锁死，设为 350px
        self.MAX_SAFE_X = 500  # 单次X轴移动上限
        self.MAX_SAFE_Y = 350  # 单次Y轴移动上限

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
            self._hardware_mouse_detected = False
        except Exception as e:
            self.logger.error(f"Interception 初始化失败: {e}")
            self.logger.info("请确认：")
            self.logger.info("1. 已安装 Interception 驱动")
            self.logger.info("2. 以管理员身份运行")
            self.logger.info("3. 驱动服务已启动")
            sys.exit(1)

    def ensure_hardware_mouse_ready(self, timeout_seconds: float = 8.0):
        """初始化阶段挂载真实硬件鼠标。"""
        if self._hardware_mouse_detected:
            return

        try:
            detected = self.simulator.auto_detect_hardware_mouse(timeout_seconds=timeout_seconds)
            self._hardware_mouse_detected = True
            self.logger.success(f"硬件鼠标挂载完成，设备号: {detected}")
        except Exception as e:
            self.logger.warning(f"自动挂载真实鼠标失败，将沿用当前设备号: {e}")

    def capture_game_focus(self):
        """强制游戏引擎捕获鼠标，进入 3D 视角模式。"""
        hwnd = getattr(self.window_mgr, "hwnd", None)
        region = self.window_mgr.get_region()

        if not hwnd or not region:
            self.logger.warning("无法执行焦点捕获：窗口句柄或区域无效")
            return

        # A. 窗口拉到前台
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)

        # B. 系统光标移动到客户区中心
        left, top, width, height = region
        center_x = left + width // 2
        center_y = top + height // 2
        ctypes.windll.user32.SetCursorPos(center_x, center_y)
        time.sleep(0.05)

        # C. 左键点击一次，让引擎锁定鼠标
        self.simulator.mouse_click()
        time.sleep(0.1)

    def safe_mouse_move(self, dx: int, dy: int):
        """安全的鼠标移动，自动拆分大位移为安全的小位移。

        Args:
            dx: X轴总位移
            dy: Y轴总位移
        """
        # 计算需要拆分的次数
        x_splits = 1
        y_splits = 1

        if abs(dx) > self.MAX_SAFE_X:
            x_splits = (abs(dx) + self.MAX_SAFE_X - 1) // self.MAX_SAFE_X

        if abs(dy) > self.MAX_SAFE_Y:
            y_splits = (abs(dy) + self.MAX_SAFE_Y - 1) // self.MAX_SAFE_Y

        # 取较大值作为总拆分数
        total_splits = max(x_splits, y_splits)

        if total_splits > 1:
            self.logger.info(f"    大位移检测：拆分为 {total_splits} 次安全移动")

        # 分段移动
        for i in range(total_splits):
            ratio = (i + 1) / total_splits
            prev_ratio = i / total_splits if i > 0 else 0

            cur_dx = int(dx * ratio) - int(dx * prev_ratio)
            cur_dy = int(dy * ratio) - int(dy * prev_ratio)

            if cur_dx != 0 or cur_dy != 0:
                self.simulator.mouse_move(cur_dx, cur_dy)

                # 小延迟模拟真实操作
                if i < total_splits - 1:  # 不是最后一次
                    time.sleep(0.03)  # 30ms 延迟

    def test_mouse_movement(self):
        """测试鼠标移动（视角移动，使用相对移动）。"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("  [1/2] 鼠标移动测试（视角移动 - 相对移动）")
        self.logger.info("=" * 60)
        self.logger.info("\n注意：游戏内视角控制使用鼠标相对移动（delta），不是绝对位置")

        # 安全的相对移动测试（避免边界截断和视角锁死）
        # 注意：X轴限制500px（避免超过窗口中心640px），Y轴限制350px（避免低头/看天）
        movements = [
            ("向右", 500, 0),         # 安全上限测试
            ("向下", 0, 350),         # Y轴安全上限测试
            ("向左", -500, 0),        # 左转安全测试
            ("向上", 0, -350),        # 抬头安全测试
            ("右下对角", 400, 300),   # 对角线组合
            ("左上对角", -400, -300), # 对角线组合
            ("顺时针圆形-1", 300, 0), # 圆形第1步
            ("顺时针圆形-2", 0, 300), # 圆形第2步
            ("顺时针圆形-3", -300, 0), # 圆形第3步
            ("顺时针圆形-4", 0, -300), # 圆形第4步
        ]

        for i, (direction, dx, dy) in enumerate(movements, 1):
            self.logger.info(f"\n[{i}/{len(movements)}] 测试 {direction} 移动 ({dx:+d}, {dy:+d})")

            # 每次真实移动前先执行焦点捕获，确保游戏进入可响应状态
            self.capture_game_focus()

            # 使用安全的移动方法
            self.safe_mouse_move(dx, dy)

            self.logger.success(f"✓ {direction} 移动完成")
            time.sleep(0.6)  # 每次移动间隔

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
            # 1) 初始化阶段挂载真实鼠标硬件
            self.ensure_hardware_mouse_ready(timeout_seconds=8.0)

            # 1. 鼠标移动测试（平滑算法）
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
            self.logger.info("  ✓ 平滑鼠标移动测试 - 10 个方向（拟人化）")
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
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="仅列出可用 Interception 设备并退出",
    )
    parser.add_argument(
        "--keyboard-device",
        type=int,
        default=None,
        help="强制指定键盘设备号",
    )
    parser.add_argument(
        "--mouse-device",
        type=int,
        default=None,
        help="强制指定鼠标设备号",
    )
    parser.add_argument(
        "--auto-detect-mouse",
        action="store_true",
        help="自动检测真实的物理鼠标设备号",
    )
    args = parser.parse_args()

    tester = AutoInputTester(debug=args.debug)

    # 列出设备
    if args.list_devices:
        devices = tester.simulator.list_all_devices()
        print("\n可用 Interception 设备：")
        print(f"  键盘设备: {devices['keyboards']}")
        print(f"  鼠标设备: {devices['mice']}")
        print(f"\n当前选择:")
        print(f"  键盘: {tester.simulator._keyboard_device}")
        print(f"  鼠标: {tester.simulator._mouse_device}")

        print("\n设备详细信息：")
        print("  --- 键盘设备 ---")
        for d in devices['keyboards']:
            info = tester.simulator.get_device_info(d)
            marker = " ←当前" if d == tester.simulator._keyboard_device else ""
            print(f"  [{d:2d}] hw_id={info['hw_id'][:32]}...{marker}" if len(info['hw_id']) > 32 else f"  [{d:2d}] hw_id={info['hw_id']}{marker}")

        print("\n  --- 鼠标设备 ---")
        for d in devices['mice']:
            info = tester.simulator.get_device_info(d)
            marker = " ←当前" if d == tester.simulator._mouse_device else ""
            print(f"  [{d:2d}] hw_id={info['hw_id'][:32]}...{marker}" if len(info['hw_id']) > 32 else f"  [{d:2d}] hw_id={info['hw_id']}{marker}")

        print("\n用法:")
        print("  --keyboard-device <n>  指定键盘设备号")
        print("  --mouse-device <n>     指定鼠标设备号")
        return

    # 自动检测物理鼠标
    if args.auto_detect_mouse:
        try:
            detected_device = tester.simulator.auto_detect_hardware_mouse(timeout_seconds=10.0)
            tester._hardware_mouse_detected = True
            print(f"\n✓ 检测到物理鼠标设备号: {detected_device}")
        except RuntimeError as e:
            print(f"\n✗ 自动检测失败: {e}")
            print("您可以使用 --mouse-device 手动指定设备号")
            sys.exit(1)

    # 覆盖设备（如指定）
    if args.keyboard_device is not None:
        tester.simulator.set_device_override(keyboard=args.keyboard_device)
    if args.mouse_device is not None:
        tester.simulator.set_device_override(mouse=args.mouse_device)

    tester.run()


if __name__ == "__main__":
    main()
