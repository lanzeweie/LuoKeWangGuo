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

import gc
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

        # 列出所有可用设备
        all_keyboards = []
        all_mice = []
        for device in range(1, 21):
            if lib.interception_is_keyboard(device):
                all_keyboards.append(device)
            if lib.interception_is_mouse(device):
                all_mice.append(device)

        if self.debug:
            self.logger.debug_msg(
                f"可用设备: keyboards={all_keyboards}, mice={all_mice}"
            )

        # 选择设备策略
        # 优先选择第一个实际设备（通常是正确的）
        # 如有需要，可通过 set_device_override() 覆盖
        self._keyboard_device = all_keyboards[0] if all_keyboards else None
        self._mouse_device = all_mice[0] if all_mice else None

        # 存储所有设备供调试
        self._all_keyboards = all_keyboards
        self._all_mice = all_mice

        if not self._keyboard_device:
            self.logger.warning("未找到键盘设备")
        if not self._mouse_device:
            self.logger.warning("未找到鼠标设备")

        if self.debug:
            self.logger.debug_msg(
                f"Interception 初始化成功: "
                f"keyboard={self._keyboard_device}, mouse={self._mouse_device}"
            )

    def auto_detect_hardware_mouse(self, timeout_seconds: float = 5.0) -> int:
        """
        动态捕获真实的物理鼠标设备号。
        原理：监听鼠标移动事件，第一个发来信号的设备就是真实的物理鼠标。

        Args:
            timeout_seconds: 等待用户移动鼠标的超时时间（秒）

        Returns:
            检测到的物理鼠标设备号

        Raises:
            RuntimeError: 超时未检测到鼠标移动
        """
        if not self._context:
            raise RuntimeError("Interception 未初始化")

        import threading
        import queue

        self.logger.info("\n" + "=" * 55)
        self.logger.warning(
            f" 嗅探模式启动：请在 {timeout_seconds:.1f} 秒内，用手稍微滑动一下你真实的鼠标..."
        )
        self.logger.info("=" * 55)

        result_queue = queue.Queue(maxsize=1)

        def monitor_thread() -> None:
            try:
                # 仅拦截鼠标的移动事件
                lib.interception_set_filter(
                    self._context,
                    lib.interception_is_mouse,
                    lib.INTERCEPTION_FILTER_MOUSE_MOVE,
                )

                # 阻塞等待硬件中断信号
                device = lib.interception_wait(self._context)

                # 接收并消费掉这个事件，防止积压
                stroke = ffi.new("InterceptionMouseStroke *")
                received = lib.interception_receive(self._context, device, stroke, 1)
                result_queue.put(device if received > 0 else None)
            except Exception:
                result_queue.put(None)
            finally:
                # 恢复默认过滤器（否则真实鼠标可能无法正常工作）
                try:
                    lib.interception_set_filter(self._context, lib.interception_is_mouse, 0)
                except Exception:
                    pass

        monitor = threading.Thread(target=monitor_thread, daemon=True)
        monitor.start()

        try:
            device = result_queue.get(timeout=timeout_seconds)
        except queue.Empty:
            raise RuntimeError(f"超时：未在 {timeout_seconds} 秒内检测到鼠标移动")

        if device is None:
            raise RuntimeError("动态捕获失败：未获取到有效鼠标事件")

        self.logger.success(f"动态捕获成功！已锁定真实物理鼠标设备号: [{device}]")

        # 将捕获到的设备号赋值给实例变量
        self._mouse_device = device
        return device

    def list_all_devices(self) -> dict:
        """列出所有可用输入设备（供调试用）。

        Returns:
            包含 keyboards 和 mice 列表的字典
        """
        if not INTERCEPTION_AVAILABLE:
            return {"keyboards": [], "mice": [], "error": "Interception 未安装"}

        if self._context is None:
            self._context = lib.interception_create_context()

        keyboards = []
        mice = []
        for device in range(1, 21):
            if lib.interception_is_keyboard(device):
                keyboards.append(device)
            if lib.interception_is_mouse(device):
                mice.append(device)

        return {"keyboards": keyboards, "mice": mice}

    def get_device_info(self, device: int) -> dict:
        """获取指定设备的硬件信息。

        Args:
            device: 设备号

        Returns:
            包含设备信息的字典
        """
        if not INTERCEPTION_AVAILABLE:
            return {"error": "Interception 未安装"}

        # 获取硬件 ID（设备唯一标识）
        hw_id_buf = ffi.new("unsigned char[256]")
        hw_id_size = lib.interception_get_hardware_id(self._context, device, hw_id_buf, 256)
        hw_id = ffi.buffer(hw_id_buf, hw_id_size)[:].hex().upper() if hw_id_size > 0 else "unknown"

        # 尝试判断是硬件还是虚拟设备
        is_keyboard = lib.interception_is_keyboard(device)
        is_mouse = lib.interception_is_mouse(device)

        return {
            "device": device,
            "hw_id": hw_id,
            "type": "keyboard" if is_keyboard else ("mouse" if is_mouse else "unknown"),
        }

    def set_device_override(self, keyboard: int = None, mouse: int = None) -> None:
        """覆盖默认设备选择（用于调试设备发送错误问题）。

        Args:
            keyboard: 强制使用的键盘设备号
            mouse: 强制使用的鼠标设备号
        """
        if keyboard is not None:
            if keyboard not in self._all_keyboards:
                self.logger.warning(
                    f"键盘设备 {keyboard} 不在可用列表中: {self._all_keyboards}"
                )
            self._keyboard_device = keyboard
            self.logger.info(f"已覆盖键盘设备: {keyboard}")

        if mouse is not None:
            if mouse not in self._all_mice:
                self.logger.warning(
                    f"鼠标设备 {mouse} 不在可用列表中: {self._all_mice}"
                )
            self._mouse_device = mouse
            self.logger.info(f"已覆盖鼠标设备: {mouse}")

    def __del__(self):
        """清理资源。"""
        if self._context and INTERCEPTION_AVAILABLE:
            lib.interception_destroy_context(self._context)
            self._context = None
            gc.collect()

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
        """相对移动（用于 3D 视角控制）。

        使用 1000Hz 级别的微步长与微秒级延迟，模拟高频鼠标输入。

        Args:
            rel_x: 相对 X 偏移
            rel_y: 相对 Y 偏移

        Returns:
            发送的事件数
        """
        if not getattr(self, "_mouse_device", None):
            raise RuntimeError("鼠标设备未就绪，请先执行硬件捕获")

        distance = math.sqrt(rel_x**2 + rel_y**2)
        if distance == 0:
            return 0

        # 步长极小（每次 1~3 像素），频率极高
        max_pixels_per_step = 2
        steps = max(10, int(distance / max_pixels_per_step))

        if self.debug:
            self.logger.debug_msg(
                f"Mouse: MOVE(rel) ({rel_x:+d},{rel_y:+d}), "
                f"distance={distance:.1f}px, steps={steps} (1000Hz 模式)"
            )

        total_sent = 0
        stroke = ffi.new("InterceptionMouseStroke *")  # 循环外创建，避免资源泄漏
        for i in range(1, steps + 1):
            ratio = i / steps
            target_dx = int(rel_x * ratio)
            target_dy = int(rel_y * ratio)

            prev_ratio = (i - 1) / steps if i > 1 else 0
            prev_dx = int(rel_x * prev_ratio)
            prev_dy = int(rel_y * prev_ratio)

            cur_dx = target_dx - prev_dx
            cur_dy = target_dy - prev_dy

            # 微颤机制：频率调低，防止画面反向抽搐
            if i % random.randint(15, 25) == 0:
                cur_dx += random.choice([-1, 0, 1])
                cur_dy += random.choice([-1, 0, 1])

            if cur_dx != 0 or cur_dy != 0:
                stroke.x = cur_dx
                stroke.y = cur_dy
                stroke.flags = 0  # 0 表示相对移动
                stroke.state = 0
                lib.interception_send(self._context, self._mouse_device, stroke, 1)
                total_sent += 1

            # 变速延迟：维持在 1ms ~ 3ms 之间
            speed = fitts_speed_profile(i / steps, distance)
            base_delay = 1 + (1 - speed) * 2
            time.sleep(base_delay / 1000.0)

            # 定期垃圾回收，防止 CFFI 对象累积耗尽资源
            if i % 50 == 0:
                gc.collect()

        # 移动结束后给一个短暂停顿，符合人类操作习惯
        time.sleep(random.uniform(0.02, 0.05))
        return total_sent

    def mouse_move_fast(self, rel_x: int, rel_y: int) -> int:
        """快速相对移动（用于大距离快速定位）。

        使用 10-15px 步长，比 mouse_move 快 5-10 倍。
        保留 Fitts's Law 变速和微颤机制。

        Args:
            rel_x: 相对 X 偏移
            rel_y: 相对 Y 偏移

        Returns:
            发送的事件数
        """
        if not getattr(self, "_mouse_device", None):
            raise RuntimeError("鼠标设备未就绪，请先执行硬件捕获")

        distance = math.sqrt(rel_x**2 + rel_y**2)
        if distance == 0:
            return 0

        # 大步长（10-15px），高频（0.5-1ms 延迟）
        max_pixels_per_step = 12
        steps = max(3, int(distance / max_pixels_per_step))

        if self.debug:
            self.logger.debug_msg(
                f"Mouse: MOVE_FAST(rel) ({rel_x:+d},{rel_y:+d}), "
                f"distance={distance:.1f}px, steps={steps} (快速模式)"
            )

        total_sent = 0
        stroke = ffi.new("InterceptionMouseStroke *")
        for i in range(1, steps + 1):
            ratio = i / steps
            target_dx = int(rel_x * ratio)
            target_dy = int(rel_y * ratio)

            prev_ratio = (i - 1) / steps if i > 1 else 0
            prev_dx = int(rel_x * prev_ratio)
            prev_dy = int(rel_y * prev_ratio)

            cur_dx = target_dx - prev_dx
            cur_dy = target_dy - prev_dy

            # 微颤：每 10-15 步一次 +/-1px
            if i % random.randint(10, 15) == 0:
                cur_dx += random.choice([-1, 0, 1])
                cur_dy += random.choice([-1, 0, 1])

            if cur_dx != 0 or cur_dy != 0:
                stroke.x = cur_dx
                stroke.y = cur_dy
                stroke.flags = 0
                stroke.state = 0
                lib.interception_send(self._context, self._mouse_device, stroke, 1)
                total_sent += 1

            # 变速延迟：0.5ms ~ 1ms
            speed = fitts_speed_profile(i / steps, distance)
            base_delay = 0.5 + (1 - speed) * 0.5
            time.sleep(base_delay / 1000.0)

            if i % 50 == 0:
                gc.collect()

        # 短暂停顿
        time.sleep(random.uniform(0.01, 0.02))
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
        stroke = ffi.new("InterceptionMouseStroke *")  # 循环外创建，避免资源泄漏

        for i, point in enumerate(path[1:], 1):
            # 计算相对移动量
            dx = int(point.x - prev_point.x)
            dy = int(point.y - prev_point.y)

            # 微颤模拟（每 5-10 步插入 1-2px 抖动）
            if i % random.randint(5, 10) == 0:
                dx += random.randint(-2, 2)
                dy += random.randint(-2, 2)

            if dx != 0 or dy != 0:
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
        stroke = ffi.new("InterceptionMouseStroke *")  # 循环外创建

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
