#!/usr/bin/env python3
"""
窗口管理模块
通过进程名查找并定位洛克王国窗口
"""

import win32gui
import win32process
import win32con
from typing import Optional, Tuple
import psutil
from src.logger import get_logger


class WindowManager:
    """窗口管理器"""

    def __init__(self, process_name: str = "NRC-Win64-Shipping.exe",
                 client_size: Tuple[int, int] = (1280, 720),
                 border_offset: int = 0, debug: bool = False):
        self.process_name = process_name.lower()
        self.client_size = client_size  # 期望的客户区尺寸 (宽, 高)
        self.border_offset = border_offset  # 额外裁剪边框偏移（像素）
        self.debug = debug
        self.logger = get_logger(debug=debug)
        self.hwnd: Optional[int] = None
        self.rect: Optional[Tuple[int, int, int, int]] = None
        self.left: int = 0
        self.top: int = 0
        self.width: int = 0
        self.height: int = 0
        self.center_x: int = 0
        self.center_y: int = 0

    def find_window(self) -> bool:
        """
        通过进程名查找窗口

        Returns:
            True if window found, False otherwise
        """
        self.logger.info(f"查找窗口: {self.process_name}")

        def callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                try:
                    # Get window text (title)
                    window_title = win32gui.GetWindowText(hwnd)
                    if not window_title:
                        return True

                    # Get process ID
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid == 0:
                        return True

                    # Get process name
                    process = psutil.Process(pid)
                    process_name = process.name().lower()

                    if self.process_name in process_name:
                        self.hwnd = int(hwnd) if not isinstance(hwnd, tuple) else int(hwnd[0])
                        self.logger.success(f"找到窗口: {window_title}")
                        return False  # Stop enumeration
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                except Exception as e:
                    self.logger.debug_msg(f"枚举窗口时出错: {e}")
            return True

        try:
            win32gui.EnumWindows(callback, None)
        except Exception as e:
            # 回调返回 False 时会触发此异常，但窗口可能已找到
            if self.hwnd is None:
                self.logger.error(f"枚举窗口失败: {e}")
                return False

        if self.hwnd:
            self.rect = win32gui.GetWindowRect(self.hwnd)
            return True

        self.logger.error("未找到游戏窗口")
        self.logger.info("请确保洛克王国游戏已启动")
        return False

    def get_window_rect(self) -> Optional[Tuple[int, int, int, int]]:
        """
        获取窗口位置和尺寸

        Returns:
            (left, top, right, bottom) or None
        """
        if not self.hwnd:
            if not self.find_window():
                return None

        try:
            self.rect = win32gui.GetWindowRect(self.hwnd)
            return self.rect
        except Exception as e:
            self.logger.error(f"获取窗口信息失败: {e}")
            return None

    def get_window_size(self) -> Optional[Tuple[int, int]]:
        """
        获取窗口尺寸

        Returns:
            (width, height) or None
        """
        rect = self.get_window_rect()
        if rect:
            left, top, right, bottom = rect
            return (right - left, bottom - top)
        return None

    def get_window_coords(self) -> Optional[Tuple[int, int, int, int]]:
        """
        获取窗口坐标和尺寸

        Returns:
            (left, top, width, height) or None
        """
        rect = self.get_window_rect()
        if rect is None:
            return None

        left, top, right, bottom = rect
        self.left = left
        self.top = top
        self.width = right - left
        self.height = bottom - top
        self.center_x = self.left + self.width // 2
        self.center_y = self.top + self.height // 2

        self.logger.info(f"窗口位置: ({self.left}, {self.top})")
        self.logger.info(f"窗口尺寸: {self.width}x{self.height}")

        return (self.left, self.top, self.width, self.height)

    def is_foreground(self) -> bool:
        """检查窗口是否在前台"""
        if not self.hwnd:
            return False
        return win32gui.GetForegroundWindow() == self.hwnd

    def is_minimized(self) -> bool:
        """检查窗口是否最小化"""
        if not self.hwnd:
            return True
        return win32gui.IsIconic(self.hwnd)

    def bring_to_foreground(self):
        """将窗口带到前台"""
        if self.hwnd:
            try:
                # 如果最小化，先恢复
                if self.is_minimized():
                    win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                    self.logger.info("已恢复最小化窗口")

                win32gui.SetForegroundWindow(self.hwnd)
                self.logger.debug_msg("窗口已置顶")
            except Exception as e:
                self.logger.error(f"置顶窗口失败: {e}")

    def get_region(self) -> Optional[Tuple[int, int, int, int]]:
        """
        获取捕获区域 (client area)

        Returns:
            (left, top, width, height) or None
        """
        if not self.hwnd:
            return None

        try:
            # Get client area (excluding title bar, borders)
            client_rect = win32gui.GetClientRect(self.hwnd)
            left, top = win32gui.ClientToScreen(self.hwnd, (0, 0))
            width = client_rect[2]
            height = client_rect[3]

            # 验证客户区尺寸是否匹配期望值
            expected_w, expected_h = self.client_size
            if width != expected_w or height != expected_h:
                self.logger.warning(
                    f"客户区尺寸 ({width}x{height}) 与期望值 ({expected_w}x{expected_h}) 不一致"
                )

            # 应用边框偏移裁剪（去除可能的边框残留）
            offset = self.border_offset
            if offset > 0:
                left += offset
                top += offset
                width -= offset * 2
                height -= offset * 2
                self.logger.info(f"应用边框裁剪: offset={offset}, 裁剪后区域=({left}, {top}, {width}, {height})")

            self.logger.debug_msg(f"捕获区域: ({left}, {top}, {width}, {height})")
            return (left, top, width, height)
        except Exception as e:
            self.logger.error(f"获取捕获区域失败: {e}")
            return None

    def get_screen_region(self) -> Optional[Tuple[int, int, int, int]]:
        """
        获取屏幕捕获区域 (用于dxcam)

        Returns:
            (left, top, right, bottom) or None
        """
        region = self.get_region()
        if region is None:
            return None

        left, top, width, height = region
        return (left, top, left + width, top + height)

    def get_center_position(self) -> Optional[Tuple[int, int]]:
        """
        获取窗口中心坐标

        Returns:
            (x, y) or None
        """
        if self.hwnd is None:
            return None

        if self.center_x == 0 or self.center_y == 0:
            self.get_window_coords()

        return (self.center_x, self.center_y)


