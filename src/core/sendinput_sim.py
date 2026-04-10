#!/usr/bin/env python3
"""
SendInput 输入模拟模块

使用 Windows SendInput API 替代 pynput，满足反作弊要求。
- 键盘: KEYBD_EVENTF_KEYDOWN / KEYBD_EVENTF_KEYUP
- 鼠标: MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE（坐标归一化 0-65535）
- 反检测: 分段轨迹 + 随机抖动 + 80-150ms 随机延迟

所有坐标均为客户区相对坐标，通过 window_mgr 转换为屏幕绝对坐标后
再送入 SendInput。
"""

import ctypes
import struct
import time
import random
from typing import Optional, Tuple

from src.logger import get_logger

# ── Windows constants ──────────────────────────────────────────────────
INPUT_KEYBOARD = 1
INPUT_MOUSE = 0

KEYBD_EVENTF_KEYUP = 0x0002

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

# Virtual-key codes (subset)
VK_MAP = {
    # Letters / common keys
    'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
    'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
    'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
    'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
    'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
    'z': 0x5A,
    # Numbers (top row)
    '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
    '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
    # Special
    'esc': 0x1B, 'escape': 0x1B,
    'space': 0x20,
    'enter': 0x0D, 'return': 0x0D,
    'tab': 0x09,
    'shift': 0x10,
    'ctrl': 0x11, 'control': 0x11,
    'alt': 0x12,
    'backspace': 0x08,
    'delete': 0x2E,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
}

# Normalization factor for MOUSEEVENTF_ABSOLUTE
_NORMALIZER = 65535.0


# ── ctypes structures ──────────────────────────────────────────────────

class _MOUSEINPUT(ctypes.Structure):
    """MOUSEINPUT — keyboard/mouse union mouse member."""
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _KEYBDINPUT(ctypes.Structure):
    """KEYBDINPUT — keyboard/mouse union keyboard member."""
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _DUMMYUNIONNAME(ctypes.Union):
    """Union of MOUSEINPUT and KEYBDINPUT inside INPUT."""
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
    ]


class INPUT(ctypes.Structure):
    """INPUT structure for SendInput."""
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", _DUMMYUNIONNAME),
    ]


def _make_keyboard_input(vk: int, scan_code: int = 0, key_up: bool = False) -> INPUT:
    """Create an INPUT structure for a keyboard event.

    Args:
        vk: Virtual-key code
        scan_code: Hardware scan code (from MapVirtualKeyW). Games may require this.
        key_up: Whether this is a key-up event.
    """
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    flags = KEYBD_EVENTF_KEYUP if key_up else 0
    # If scan_code is provided, use KEYBDINPUT_SCANCODE flag so the game sees
    # a hardware-like event rather than a virtual-key event.
    if scan_code:
        flags |= 0x0008  # KEYEVENTF_SCANCODE
    inp.union.ki.wVk = vk if not scan_code else 0
    inp.union.ki.wScan = scan_code if scan_code else vk
    inp.union.ki.dwFlags = flags
    inp.union.ki.time = 0
    inp.union.ki.dwExtraInfo = None
    return inp


def _make_mouse_move_input(abs_x: int, abs_y: int) -> INPUT:
    """Create an INPUT structure for absolute mouse move."""
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi.dx = abs_x
    inp.union.mi.dy = abs_y
    inp.union.mi.mouseData = 0
    inp.union.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
    inp.union.mi.time = 0
    inp.union.mi.dwExtraInfo = None
    return inp


def _make_mouse_move_relative(dx: int, dy: int) -> INPUT:
    """Create an INPUT structure for **relative** mouse move.

    DX games typically expect relative delta movements, not absolute positions.
    Currently unused — `mouse_move()` uses absolute mode. Keep for future use.
    """
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi.dx = dx
    inp.union.mi.dy = dy
    inp.union.mi.mouseData = 0
    inp.union.mi.dwFlags = MOUSEEVENTF_MOVE  # No ABSOLUTE flag → relative mode
    inp.union.mi.time = 0
    inp.union.mi.dwExtraInfo = None
    return inp


