#!/usr/bin/env python3
"""
输入模拟模块
使用pynput模拟键盘输入
"""

import time
import random
from typing import Optional
from pynput.keyboard import Key, Controller
from src.logger import get_logger


class InputSimulator:
    """输入模拟器"""

    def __init__(self, debug: bool = False):
        """
        初始化输入模拟器

        Args:
            debug: 是否启用调试模式
        """
        self.debug = debug
        self.logger = get_logger(debug=debug)
        self.keyboard = Controller()
        self.last_key_time = 0
        self.min_interval = 0.05  # 最小按键间隔 (50ms)

    def press_key(self, key: str, duration: Optional[float] = None,
                  add_random_delay: bool = True) -> bool:
        """
        按下并释放按键

        Args:
            key: 按键名称 ('w', 'a', 's', 'd', 'space', 'q', 'e'等)
            duration: 按键持续时间 (秒)，None表示瞬时按下
            add_random_delay: 是否添加随机延迟

        Returns:
            bool: 是否成功
        """
        try:
            # 将字符串转换为pynput键
            pynput_key = self._parse_key(key)
            if pynput_key is None:
                self.logger.error(f"无效的按键: {key}")
                return False

            # 强制延迟以避免高频输入
            current_time = time.time()
            elapsed = current_time - self.last_key_time

            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                time.sleep(sleep_time)

            # 添加随机延迟 (5-150ms)
            if add_random_delay:
                delay = random.uniform(0.005, 0.15)
                time.sleep(delay)

            # 执行按键
            self.keyboard.press(pynput_key)

            if duration is not None:
                time.sleep(duration)

            self.keyboard.release(pynput_key)

            self.last_key_time = time.time()

            if self.debug:
                if duration is not None:
                    self.logger.debug_msg(f"按键 '{key}' (持续 {duration:.3f}s)")
                else:
                    self.logger.debug_msg(f"按键 '{key}' (瞬时)")

            return True

        except Exception as e:
            self.logger.error(f"按键 '{key}' 失败: {e}")
            return False

    def press_and_hold(self, key: str) -> bool:
        """
        按下按键并保持 (需要手动释放)

        Args:
            key: 按键名称

        Returns:
            bool: 是否成功
        """
        try:
            pynput_key = self._parse_key(key)
            if pynput_key is None:
                return False

            self.keyboard.press(pynput_key)
            self.last_key_time = time.time()

            if self.debug:
                self.logger.debug_msg(f"按下并保持: '{key}'")

            return True
        except Exception as e:
            self.logger.error(f"按下 '{key}' 失败: {e}")
            return False

    def release_key(self, key: str) -> bool:
        """
        释放按键

        Args:
            key: 按键名称

        Returns:
            bool: 是否成功
        """
        try:
            pynput_key = self._parse_key(key)
            if pynput_key is None:
                return False

            self.keyboard.release(pynput_key)

            if self.debug:
                self.logger.debug_msg(f"释放: '{key}'")

            return True
        except Exception as e:
            self.logger.error(f"释放 '{key}' 失败: {e}")
            return False

    def _parse_key(self, key: str) -> Optional:
        """
        解析按键字符串为pynput键对象

        Args:
            key: 按键名称

        Returns:
            pynput键对象或None
        """
        key_lower = key.lower()

        # 特殊按键映射
        special_keys = {
            'space': Key.space,
            'enter': Key.enter,
            'esc': Key.esc,
            'escape': Key.esc,
            'tab': Key.tab,
            'shift': Key.shift,
            'ctrl': Key.ctrl,
            'control': Key.ctrl,
            'alt': Key.alt,
            'up': Key.up,
            'down': Key.down,
            'left': Key.left,
            'right': Key.right,
        }

        if key_lower in special_keys:
            return special_keys[key_lower]

        # 单个字符
        if len(key) == 1:
            return key

        self.logger.error(f"无法解析按键: {key}")
        return None

    def wait(self, duration: float, add_random_delay: bool = True) -> bool:
        """
        等待指定时间

        Args:
            duration: 等待时间 (秒)
            add_random_delay: 是否添加随机延迟

        Returns:
            bool: 是否成功
        """
        try:
            # 添加随机延迟 (±10%)
            if add_random_delay:
                duration *= random.uniform(0.9, 1.1)

            if self.debug:
                self.logger.debug_msg(f"等待 {duration:.3f}s")

            time.sleep(duration)
            return True
        except Exception as e:
            self.logger.error(f"等待失败: {e}")
            return False


def test_input_simulator():
    """测试输入模拟器"""
    logger = get_logger(debug=True)
    logger.info("=" * 50)
    logger.info("输入模拟模块测试")
    logger.info("=" * 50)

    logger.warning("⚠ 此测试将在3秒后开始，请确保焦点在文本编辑器中")
    logger.warning("⚠ 测试将输出 'test' 并移动光标")

    # 等待3秒
    for i in range(3, 0, -1):
        logger.info(f"倒计时: {i}...")
        time.sleep(1)

    logger.info("\n[测试1] 瞬时按键测试...")
    sim = InputSimulator(debug=True)

    # 测试瞬时按键
    keys = ['t', 'e', 's', 't']
    for key in keys:
        sim.press_key(key)
        time.sleep(0.1)

    sim.press_key('enter')
    logger.success("✓ 瞬时按键测试完成")

    logger.info("\n[测试2] 持续按键测试...")
    # 测试持续按键 (移动光标)
    sim.press_key('left', duration=0.5)
    sim.press_key('right', duration=0.3)
    sim.press_key('enter')
    logger.success("✓ 持续按键测试完成")

    logger.info("\n[测试3] 组合按键测试...")
    # 测试组合按键
    sim.press_key('shift')
    sim.press_key('2')  # 输出 @
    sim.release_key('shift')
    sim.press_key('space')
    logger.success("✓ 组合按键测试完成")

    logger.info("\n[测试4] 特殊按键测试...")
    # 测试特殊按键
    sim.press_key('tab')
    sim.press_key('space')
    sim.press_key('enter')
    logger.success("✓ 特殊按键测试完成")

    logger.success("\n✓ 输入模拟测试完成")
    logger.info("=" * 50)
    return True


if __name__ == "__main__":
    test_input_simulator()
