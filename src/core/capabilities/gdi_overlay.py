#!/usr/bin/env python3
"""
GDI 覆盖绘制模块
在游戏窗口上使用 GDI 绘制检测框
"""

import win32gui
import win32ui
import win32con
import win32api
from typing import List, Optional
from src.core.capabilities.detection import DetectionResult
from src.logger import get_logger

# 颜色定义 (RGB 格式，GDI 使用 0x00BBGGRR 格式)
def rgb(r: int, g: int, b: int) -> int:
    """转换为 GDI COLORREF (0x00BBGGRR)"""
    return b << 16 | g << 8 | r


COLOR_GREEN = rgb(0, 255, 0)
COLOR_RED = rgb(0, 0, 255)
COLOR_WHITE = rgb(255, 255, 255)
COLOR_BLACK = rgb(0, 0, 0)
COLOR_YELLOW = rgb(0, 255, 255)


class GDIOverlay:
    """GDI 覆盖层"""

    def __init__(self, hwnd: int, debug: bool = False):
        """
        初始化 GDI 覆盖层

        Args:
            hwnd: 游戏窗口句柄
            debug: 是否启用调试模式
        """
        self.hwnd = hwnd
        self.debug = debug
        self.logger = get_logger(debug=debug)
        self._dc: Optional[int] = None
        self._pen: Optional[int] = None
        self._brush: Optional[int] = None
        self._font: Optional[int] = None

    def start(self) -> bool:
        """
        获取窗口 DC 并初始化绘图对象

        Returns:
            是否成功
        """
        try:
            # 获取窗口 DC（pywin32 可能返回元组或 int）
            dc_result = win32gui.GetDC(self.hwnd)
            self._dc = dc_result[0] if isinstance(dc_result, tuple) else int(dc_result)
            if self._dc is None:
                self.logger.error("获取窗口 DC 失败")
                return False

            # 创建画笔 (3px 绿色实线)
            self._pen = win32gui.CreatePen(win32con.PS_SOLID, 3, COLOR_GREEN)

            # 创建画刷 (半透明填充用 — GDI 无 alpha，用实心绿代替)
            self._brush = win32gui.CreateSolidBrush(COLOR_GREEN)

            # 创建字体
            self._font = win32gui.CreateFont(
                18, 0, 0, 0, win32con.FW_BOLD, 0, 0, 0,
                win32con.DEFAULT_CHARSET,
                win32con.OUT_DEFAULT_PRECIS,
                win32con.CLIP_DEFAULT_PRECIS,
                win32con.DEFAULT_QUALITY,
                win32con.DEFAULT_PITCH | win32con.FF_DONTCARE,
                "Microsoft YaHei"
            )

            self.logger.success("GDI 覆盖层已启动")
            return True

        except Exception as e:
            self.logger.error(f"GDI 覆盖层启动失败: {e}")
            return False

    def draw(self, detections: List[DetectionResult]):
        """
        在窗口上绘制检测结果

        Args:
            detections: 检测结果列表
        """
        if self._dc is None:
            return

        try:
            # 保存当前对象
            old_pen = win32gui.SelectObject(self._dc, self._pen)
            old_brush = win32gui.SelectObject(self._dc, win32gui.GetStockObject(win32con.NULL_BRUSH))
            old_font = win32gui.SelectObject(self._dc, self._font)

            # 设置文字颜色为白色
            win32gui.SetTextColor(self._dc, COLOR_WHITE)
            # 设置文字背景为透明
            win32gui.SetBkMode(self._dc, win32con.TRANSPARENT)

            for det in detections:
                # 绘制矩形框
                win32gui.Rectangle(
                    self._dc,
                    det.x1, det.y1,
                    det.x2 + 1, det.y2 + 1  # +1 因为 GDI 的 Rectangle 是排他的
                )

                # 绘制中心点（小红点）
                dot_pen = win32gui.CreatePen(win32con.PS_SOLID, 2, COLOR_RED)
                old_dot_pen = win32gui.SelectObject(self._dc, dot_pen)
                win32gui.Ellipse(self._dc, det.x1 + (det.width // 2) - 3,
                                 det.y1 + (det.height // 2) - 3,
                                 det.x1 + (det.width // 2) + 3,
                                 det.y1 + (det.height // 2) + 3)
                win32gui.SelectObject(self._dc, old_dot_pen)
                win32gui.DeleteObject(dot_pen)

                # 绘制标签（类别名 + 置信度）
                label = f"{det.confidence:.0%}"
                win32gui.TextOut(self._dc, det.x1 + 4, det.y1 - 18, label)

            # 恢复对象
            win32gui.SelectObject(self._dc, old_font)
            win32gui.SelectObject(self._dc, old_brush)
            win32gui.SelectObject(self._dc, old_pen)

        except Exception as e:
            self.logger.error(f"GDI 绘制失败: {e}")

    def clear(self):
        """清除覆盖层（重绘窗口触发刷新）"""
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            # 强制窗口重绘（擦除背景）
            win32gui.RedrawWindow(
                self.hwnd,
                None, None,
                win32con.RDW_INVALIDATE | win32con.RDW_ERASE | win32con.RDW_UPDATENOW
            )

    def stop(self):
        """释放 GDI 资源"""
        try:
            if self._font:
                win32gui.DeleteObject(self._font)
            if self._brush:
                win32gui.DeleteObject(self._brush)
            if self._pen:
                win32gui.DeleteObject(self._pen)
            if self._dc:
                win32gui.ReleaseDC(self.hwnd, self._dc)
            self.logger.info("GDI 覆盖层已停止")
        except Exception as e:
            self.logger.error(f"GDI 覆盖层停止失败: {e}")

    def __enter__(self):
        if self.start():
            return self
        return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
