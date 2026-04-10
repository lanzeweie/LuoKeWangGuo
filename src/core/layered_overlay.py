#!/usr/bin/env python3
"""
DWM 分层覆盖窗口
使用 WS_EX_LAYERED + UpdateLayeredWindow 实现透明覆盖层
游戏需要使用"无边框窗口模式"才能被覆盖
"""

import ctypes
from ctypes import wintypes, Structure, POINTER, byref, sizeof
import win32gui
import win32con
import numpy as np
from typing import List, Optional
from src.core.detection import DetectionResult
from src.logger import get_logger

# ── Windows 常量 ──
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01

# ── ctypes 结构体 ──


class BLENDFUNCTION(Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


class POINT(Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class SIZE(Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BITMAPINFOHEADER(Structure):
    _pack_ = 1
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class BITMAPINFO(Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER)]


# ── 加载 DLL ──
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, POINTER(POINT),
    POINTER(SIZE), wintypes.HDC, POINTER(POINT),
    ctypes.c_uint, POINTER(BLENDFUNCTION), ctypes.c_ulong
]
user32.UpdateLayeredWindow.restype = ctypes.c_bool

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.c_void_p, ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_uint32
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = ctypes.c_bool
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = ctypes.c_bool
gdi32.SetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
gdi32.SetPixel.restype = ctypes.c_uint


class LayeredOverlay:
    """DWM 分层覆盖窗口"""

    def __init__(self, x: int, y: int, width: int, height: int, debug: bool = False):
        """
        初始化分层覆盖窗口

        Args:
            x, y: 窗口位置（屏幕坐标）
            width, height: 窗口尺寸
            debug: 调试模式
        """
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.debug = debug
        self.logger = get_logger(debug=debug)
        self._hwnd: Optional[int] = None
        self._mem_dc: Optional[int] = None
        self._screen_dc: Optional[int] = None
        self._bitmap: Optional[int] = None
        self._bits_ptr: Optional[int] = None  # 指向像素数据的指针
        self._buffer: Optional[np.ndarray] = None  # numpy 视图 (H, W, 4) BGRA

    def create_window(self) -> bool:
        """创建分层窗口"""
        try:
            # 注册窗口类
            class_name = f"LuokeOverlay_{id(self)}"
            wc = win32gui.WNDCLASS()
            wc.lpszClassName = class_name
            wc.hbrBackground = win32gui.GetStockObject(win32con.NULL_BRUSH)
            wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
            wc.hInstance = 0
            try:
                win32gui.RegisterClass(wc)
            except Exception:
                pass

            # 创建窗口
            self._hwnd = win32gui.CreateWindowEx(
                WS_EX_LAYERED | WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST,
                class_name,
                "LuokeOverlay",
                win32con.WS_POPUP,
                self.x, self.y, self.width, self.height,
                0, 0, 0, None
            )

            if not self._hwnd:
                self.logger.error("创建分层窗口失败")
                return False

            win32gui.ShowWindow(self._hwnd, win32con.SW_SHOWNA)

            # 创建离屏 DC
            self._screen_dc = win32gui.GetDC(0)
            self._mem_dc = gdi32.CreateCompatibleDC(self._screen_dc)

            # 创建 32 位 DIB 位图 (BGRA)
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = self.width
            bmi.bmiHeader.biHeight = -self.height  # 负值 = 从上到下
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0  # BI_RGB
            bmi.bmiHeader.biSizeImage = self.width * self.height * 4

            bits_ptr = ctypes.c_void_p()
            self._bitmap = gdi32.CreateDIBSection(
                self._mem_dc,
                byref(bmi),
                0,
                byref(bits_ptr),
                0, 0
            )

            if not self._bitmap:
                self.logger.error("创建 DIB 位图失败")
                return False

            gdi32.SelectObject(self._mem_dc, self._bitmap)
            self._bits_ptr = bits_ptr.value

            # 创建 numpy 视图，方便操作像素
            buf = (ctypes.c_uint8 * (self.height * self.width * 4)).from_address(self._bits_ptr)
            self._buffer = np.ctypeslib.as_array(buf).reshape((self.height, self.width, 4))

            self.logger.success(
                f"分层覆盖窗口已创建 ({self.x},{self.y},{self.width}x{self.height})"
            )
            return True

        except Exception as e:
            self.logger.error(f"分层窗口创建失败: {e}")
            return False

    def draw(self, detections: List[DetectionResult]):
        """绘制检测结果到分层窗口"""
        if self._buffer is None or self._hwnd is None:
            return

        try:
            buf = self._buffer
            # 清屏 — 全部设为完全透明
            buf[:, :, 0] = 0   # B
            buf[:, :, 1] = 0   # G
            buf[:, :, 2] = 0   # R
            buf[:, :, 3] = 0   # A

            for det in detections:
                x1, y1, x2, y2 = det.x1, det.y1, det.x2, det.y2
                cx, cy = det.center

                # ── 画矩形框 ──
                thickness = 3
                # 上下边
                buf[y1:y1 + thickness, x1:x2] = [0, 255, 0, 255]
                buf[y2 - thickness:y2, x1:x2] = [0, 255, 0, 255]
                # 左右边
                buf[y1:y2, x1:x1 + thickness] = [0, 255, 0, 255]
                buf[y1:y2, x2 - thickness:x2] = [0, 255, 0, 255]

                # ── 画中心点 ──
                for dy in range(-4, 5):
                    for dx in range(-4, 5):
                        if dx * dx + dy * dy <= 16:
                            py, px = cy + dy, cx + dx
                            if 0 <= py < self.height and 0 <= px < self.width:
                                buf[py, px] = [0, 0, 255, 255]

                # ── 画标签（简化为白色像素行） ──
                label = f"{det.confidence:.0%}"
                for i, ch in enumerate(label):
                    # 简化的标签：在框上方画一条白线
                    lx = x1 + 4 + i * 5
                    if 0 <= lx < self.width and y1 - 12 >= 0:
                        buf[y1 - 12:y1 - 6, lx:lx + 4] = [255, 255, 255, 255]

            # ── 提交到分层窗口 ──
            blend = BLENDFUNCTION()
            blend.BlendOp = AC_SRC_OVER
            blend.BlendFlags = 0
            blend.SourceConstantAlpha = 255
            blend.AlphaFormat = AC_SRC_ALPHA

            pt_dst = POINT(self.x, self.y)
            size = SIZE(self.width, self.height)
            pt_src = POINT(0, 0)

            user32.UpdateLayeredWindow(
                self._hwnd,
                self._screen_dc,
                byref(pt_dst),
                byref(size),
                self._mem_dc,
                byref(pt_src),
                0,
                byref(blend),
                ULW_ALPHA
            )

        except Exception as e:
            self.logger.error(f"分层窗口绘制失败: {e}")

    def destroy(self):
        """销毁覆盖窗口"""
        try:
            if self._bitmap:
                gdi32.DeleteObject(self._bitmap)
            if self._mem_dc:
                gdi32.DeleteDC(self._mem_dc)
            if self._screen_dc:
                win32gui.ReleaseDC(0, self._screen_dc)
            if self._hwnd:
                win32gui.DestroyWindow(self._hwnd)
            self.logger.info("分层覆盖窗口已销毁")
        except Exception as e:
            self.logger.error(f"分层窗口销毁失败: {e}")
