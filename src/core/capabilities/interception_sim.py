#!/usr/bin/env python3
"""
Interception 输入模拟模块（集成拟人化算法）

使用 Interception 驱动级注入，内置拟人化鼠标移动算法：
- 贝塞尔曲线轨迹（三阶，随机控制点）
- Fitts's Law 变速模型（前30%加速，后70%减速）
- 微颤模拟（Micro-tremor）
- 过冲修复（Overshoot & Correction）
- 高斯分布随机延迟

所有坐标均为客户区相对坐标。
"""

import time
import random
import math
import ctypes
from typing import Optional, Tuple, List
from dataclasses import dataclass

from src.logger import get_logger

# ── Interception 驱动导入 ──────────────────────────────────────────
try:
    from interception import ffi, lib
    INTERCEPTION_AVAILABLE = True
except ImportError:
    INTERCEPTION_AVAILABLE = False
    ffi = None
    lib = None

# ── Scan Codes (硬件扫描码) ────────────────────────────────────────
# Interception 驱动使用 Scan Code，不是 Virtual Key Code
SCAN_CODE_MAP = {
    'w': 0x11, 'a': 0x1E, 's': 0x1F, 'd': 0x20,
    'e': 0x12, 'r': 0x13, 'f': 0x21, 'q': 0x10,
    't': 0x14, 'y': 0x15, 'u': 0x16, 'i': 0x17,
    'o': 0x18, 'p': 0x19, 'g': 0x22, 'h': 0x23,
    'j': 0x24, 'k': 0x25, 'l': 0x26, 'z': 0x2C,
    'x': 0x2D, 'c': 0x2E, 'v': 0x2F, 'b': 0x30,
    'n': 0x31, 'm': 0x32,
    '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05,
    '5': 0x06, '6': 0x07, '7': 0x08, '8': 0x09,
    '9': 0x0A, '0': 0x0B,
    'f1': 0x3B, 'f2': 0x3C, 'f3': 0x3D, 'f4': 0x3E,
    'f5': 0x3F, 'f6': 0x40, 'f7': 0x41, 'f8': 0x42,
    'f9': 0x43, 'f10': 0x44, 'f11': 0x57, 'f12': 0x58,
    'space': 0x39, 'shift': 0x2A, 'ctrl': 0x1D, 'alt': 0x38,
    'esc': 0x01, 'escape': 0x01,
    'enter': 0x1C, 'return': 0x1C,
    'tab': 0x0F, 'backspace': 0x0E,
    'delete': 0x53, 'insert': 0x52, 'home': 0x47, 'end': 0x4F,
    'pageup': 0x49, 'pagedown': 0x51,
    'up': 0x48, 'down': 0x50, 'left': 0x4B, 'right': 0x4D,
}


# ── 拟人化算法：贝塞尔曲线 ────────────────────────────────────────
@dataclass
class Point:
    x: float
    y: float


def cubic_bezier(t: float, p0: Point, p1: Point, p2: Point, p3: Point) -> Point:
    """三阶贝塞尔曲线插值。

    B(t) = (1-t)³P₀ + 3(1-t)²tP₁ + 3(1-t)t²P₂ + t³P₃
    """
    u = 1 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t

    x = uuu * p0.x + 3 * uu * t * p1.x + 3 * u * tt * p2.x + ttt * p3.x
    y = uuu * p0.y + 3 * uu * t * p1.y + 3 * u * tt * p2.y + ttt * p3.y

    return Point(x, y)