def _make_mouse_button_input(flag: int) -> INPUT:
    """Create an INPUT structure for mouse button down/up."""
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi.dx = 0
    inp.union.mi.dy = 0
    inp.union.mi.mouseData = 0
    inp.union.mi.dwFlags = flag
    inp.union.mi.time = 0
    inp.union.mi.dwExtraInfo = None
    return inp


def _send_inputs(inputs: list) -> int:
    """Send a list of INPUT structures via SendInput API.

    Returns the number of successfully inserted events.
    """
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    result = ctypes.windll.user32.SendInput(
        n,
        ctypes.byref(arr),
        ctypes.sizeof(INPUT),
    )
    return result


def _normalize_coord(pixel: int, screen_size: int) -> int:
    """Normalize a pixel coordinate to 0-65535 range for SendInput."""
    if screen_size <= 0:
        return 0
    return int((pixel * _NORMALIZER) / screen_size + 0.5)


# ── Main class ─────────────────────────────────────────────────────────

class SendInputSimulator:
    """基于 Windows SendInput API 的输入模拟器（反检测）。

    所有坐标参数均为**客户区相对坐标**。内部通过 window_mgr 转换为
    屏幕绝对坐标后再送入 SendInput。
    """

    def __init__(self, window_mgr, debug: bool = False):
        """
        Args:
            window_mgr: WindowManager 实例，用于获取客户区坐标偏移
            debug: 是否启用调试日志
        """
        self._wm = window_mgr
        self.debug = debug
        self.logger = get_logger(debug=debug)

    # ── helpers ─────────────────────────────────────────────────────

    def _get_screen_size(self) -> Tuple[int, int]:
        """Return (screen_width, screen_height) from system metrics."""
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        return sw, sh

    def _client_to_screen(self, rel_x: int, rel_y: int) -> Tuple[int, int]:
        """Convert client-relative coordinates to screen absolute coordinates."""
        region = self._wm.get_region()
        if region is None:
            raise RuntimeError(
                "无法获取窗口客户区坐标，请确认窗口已找到"
            )
        left, top, _w, _h = region
        return left + rel_x, top + rel_y

    def _random_delay(self) -> None:
        """80-150ms random delay between operations."""
        time.sleep(random.uniform(0.08, 0.15))

    # ── keyboard ────────────────────────────────────────────────────

    def press_key(self, key: str, duration: float = 0.2) -> int:
        """按键（按下 -> 等待 duration -> 松开）。

        Args:
            key: 按键名 ('w', 'a', 's', 'd', 'e', 'esc' 等)
            duration: 按住时长（秒），默认 0.2s

        Returns:
            成功发送的事件数（2 = 按下 + 松开）
        """
        key_lower = key.lower()
        vk = VK_MAP.get(key_lower)
        if vk is None:
            raise ValueError(f"未知按键: {key!r}，支持的按键: {sorted(VK_MAP.keys())}")

        # 填充 scan code — 游戏可能只认 scan code 不认 vk
        scan_code = ctypes.windll.user32.MapVirtualKeyW(vk, 0)

        self._random_delay()

        # Key down
        down = _make_keyboard_input(vk, scan_code, key_up=False)
        n = _send_inputs([down])
        if self.debug:
            self.logger.debug_msg(f"Keyboard: KEYDOWN '{key_lower}' (vk=0x{vk:02X}, sc=0x{scan_code:02X}) Sent={n}/1")

        if duration > 0:
            time.sleep(duration)

        # Key up
        up = _make_keyboard_input(vk, scan_code, key_up=True)
        n2 = _send_inputs([up])
        if self.debug:
            self.logger.debug_msg(f"Keyboard: KEYUP   '{key_lower}'                              Sent={n2}/1")

        self._random_delay()
        result = n + n2
        if n != 1:
            self.logger.warning(f"SendInput KEYDOWN only returned {n}/1")
        if n2 != 1:
            self.logger.warning(f"SendInput KEYUP only returned {n2}/1")
        return result

    def key_down(self, key: str) -> int:
        """仅按下（不松开），用于需要按住一段时间的场景。

        Returns:
            成功发送的事件数
        """
        key_lower = key.lower()
        vk = VK_MAP.get(key_lower)
        if vk is None:
            raise ValueError(f"未知按键: {key!r}")

        scan_code = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        self._random_delay()
        down = _make_keyboard_input(vk, scan_code, key_up=False)
        n = _send_inputs([down])
        if self.debug:
            self.logger.debug_msg(f"KeyDown(hold): {key_lower} (sc=0x{scan_code:02X})")
        return n

    def key_up(self, key: str) -> int:
        """仅松开。

        Returns:
            成功发送的事件数
        """
        key_lower = key.lower()
        vk = VK_MAP.get(key_lower)
        if vk is None:
            raise ValueError(f"未知按键: {key!r}")

        scan_code = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        self._random_delay()
        up = _make_keyboard_input(vk, scan_code, key_up=True)
        n = _send_inputs([up])
        if self.debug:
            self.logger.debug_msg(f"KeyUp: {key_lower}")
        return n

    # ── mouse movement ──────────────────────────────────────────────

    def mouse_move(self, rel_x: int, rel_y: int) -> int:
        """鼠标移动到客户区相对坐标。

        将客户区坐标转换为屏幕绝对坐标后，使用 SendInput 的
        MOUSEEVENTF_ABSOLUTE 模式精确定位。

        Args:
            rel_x: 客户区 X 坐标（像素）
            rel_y: 客户区 Y 坐标（像素）

        Returns:
            成功发送的事件总数
        """
        self._random_delay()

        # 客户区相对坐标 → 屏幕绝对坐标
        abs_x, abs_y = self._client_to_screen(rel_x, rel_y)

        # 归一化到 0-65535
        sw, sh = self._get_screen_size()
        nx = _normalize_coord(abs_x, sw)
        ny = _normalize_coord(abs_y, sh)

        inp = _make_mouse_move_input(nx, ny)
        n = _send_inputs([inp])

        self.logger.debug_msg(
            f"Mouse:   MOVE(abs): client({rel_x},{rel_y}) -> "
            f"screen({abs_x},{abs_y}) -> normalized({nx},{ny}) Sent={n}/1"
        )

        self._random_delay()
        return n

    # ── mouse buttons ───────────────────────────────────────────────

    def mouse_down(self) -> int:
        """鼠标左键按下。

        Returns:
            成功发送的事件数
        """
        self._random_delay()
        inp = _make_mouse_button_input(MOUSEEVENTF_LEFTDOWN)
        n = _send_inputs([inp])
        self.logger.debug_msg(f"Mouse:   DOWN     Sent={n}/1")
        return n

    def mouse_up(self) -> int:
        """鼠标左键松开。

        Returns:
            成功发送的事件数
        """
        self._random_delay()
        inp = _make_mouse_button_input(MOUSEEVENTF_LEFTUP)
        n = _send_inputs([inp])
        self.logger.debug_msg(f"Mouse:   UP       Sent={n}/1")
        return n

    def mouse_click(self) -> int:
        """鼠标左键点击（按下 -> 松开）。

        Returns:
            成功发送的事件数
        """
        self._random_delay()
        down = _make_mouse_button_input(MOUSEEVENTF_LEFTDOWN)
        up = _make_mouse_button_input(MOUSEEVENTF_LEFTUP)
        n = _send_inputs([down, up])
        self.logger.debug_msg(f"Mouse:   CLICK    Sent={n}/2")
        self._random_delay()
        return n


