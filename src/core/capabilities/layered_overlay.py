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
from typing import List, Optional, Tuple
from src.core.capabilities.detection import DetectionResult
from src.core.capabilities.target_scoring import TargetScore
from src.logger import get_logger

# Pillow 导入 - 用于字体渲染
try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("警告: Pillow 未安装，将使用简化文字显示")

# ── Windows 常量 ──
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
# 截屏时排除窗口（关键！防止覆盖层框被截到下一帧，导致 YOLO 看到"带框的宠物"漏检）
WDA_EXCLUDEFROMCAPTURE = 0x00000011

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
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowDisplayAffinity.restype = wintypes.BOOL


class LayeredOverlay:
    """DWM 分层覆盖窗口"""

    # 默认类别名称列表
    DEFAULT_CLASS_NAMES = ["目标"]

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        debug: bool = False,
        class_names: Optional[List[str]] = None,
        # 尺寸配置
        box_thickness: int = 3,
        center_radius: int = 4,
        font_size_normal: int = 14,
        font_size_small: int = 10,
        font_size_large: int = 16,
        # 标签偏移（相对于检测框左上角）
        label_offset_y: int = -25,
        rank_offset_y: int = -24,
        class_offset_y: int = -40,
        distance_offset_y: int = -72,
        # 状态文字位置
        state_x: int = 16,
        state_y: int = 16,
        # 进度条
        bar_width: int = 100,
        bar_height: int = 10,
        bar_y: int = 16,
    ):
        """
        初始化分层覆盖窗口

        Args:
            x, y: 窗口位置（屏幕坐标）
            width, height: 窗口尺寸
            debug: 调试模式
            class_names: 类别名称列表，如 ["奇丽草群组"]
            box_thickness: 边框粗细（像素）
            center_radius: 中心点半径（像素）
            font_size_normal: 普通字体大小
            font_size_small: 小字体大小
            font_size_large: 大字体大小
            label_offset_y: 标签相对检测框左上角的 Y 偏移
            rank_offset_y: 优先级标签的 Y 偏移
            class_offset_y: 类别标签的 Y 偏移
            distance_offset_y: 距离标签的 Y 偏移
            state_x, state_y: 状态文字的绝对位置
            bar_width, bar_height: 验证进度条尺寸
            bar_y: 验证进度条的 Y 位置
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
        self._bits_ptr: Optional[int] = None
        self._buffer: Optional[np.ndarray] = None
        self._back_buffer: Optional[np.ndarray] = None
        self._class_names = class_names or self.DEFAULT_CLASS_NAMES

        # ── 尺寸配置 ──
        self._box_thickness = box_thickness
        self._center_radius = center_radius
        self._center_radius_sq = center_radius * center_radius  # 预计算，避免重复乘法
        self._font_size_normal = font_size_normal
        self._font_size_small = font_size_small
        self._font_size_large = font_size_large
        self._label_offset_y = label_offset_y
        self._rank_offset_y = rank_offset_y
        self._class_offset_y = class_offset_y
        self._distance_offset_y = distance_offset_y
        self._state_x = state_x
        self._state_y = state_y
        self._bar_width = bar_width
        self._bar_height = bar_height
        self._bar_y = bar_y

        # 字体相关 - 仅在需要时初始化
        self._font_cache = {}  # 字体缓存
        self._init_fonts()

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

            # 关键修复：设置 WDA_EXCLUDEFROMCAPTURE，防止覆盖层被截屏截取
            # 否则画框会污染下一帧截图，导致 YOLO 看到"带框的宠物"漏检
            user32.SetWindowDisplayAffinity(self._hwnd, WDA_EXCLUDEFROMCAPTURE)

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
            self._back_buffer = np.zeros((self.height, self.width, 4), dtype=np.uint8)

            self.logger.success(
                f"分层覆盖窗口已创建 ({self.x},{self.y},{self.width}x{self.height})"
            )
            return True

        except Exception as e:
            self.logger.error(f"分层窗口创建失败: {e}")
            return False

    def _init_fonts(self):
        """初始化字体缓存"""
        if not PILLOW_AVAILABLE:
            return

        try:
            # 尝试加载系统字体
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
                "C:/Windows/Fonts/simhei.ttf",  # 黑体
                "C:/Windows/Fonts/simsun.ttc",  # 宋体
            ]

            for path in font_paths:
                try:
                    self._font_cache['normal'] = ImageFont.truetype(path, self._font_size_normal)
                    self._font_cache['small'] = ImageFont.truetype(path, self._font_size_small)
                    self._font_cache['large'] = ImageFont.truetype(path, self._font_size_large)
                    self.logger.debug(f"字体加载成功: {path}")
                    break
                except:
                    continue

            if not self._font_cache:
                # 使用默认字体
                self._font_cache['normal'] = ImageFont.load_default()
                self._font_cache['small'] = ImageFont.load_default()
                self._font_cache['large'] = ImageFont.load_default()
                self.logger.warning("使用默认字体")

        except Exception as e:
            self.logger.error(f"字体初始化失败: {e}")

    def _draw_text(self, text: str, x: int, y: int, color: Tuple[int, int, int, int],
                   font_size: str = 'normal', max_width: int = 200) -> bool:
        """
        在离屏缓冲区绘制文字（完全离屏，不影响截屏）

        Args:
            text: 要绘制的文字（支持中文）
            x, y: 绘制位置（相对于覆盖层）
            color: BGRA 颜色值
            font_size: 字体大小 ('small', 'normal', 'large')
            max_width: 最大宽度，超出会换行

        Returns:
            bool: 是否绘制成功
        """
        if self.debug:
            print(f"[DEBUG] _draw_text 被调用: text='{text}' at ({x},{y})")

        if not PILLOW_AVAILABLE:
            if self.debug:
                print("[DEBUG] Pillow 不可用，使用备用方案")
            return self._draw_text_fallback(text, x, y, color)

        if self._back_buffer is None:
            if self.debug:
                print("[DEBUG] _back_buffer 是 None")
            return self._draw_text_fallback(text, x, y, color)

        if not text:
            if self.debug:
                print("[DEBUG] 文本为空")
            return self._draw_text_fallback(text, x, y, color)

        try:
            font = self._font_cache.get(font_size, self._font_cache.get('normal'))
            if not font:
                return self._draw_text_fallback(text, x, y, color)

            # 获取文字尺寸（原始尺寸）
            try:
                # 尝试使用 getbbox（新版本 Pillow）
                bbox = font.getbbox(text)
                orig_width = bbox[2] - bbox[0]
                orig_height = bbox[3] - bbox[1]
            except:
                # 回退到 getsize（旧版本 Pillow）
                orig_width, orig_height = font.getsize(text)

            # 确保不越界，计算实际绘制位置和尺寸
            draw_x = max(0, x)
            draw_y = max(0, y)

            # 计算实际可绘制的宽度
            if x < 0:
                # 如果 x 是负数，需要裁剪文字
                offset = -x
                text_to_draw = text  # 简化处理，还是绘制完整文字
                if draw_x + orig_width > self.width:
                    draw_width = self.width - draw_x
                else:
                    draw_width = orig_width
            else:
                text_to_draw = text
                if x + orig_width > self.width:
                    draw_width = self.width - x
                else:
                    draw_width = orig_width

            # 计算实际可绘制的高度
            if y < 0:
                if draw_y + orig_height > self.height:
                    draw_height = self.height - draw_y
                else:
                    draw_height = orig_height
            else:
                if y + orig_height > self.height:
                    draw_height = self.height - y
                else:
                    draw_height = orig_height

            # 如果没有可绘制空间，直接返回
            if draw_width <= 0 or draw_height <= 0:
                return False

            # 创建临时图像（使用原始尺寸，确保文字完整）
            temp_img = Image.new('RGBA', (orig_width, orig_height), (0, 0, 0, 0))
            temp_draw = ImageDraw.Draw(temp_img)

            # 绘制文字到临时图像
            temp_draw.text((0, 0), text_to_draw, font=font, fill=color[:3] + (color[3],))

            # 转换为 numpy 数组
            text_array = np.array(temp_img)
            if text_array.shape[2] == 4:  # RGBA
                # 裁剪数组以适应目标区域
                src_x = 0 if x >= 0 else -x
                src_y = 0 if y >= 0 else -y
                src_w = min(draw_width, orig_width - src_x)
                src_h = min(draw_height, orig_height - src_y)

                if src_w > 0 and src_h > 0:
                    # 复制裁剪后的文字到离屏缓冲区
                    self._back_buffer[draw_y:draw_y+src_h, draw_x:draw_x+src_w] = text_array[src_y:src_y+src_h, src_x:src_x+src_w]

            return True

        except Exception as e:
            print(f"[WARNING] 文字绘制失败，使用备用方案: {e}")
            return self._draw_text_fallback(text, x, y, color)

    def _draw_text_fallback(self, text: str, x: int, y: int, color: Tuple[int, int, int, int]) -> bool:
        """
        备用文字绘制方案 - 使用简单的色块表示

        完全离屏操作，不会影响截屏
        """
        try:
            # 用字符数量计算宽度
            char_count = len(text)
            block_width = char_count * 6  # 每个字符约6像素宽
            block_height = 6

            # 确保不越界
            if x < 0 or y < 0 or x + block_width > self.width or y + block_height > self.height:
                return False

            # 在离屏缓冲区画色块
            self._back_buffer[y:y+block_height, x:x+block_width] = color
            return True
        except:
            return False

    def draw(self, detections: List[DetectionResult]):
        """绘制检测结果到分层窗口"""
        if self._buffer is None or self._hwnd is None:
            return

        try:
            buf = self._back_buffer
            buf[:] = 0

            for det in detections:
                x1, y1, x2, y2 = det.x1, det.y1, det.x2, det.y2
                cx, cy = det.center

                # ── 画矩形框 ──
                buf[y1:y1 + self._box_thickness, x1:x2] = [0, 255, 0, 255]
                buf[y2 - self._box_thickness:y2, x1:x2] = [0, 255, 0, 255]
                buf[y1:y2, x1:x1 + self._box_thickness] = [0, 255, 0, 255]
                buf[y1:y2, x2 - self._box_thickness:x2] = [0, 255, 0, 255]

                # ── 画中心点 ──
                r = self._center_radius
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        if dx * dx + dy * dy <= self._center_radius_sq:
                            py, px = cy + dy, cx + dx
                            if 0 <= py < self.height and 0 <= px < self.width:
                                buf[py, px] = [0, 0, 255, 255]

                # ── 画类别名称标签（支持中文） ──
                class_name = self._class_names[det.class_id] if det.class_id < len(self._class_names) else f"ID{det.class_id}"
                label = f"{class_name} {det.confidence:.0%}"
                label_y = y1 + self._label_offset_y if y1 + self._label_offset_y >= 0 else y1 + 6
                success = self._draw_text(label, x1 + 4, label_y, (255, 255, 255, 255), 'normal')
                if self.debug:
                    print(f"[DEBUG] 绘制标签 '{label}' 在 ({x1 + 4}, {label_y}) {'成功' if success else '失败'}")

            # ── 双缓冲提交 ──
            np.copyto(self._buffer, self._back_buffer)
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

    # ── 距离状态颜色 ──
    _DISTANCE_COLORS = {
        "FAR": (0, 0, 255, 255),      # 红色 (B,G,R,A)
        "MEDIUM": (0, 255, 255, 255),  # 黄色 (B,G,R,A)
        "CLOSE": (0, 255, 0, 255),     # 绿色 (B,G,R,A)
    }

    def draw_scored(
        self,
        scored_detections: List[TargetScore],
        verification_progress: int = 0,
        verification_required: int = 0,
        current_state: str = "",
    ):
        """
        绘制带优先级和距离状态的检测结果

        Args:
            scored_detections: 已评分的目标列表
            verification_progress: 当前验证进度
            verification_required: 需要的验证周期数
            current_state: 当前状态文本
        """
        if self._buffer is None or self._hwnd is None:
            return

        try:
            buf = self._back_buffer
            buf[:] = 0

            for score in scored_detections:
                det = score.detection
                x1, y1, x2, y2 = det.x1, det.y1, det.x2, det.y2
                cx, cy = det.center

                # 根据距离状态选择颜色
                color = self._DISTANCE_COLORS.get(score.distance_state, (0, 255, 0, 255))

                # ── 画矩形框（颜色编码） ──
                buf[y1:y1 + self._box_thickness, x1:x2] = color
                buf[y2 - self._box_thickness:y2, x1:x2] = color
                buf[y1:y2, x1:x1 + self._box_thickness] = color
                buf[y1:y2, x2 - self._box_thickness:x2] = color

                # ── 画中心点 ──
                r = self._center_radius
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        if dx * dx + dy * dy <= self._center_radius_sq:
                            py, px = cy + dy, cx + dx
                            if 0 <= py < self.height and 0 <= px < self.width:
                                buf[py, px] = [255, 255, 255, 255]

                # ── 优先级标签 (#1, #2, ...) ──
                rank_label = f"#{score.priority_rank}"
                rank_y = y1 + self._rank_offset_y if y1 + self._rank_offset_y >= 0 else y2 + 6
                self._draw_text(rank_label, x1 + 4, rank_y, (255, 255, 255, 255), 'small')

                # ── 类别名称标签 ──
                class_name = self._class_names[det.class_id] if det.class_id < len(self._class_names) else f"ID{det.class_id}"
                class_label = f"{class_name} {det.confidence:.0%}"
                class_label_y = y1 + self._class_offset_y if y1 + self._class_offset_y >= 0 else y2 + 6
                self._draw_text(class_label, x1 + 4, class_label_y, (255, 255, 255, 255), 'small')

                # ── 距离状态标签（中文支持） ──
                distance_text = {
                    "FAR": "远",
                    "MEDIUM": "中",
                    "CLOSE": "近"
                }.get(score.distance_state, score.distance_state)
                distance_y = y1 + self._distance_offset_y if y1 + self._distance_offset_y >= 0 else y2 + 6
                self._draw_text(distance_text, x1 + 4, distance_y, color, 'small')

            # ── 验证进度条 ──
            if verification_required > 0 and verification_progress > 0:
                bar_x = self.width // 2 - self._bar_width // 2

                buf[self._bar_y:self._bar_y + self._bar_height, bar_x:bar_x + self._bar_width] = [128, 128, 128, 200]
                filled = int(self._bar_width * verification_progress / verification_required)
                if filled > 0:
                    buf[self._bar_y:self._bar_y + self._bar_height, bar_x:bar_x + filled] = [0, 255, 0, 255]

                progress_text = f"验证: {verification_progress}/{verification_required}"
                self._draw_text(progress_text, bar_x + self._bar_width + 8, self._bar_y, (255, 255, 255, 255), 'small')

            # ── 状态文本（中文支持） ──
            if current_state:
                state_text_map = {
                    "SEARCH": "搜索中",
                    "VERIFY": "验证中",
                    "NAVIGATE": "靠近中",
                    "AIM_AND_THROW": "瞄准投掷",
                    "WAIT_RESULT": "等待结果",
                    "COOLDOWN": "冷却中",
                    "BATTLE_EXIT": "战斗退出"
                }
                display_text = state_text_map.get(current_state, current_state)
                self._draw_text(display_text, self._state_x, self._state_y, (255, 255, 255, 255), 'large')

            # ── 提交 ──
            np.copyto(self._buffer, self._back_buffer)
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