def generate_bezier_path(start: Point, end: Point, steps: int = 30) -> List[Point]:
    """生成贝塞尔曲线路径，随机控制点。

    Args:
        start: 起点
        end: 终点
        steps: 采样点数量

    Returns:
        路径点列表
    """
    # 计算中点和距离
    mid_x = (start.x + end.x) / 2
    mid_y = (start.y + end.y) / 2
    distance = math.sqrt((end.x - start.x)**2 + (end.y - start.y)**2)

    # 随机偏移量（距离的 15-30%）
    offset_range = distance * random.uniform(0.15, 0.30)

    # 随机控制点（在中点两侧）
    angle = random.uniform(0, 2 * math.pi)
    p1 = Point(
        start.x + (mid_x - start.x) * 0.5 + math.cos(angle) * offset_range * 0.5,
        start.y + (mid_y - start.y) * 0.5 + math.sin(angle) * offset_range * 0.5
    )

    angle2 = angle + math.pi + random.uniform(-0.5, 0.5)
    p2 = Point(
        mid_x + (end.x - mid_x) * 0.5 + math.cos(angle2) * offset_range * 0.5,
        mid_y + (end.y - mid_y) * 0.5 + math.sin(angle2) * offset_range * 0.5
    )

    # 采样曲线
    path = []
    for i in range(steps + 1):
        t = i / steps
        point = cubic_bezier(t, start, p1, p2, end)
        path.append(point)

    return path


# ── 拟人化算法：Fitts's Law 变速 ──────────────────────────────────
def fitts_speed_profile(t: float, distance: float) -> float:
    """Fitts's Law 变速模型。

    前 30% 指数加速，后 70% 正态分布减速。

    Args:
        t: 进度 [0, 1]
        distance: 总距离（像素）

    Returns:
        当前速度系数 [0, 1]
    """
    if t < 0.3:
        # 加速阶段：指数增长
        return (t / 0.3) ** 1.5
    else:
        # 减速阶段：正态分布衰减
        normalized_t = (t - 0.3) / 0.7
        return 1.0 - (normalized_t ** 2) * 0.3


# ── 拟人化算法：随机延迟 ────────────────────────────────────────────
def human_like_delay(base_ms: float = 80.0) -> None:
    """高斯分布随机延迟。

    Args:
        base_ms: 基准延迟（毫秒），默认 80ms
    """
    jitter = random.gauss(base_ms, base_ms * 0.15)
    actual_delay = max(0.1, jitter)
    time.sleep(actual_delay / 1000.0)