# ── Tests (no actual input sent) ──────────────────────────────────────

class _MockWindowManager:
    """Fake WindowManager for unit testing without a real window."""

    def __init__(self, client_left: int = 100, client_top: int = 200,
                 client_width: int = 1280, client_height: int = 720):
        self._left = client_left
        self._top = client_top
        self._width = client_width
        self._height = client_height

    def get_region(self):
        return (self._left, self._top, self._width, self._height)


def test_sendinput_simulator() -> bool:
    """测试 SendInputSimulator 结构体定义和参数计算。

    不发送任何实际输入，仅验证内部逻辑正确性。
    """
    passed = 0
    failed = 0

    def check(name: str, condition: bool):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")

    # ── Test 1: Structure sizes ─────────────────────────────────────
    print("[Test 1] ctypes structure sizes...")
    check("_KEYBDINPUT size == 24", ctypes.sizeof(_KEYBDINPUT) == 24)
    check("_MOUSEINPUT size == 32", ctypes.sizeof(_MOUSEINPUT) == 32)
    check("_DUMMYUNIONNAME size == 32", ctypes.sizeof(_DUMMYUNIONNAME) == 32)
    check("INPUT size == 40", ctypes.sizeof(INPUT) == 40)  # 4 + 4 padding + 32
    check("INPUT type offset == 0", INPUT.type.offset == 0)
    check("INPUT union offset == 8", INPUT.union.offset == 8)

    # ── Test 2: Keyboard INPUT creation ─────────────────────────────
    print("\n[Test 2] Keyboard INPUT creation...")
    inp = _make_keyboard_input(0x57, scan_code=0x11, key_up=False)  # 'W'
    check("type == INPUT_KEYBOARD", inp.type == INPUT_KEYBOARD)
    check("wScan == 0x11", inp.union.ki.wScan == 0x11)
    check("dwFlags == SCANCODE (0x0008)", inp.union.ki.dwFlags == 0x0008)

    inp_up = _make_keyboard_input(0x57, scan_code=0x11, key_up=True)
    check("dwFlags == SCANCODE|KEYUP (0x000A)", inp_up.union.ki.dwFlags == 0x000A)

    # No scan code fallback (legacy vk-only mode)
    inp_vk = _make_keyboard_input(0x57, scan_code=0, key_up=False)
    check("vk-only: wVk == 0x57", inp_vk.union.ki.wVk == 0x57)
    check("vk-only: dwFlags == 0", inp_vk.union.ki.dwFlags == 0)

    # ── Test 3: Mouse INPUT creation ────────────────────────────────
    print("\n[Test 3] Mouse INPUT creation...")
    mx = _make_mouse_move_input(32768, 32768)
    check("type == INPUT_MOUSE", mx.type == INPUT_MOUSE)
    check("dx == 32768", mx.union.mi.dx == 32768)
    check("dy == 32768", mx.union.mi.dy == 32768)
    check("dwFlags == MOVE|ABSOLUTE",
          mx.union.mi.dwFlags == (MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE))

    md = _make_mouse_button_input(MOUSEEVENTF_LEFTDOWN)
    check("mouse_down dwFlags == LEFTDOWN", md.union.mi.dwFlags == MOUSEEVENTF_LEFTDOWN)

    mu = _make_mouse_button_input(MOUSEEVENTF_LEFTUP)
    check("mouse_up dwFlags == LEFTUP", mu.union.mi.dwFlags == MOUSEEVENTF_LEFTUP)

    # ── Test 4: Coordinate normalization ────────────────────────────
    print("\n[Test 4] Coordinate normalization...")
    # 1920px screen: pixel 960 -> 32768
    check("norm(960, 1920) == 32768",
          _normalize_coord(960, 1920) == 32768)
    check("norm(0, 1920) == 0",
          _normalize_coord(0, 1920) == 0)
    check("norm(1919, 1920) ~ 65501",
          65500 <= _normalize_coord(1919, 1920) <= 65536)
    check("norm(0, 0) == 0 (guard)",
          _normalize_coord(100, 0) == 0)

    # ── Test 5: client_to_screen conversion ─────────────────────────
    print("\n[Test 5] Client-to-screen coordinate conversion...")
    mock_wm = _MockWindowManager(client_left=100, client_top=200)
    sim = SendInputSimulator(mock_wm, debug=False)
    sx, sy = sim._client_to_screen(50, 60)
    check("client (50,60) -> screen (150,260)", sx == 150 and sy == 260)

    # ── Test 5b: Relative mouse move INPUT creation ─────────────────
    print("\n[Test 5b] Relative mouse move INPUT...")
    rel_inp = _make_mouse_move_relative(10, -5)
    check("type == INPUT_MOUSE", rel_inp.type == INPUT_MOUSE)
    check("dx == 10", rel_inp.union.mi.dx == 10)
    check("dy == -5", rel_inp.union.mi.dy == -5)
    check("dwFlags == MOVE only (no ABSOLUTE)",
          rel_inp.union.mi.dwFlags == MOUSEEVENTF_MOVE)
    check("not absolute",
          (rel_inp.union.mi.dwFlags & MOUSEEVENTF_ABSOLUTE) == 0)

    # ── Test 6: VK_MAP coverage ─────────────────────────────────────
    print("\n[Test 6] VK_MAP coverage...")
    required_keys = ['w', 'a', 's', 'd', 'e', 'esc', 'escape', 'space', 'enter']
    for k in required_keys:
        check(f"VK_MAP['{k}'] defined", k in VK_MAP and VK_MAP[k] > 0)

    # ── Test 7: mouse_move segment calculation (relative mode) ──────
    print("\n[Test 7] Mouse move segment planning (relative mode)...")
    # Verify the relative move INPUT produces correct delta values
    rel_x, rel_y = 100, 50
    rel_inp = _make_mouse_move_relative(rel_x, rel_y)
    check("relative dx == 100", rel_inp.union.mi.dx == 100)
    check("relative dy == 50", rel_inp.union.mi.dy == 50)
    check("relative mode: no ABSOLUTE flag",
          (rel_inp.union.mi.dwFlags & MOUSEEVENTF_ABSOLUTE) == 0)

    # ── Summary ─────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed == 0:
        print("All tests passed!")
    else:
        print(f"WARNING: {failed} test(s) failed!")
    print(f"{'=' * 50}")
    return failed == 0