def test_window_manager():
    """测试窗口管理器"""
    logger = get_logger(debug=True)
    logger.info("=" * 50)
    logger.info("窗口管理器测试")
    logger.info("=" * 50)

    # 测试1: 初始化
    logger.info("\n[测试1] 初始化窗口管理器...")
    mgr = WindowManager(debug=True)

    # 测试2: 查找窗口
    logger.info("\n[测试2] 查找窗口...")
    if not mgr.find_window():
        logger.error("未找到窗口，测试终止")
        return False

    # 测试3: 获取窗口信息
    logger.info("\n[测试3] 获取窗口坐标和尺寸...")
    coords = mgr.get_window_coords()
    if coords is None:
        logger.error("获取窗口信息失败")
        return False

    # 测试4: 检查窗口状态
    logger.info("\n[测试4] 检查窗口状态...")
    if mgr.is_minimized():
        logger.warning("窗口当前为最小化状态")
        mgr.bring_to_foreground()
    else:
        logger.info("窗口正常显示")

    # 测试5: 获取捕获区域
    logger.info("\n[测试5] 获取捕获区域...")
    region = mgr.get_region()
    if region:
        logger.info(f"捕获区域: {region}")
    else:
        logger.error("获取捕获区域失败")
        return False

    # 测试6: 获取屏幕区域
    logger.info("\n[测试6] 获取屏幕捕获区域...")
    screen_region = mgr.get_screen_region()
    if screen_region:
        logger.info(f"屏幕区域: {screen_region}")
    else:
        logger.error("获取屏幕区域失败")
        return False

    # 测试7: 获取中心坐标
    logger.info("\n[测试7] 获取窗口中心...")
    center = mgr.get_center_position()
    if center:
        logger.info(f"窗口中心: {center}")
    else:
        logger.error("获取中心坐标失败")
        return False

    logger.success("\n✓ 所有测试通过")
    logger.info("=" * 50)
    return True


if __name__ == "__main__":
    test_window_manager()