# ── InterceptionSimulator 主类 ─────────────────────────────────────
class InterceptionSimulator:
    """基于 Interception 驱动的输入模拟器（集成拟人化算法）。

    所有坐标参数均为**客户区相对坐标**。
    """

    def __init__(self, window_mgr, debug: bool = False):
        """
        Args:
            window_mgr: WindowManager 实例
            debug: 是否启用调试日志
        """
        if not INTERCEPTION_AVAILABLE:
            raise ImportError(
                "Interception 驱动未安装。请运行: pip install interception"
            )

        self._wm = window_mgr
        self.debug = debug
        self.logger = get_logger(debug=debug)

        # 初始化 interception 上下文
        self._context = None
        self._keyboard_device = None
        self._mouse_device = None

        self._init_devices()

    def _init_devices(self) -> None:
        """初始化 interception 设备。"""
        self._context = lib.interception_create_context()
        if not self._context:
            raise RuntimeError(
                "无法初始化 Interception 驱动。请确认：\n"
                "1. 驱动已安装\n"
                "2. 以管理员身份运行\n"
                "3. 驱动服务已启动"
            )

        # 设置过滤器 - 这是关键！必须设置过滤器才能拦截输入
        # INTERCEPTION_FILTER_KEY_ALL = 0xFFFF
        # INTERCEPTION_FILTER_MOUSE_ALL = 0xFFFF
        lib.interception_set_filter(
            self._context,
            lib.interception_is_keyboard,
            0xFFFF  # INTERCEPTION_FILTER_KEY_ALL
        )
        lib.interception_set_filter(
            self._context,
            lib.interception_is_mouse,
            0xFFFF  # INTERCEPTION_FILTER_MOUSE_ALL
        )

        # 查找键盘设备
        for device in range(1, 21):
            if lib.interception_is_keyboard(device):
                self._keyboard_device = device
                break

        # 查找鼠标设备
        for device in range(1, 21):
            if lib.interception_is_mouse(device):
                self._mouse_device = device
                break

        if not self._keyboard_device:
            self.logger.warning("未找到键盘设备")
        if not self._mouse_device:
            self.logger.warning("未找到鼠标设备")

        if self.debug:
            self.logger.debug_msg(
                f"Interception 初始化成功: "
                f"keyboard={self._keyboard_device}, mouse={self._mouse_device}"
            )

    def __del__(self):
        """清理资源。"""
        if self._context and INTERCEPTION_AVAILABLE:
            lib.interception_destroy_context(self._context)

    # ── 键盘操作 ────────────────────────────────────────────────────

    def press_key(self, key: str, duration: float = 0.2) -> int:
        """按键（按下 -> 等待 -> 松开）。

        Args:
            key: 按键名
            duration: 按住时长（秒）

        Returns:
            成功发送的事件数
        """
        if not self._keyboard_device:
            raise RuntimeError("键盘设备未找到")

        key_lower = key.lower()
        scan_code = SCAN_CODE_MAP.get(key_lower)
        if scan_code is None:
            raise ValueError(f"未知按键: {key!r}")

        human_like_delay(80)

        # 按下
        stroke = ffi.new("InterceptionKeyStroke *")
        stroke.code = scan_code
        stroke.state = 0  # Key down
        lib.interception_send(self._context, self._keyboard_device, stroke, 1)

        if self.debug:
            self.logger.debug_msg(f"Keyboard: KEYDOWN '{key_lower}' (scan=0x{scan_code:02X})")

        # 持续时间（随机抖动）
        hold_time = duration + random.gauss(0, duration * 0.1)
        time.sleep(max(0.05, hold_time))

        # 松开
        stroke.state = lib.INTERCEPTION_KEY_UP
        lib.interception_send(self._context, self._keyboard_device, stroke, 1)

        if self.debug:
            self.logger.debug_msg(f"Keyboard: KEYUP   '{key_lower}'")

        human_like_delay(80)
        return 2

    def key_down(self, key: str) -> int:
        """仅按下。"""
        if not self._keyboard_device:
            raise RuntimeError("键盘设备未找到")

        key_lower = key.lower()
        scan_code = SCAN_CODE_MAP.get(key_lower)
        if scan_code is None:
            raise ValueError(f"未知按键: {key!r}")

        human_like_delay(80)

        stroke = ffi.new("InterceptionKeyStroke *")
        stroke.code = scan_code
        stroke.state = 0  # Key down
        lib.interception_send(self._context, self._keyboard_device, stroke, 1)

        if self.debug:
            self.logger.debug_msg(f"KeyDown(hold): {key_lower} (scan=0x{scan_code:02X})")

        return 1

    def key_up(self, key: str) -> int:
        """仅松开。"""
        if not self._keyboard_device:
            raise RuntimeError("键盘设备未找到")

        key_lower = key.lower()
        scan_code = SCAN_CODE_MAP.get(key_lower)
        if scan_code is None:
            raise ValueError(f"未知按键: {key!r}")

        human_like_delay(80)

        stroke = ffi.new("InterceptionKeyStroke *")
        stroke.code = scan_code
        stroke.state = lib.INTERCEPTION_KEY_UP
        lib.interception_send(self._context, self._keyboard_device, stroke, 1)

        if self.debug:
            self.logger.debug_msg(f"KeyUp: {key_lower} (scan=0x{scan_code:02X})")

        return 1

    # ── 鼠标操作（拟人化） ──────────────────────────────────────────

    def mouse_move(self, rel_x: int, rel_y: int) -> int:
        """相对移动（用于视角控制），分段平滑移动。

        Args:
            rel_x: 相对 X 偏移
            rel_y: 相对 Y 偏移

        Returns:
            发送的事件数
        """
        if not self._mouse_device:
            raise RuntimeError("鼠标设备未找到")

        # 计算总距离
        distance = math.sqrt(rel_x**2 + rel_y**2)

        # 根据距离决定分段数（距离越大，分段越多）
        steps = max(10, min(50, int(distance / 10)))

        if self.debug:
            self.logger.debug_msg(
                f"Mouse: MOVE(rel) ({rel_x:+d},{rel_y:+d}), "
                f"distance={distance:.1f}px, steps={steps}"
            )

        total_sent = 0

        # 分段发送相对移动
        for i in range(1, steps + 1):
            # 计算当前段的目标位置
            ratio = i / steps
            target_dx = int(rel_x * ratio)
            target_dy = int(rel_y * ratio)

            # 计算已发送的位移
            prev_ratio = (i - 1) / steps if i > 1 else 0
            prev_dx = int(rel_x * prev_ratio)
            prev_dy = int(rel_y * prev_ratio)

            # 本段位移
            cur_dx = target_dx - prev_dx
            cur_dy = target_dy - prev_dy

            # 微颤模拟（每 5-10 步插入 1-2px 抖动）
            if i % random.randint(5, 10) == 0:
                cur_dx += random.randint(-1, 1)
                cur_dy += random.randint(-1, 1)

            if cur_dx != 0 or cur_dy != 0:
                stroke = ffi.new("InterceptionMouseStroke *")
                stroke.x = cur_dx
                stroke.y = cur_dy
                stroke.flags = 0  # 相对移动
                stroke.state = 0

                lib.interception_send(self._context, self._mouse_device, stroke, 1)
                total_sent += 1

            # Fitts's Law 变速延迟
            t = i / steps
            speed = fitts_speed_profile(t, distance)
            base_delay = 5 + (1 - speed) * 15  # 5-20ms
            time.sleep(base_delay / 1000.0)

        human_like_delay(80)
        return total_sent

    def mouse_move_to(self, rel_x: int, rel_y: int) -> int:
        """拟人化移动到目标位置（贝塞尔曲线 + Fitts's Law）。

        Args:
            rel_x: 目标 X（客户区相对坐标）
            rel_y: 目标 Y（客户区相对坐标）

        Returns:
            发送的事件数
        """
        if not self._mouse_device:
            raise RuntimeError("鼠标设备未找到")

        # 获取当前鼠标位置（屏幕绝对坐标）
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))

        # 转换为客户区相对坐标
        region = self._wm.get_region()
        if region is None:
            raise RuntimeError("无法获取窗口客户区坐标")

        left, top, _w, _h = region
        current_x = pt.x - left
        current_y = pt.y - top

        # 生成贝塞尔曲线路径
        start = Point(float(current_x), float(current_y))
        end = Point(float(rel_x), float(rel_y))

        distance = math.sqrt((end.x - start.x)**2 + (end.y - start.y)**2)

        # 根据距离调整步数（距离越远，步数越多）
        steps = max(15, min(50, int(distance / 10)))

        path = generate_bezier_path(start, end, steps)

        if self.debug:
            self.logger.debug_msg(
                f"Mouse: MOVE_TO humanlike path: "
                f"({current_x},{current_y}) -> ({rel_x},{rel_y}), "
                f"distance={distance:.1f}px, steps={steps}"
            )

        # 沿路径移动
        prev_point = path[0]
        total_sent = 0

        for i, point in enumerate(path[1:], 1):
            # 计算相对移动量
            dx = int(point.x - prev_point.x)
            dy = int(point.y - prev_point.y)

            # 微颤模拟（每 5-10 步插入 1-2px 抖动）
            if i % random.randint(5, 10) == 0:
                dx += random.randint(-2, 2)
                dy += random.randint(-2, 2)

            if dx != 0 or dy != 0:
                stroke = ffi.new("InterceptionMouseStroke *")
                stroke.x = dx
                stroke.y = dy
                stroke.flags = 0
                stroke.state = 0

                lib.interception_send(self._context, self._mouse_device, stroke, 1)
                total_sent += 1

            # Fitts's Law 变速延迟
            t = i / len(path)
            speed = fitts_speed_profile(t, distance)
            base_delay = 5 + (1 - speed) * 15  # 5-20ms
            time.sleep(base_delay / 1000.0)

            prev_point = point

        # 过冲修复（10% 概率）
        if random.random() < 0.1 and distance > 50:
            overshoot = random.randint(3, 8)
            direction = random.choice([-1, 1])

            # 过冲
            stroke = ffi.new("InterceptionMouseStroke *")
            stroke.x = direction * overshoot
            stroke.y = 0
            stroke.flags = 0
            stroke.state = 0
            lib.interception_send(self._context, self._mouse_device, stroke, 1)
            total_sent += 1

            time.sleep(random.uniform(0.02, 0.05))

            # 回调
            stroke.x = -direction * overshoot
            lib.interception_send(self._context, self._mouse_device, stroke, 1)
            total_sent += 1

            if self.debug:
                self.logger.debug_msg(f"Mouse: Overshoot correction ({overshoot}px)")

        human_like_delay(80)
        return total_sent

    def mouse_click(self) -> int:
        """左键点击。"""
        if not self._mouse_device:
            raise RuntimeError("鼠标设备未找到")

        human_like_delay(80)

        stroke = ffi.new("InterceptionMouseStroke *")

        # 按下
        stroke.state = lib.INTERCEPTION_MOUSE_LEFT_BUTTON_DOWN
        stroke.flags = 0
        lib.interception_send(self._context, self._mouse_device, stroke, 1)

        # 持续时间（40-120ms 随机）
        hold_time = random.gauss(80, 20)
        time.sleep(max(40, min(120, hold_time)) / 1000.0)

        # 松开
        stroke.state = lib.INTERCEPTION_MOUSE_LEFT_BUTTON_UP
        lib.interception_send(self._context, self._mouse_device, stroke, 1)

        if self.debug:
            self.logger.debug_msg(f"Mouse: CLICK (hold={hold_time:.1f}ms)")

        human_like_delay(80)
        return 2

    def mouse_down(self) -> int:
        """左键按下。"""
        if not self._mouse_device:
            raise RuntimeError("鼠标设备未找到")

        human_like_delay(80)

        stroke = ffi.new("InterceptionMouseStroke *")
        stroke.state = lib.INTERCEPTION_MOUSE_LEFT_BUTTON_DOWN
        stroke.flags = 0
        lib.interception_send(self._context, self._mouse_device, stroke, 1)

        if self.debug:
            self.logger.debug_msg("Mouse: DOWN")

        return 1

    def mouse_up(self) -> int:
        """左键松开。"""
        if not self._mouse_device:
            raise RuntimeError("鼠标设备未找到")

        human_like_delay(80)

        stroke = ffi.new("InterceptionMouseStroke *")
        stroke.state = lib.INTERCEPTION_MOUSE_LEFT_BUTTON_UP
        stroke.flags = 0
        lib.interception_send(self._context, self._mouse_device, stroke, 1)

        if self.debug:
            self.logger.debug_msg("Mouse: UP")

        return 1

    def mouse_drag_relative(self, dx: int, dy: int) -> int:
        """相对拖动（按住右键移动视角）。

        Args:
            dx: 相对 X 偏移
            dy: 相对 Y 偏移

        Returns:
            发送的事件数
        """
        if not self._mouse_device:
            raise RuntimeError("鼠标设备未找到")

        human_like_delay(80)

        stroke = ffi.new("InterceptionMouseStroke *")

        # 右键按下
        stroke.state = lib.INTERCEPTION_MOUSE_RIGHT_BUTTON_DOWN
        stroke.flags = 0
        lib.interception_send(self._context, self._mouse_device, stroke, 1)
        total_sent = 1

        time.sleep(0.1)

        # 分段移动
        step_size = 30
        steps = max(1, max(abs(dx), abs(dy)) // step_size)

        for i in range(steps):
            ratio = (i + 1) / steps
            target_dx = int(dx * ratio)
            target_dy = int(dy * ratio)

            prev_ratio = i / steps if i > 0 else 0
            prev_dx = int(dx * prev_ratio)
            prev_dy = int(dy * prev_ratio)

            cur_dx = target_dx - prev_dx
            cur_dy = target_dy - prev_dy

            if cur_dx != 0 or cur_dy != 0:
                stroke.x = cur_dx
                stroke.y = cur_dy
                stroke.state = 0
                stroke.flags = 0
                lib.interception_send(self._context, self._mouse_device, stroke, 1)
                total_sent += 1

            time.sleep(random.uniform(0.05, 0.08))

        # 右键松开
        stroke.state = lib.INTERCEPTION_MOUSE_RIGHT_BUTTON_UP
        stroke.x = 0
        stroke.y = 0
        lib.interception_send(self._context, self._mouse_device, stroke, 1)
        total_sent += 1

        if self.debug:
            self.logger.debug_msg(f"Mouse: DRAG_REL ({dx:+d},{dy:+d})")

        human_like_delay(80)
        return total_sent