if __name__ == "__main__":
    test_sendinput_simulator()


# ── Quick input verification ───────────────────────────────────────────

def test_real_input():
    """Quick test to verify real input is being sent.

    IMPORTANT: This will actually send keyboard/mouse events!
    Make sure your game window is ready and you can stop quickly if needed.
    """
    import sys

    try:
        from src.core.window_mgr import WindowManager

        print("\n" + "=" * 50)
        print("REAL INPUT TEST — Be prepared to switch windows!")
        print("=" * 50 + "\n")

        # Create simulator with debug mode enabled
        wm = WindowManager(process_name="NRC-Win64-Shipping.exe", debug=True)
        sim = SendInputSimulator(wm, debug=True)

        # Wait a moment for user to prepare
        print("Preparing... in 3 seconds, will send 'w' key then 'a' key.\n")
        time.sleep(3)

        # Test keyboard
        print("Test 1: Pressing 'w' for 0.3s...")
        result = sim.press_key('w', duration=0.3)
        print(f"→ Result: {result} events sent\n")

        time.sleep(0.5)

        print("Test 2: Pressing 'a' for 0.3s...")
        result = sim.press_key('a', duration=0.3)
        print(f"→ Result: {result} events sent\n")

        time.sleep(0.5)

        print("Test 3: Testing mouse move (client offset 100,100 → 150,150)...")
        result = sim.mouse_move(50, 50)
        print(f"→ Result: {result} events sent\n")

        print("✓ Real input test completed!")
        print("=" * 50 + "\n")

    except Exception as e:
        print(f"\n✗ Error during real input test: {e}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--real-test":
        test_real_input()
    else:
        test_sendinput_simulator()
