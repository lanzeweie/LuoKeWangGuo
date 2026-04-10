#!/usr/bin/env python3
"""
通用 GUI 坐标选择器

提供两种交互模式：
- "point" — 点击选点，输出单个相对坐标 (rel_x, rel_y)
- "rect"  — 拖拽框选矩形，输出相对区域 (rel_x, rel_y, rel_w, rel_h)

设计原则：
- 纯展示截图 + 用户交互，不绑定任何业务逻辑
- 输出相对坐标 (0.0-1.0)，适配不同分辨率
- 通过回调函数 (callbacks) 注入业务行为
- 可复用、可组合

用法:
    from src.tools.relative_coordinate_picker import (
        RelativeCoordinatePicker, PickerMode
    )

    # 选点模式
    def on_point_selected(rel_coords):
        print(f"选中点: {rel_coords}")

    picker = RelativeCoordinatePicker(
        image=screenshot,
        title="选择确认按钮位置",
        mode=PickerMode.POINT,
        on_confirm=on_point_selected,
        on_retake=lambda: recapture(),
    )

    # 框选矩形模式
    def on_rect_selected(region):
        print(f"选中区域: {region}")

    picker = RelativeCoordinatePicker(
        image=screenshot,
        title="框选模板区域",
        mode=PickerMode.RECT,
        on_confirm=on_rect_selected,
        on_retake=lambda: recapture(),
    )
"""

import tkinter as tk
from tkinter import messagebox
from typing import Optional, Callable, Union, Tuple
from dataclasses import dataclass
from enum import Enum, auto

from PIL import Image, ImageTk


class PickerMode(Enum):
    """选择器模式"""
    POINT = auto()  # 点击选点
    RECT = auto()   # 拖拽框选


@dataclass
class PointCoords:
    """选点结果（相对坐标 0.0-1.0）"""
    rel_x: float
    rel_y: float
    abs_x: int
    abs_y: int
    window_w: int
    window_h: int

    def to_dict(self) -> dict:
        return {
            "rel_x": self.rel_x,
            "rel_y": self.rel_y,
            "abs_x": self.abs_x,
            "abs_y": self.abs_y,
            "window_w": self.window_w,
            "window_h": self.window_h,
        }


@dataclass
class RectCoords:
    """框选结果（相对坐标 0.0-1.0）"""
    rel_x: float
    rel_y: float
    rel_w: float
    rel_h: float
    abs_x: int
    abs_y: int
    abs_w: int
    abs_h: int
    window_w: int
    window_h: int

    def to_dict(self) -> dict:
        return {
            "rel_x": self.rel_x,
            "rel_y": self.rel_y,
            "rel_w": self.rel_w,
            "rel_h": self.rel_h,
            "abs_x": self.abs_x,
            "abs_y": self.abs_y,
            "abs_w": self.abs_w,
            "abs_h": self.abs_h,
            "window_w": self.window_w,
            "window_h": self.window_h,
        }


# ─────────────────────────── 核心 GUI 组件 ───────────────────────────

class RelativeCoordinatePicker:
    """
    通用相对坐标选择器 GUI

    支持两种模式：
    - PickerMode.POINT: 点击选点 → on_confirm(PointCoords)
    - PickerMode.RECT:  拖拽框选 → on_confirm(RectCoords)
    """

    # 显示尺寸上限
    MAX_DISP_W = 1280
    MAX_DISP_H = 720
    MIN_RECT_SIZE = 5  # 矩形最小尺寸（显示像素）

    def __init__(
        self,
        image: Image.Image,
        title: str,
        mode: PickerMode,
        on_confirm: Callable[[Union[PointCoords, RectCoords]], None],
        on_retake: Optional[Callable[[], Optional[Image.Image]]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        hint_text: Optional[str] = None,
    ):
        """
        Args:
            image: 当前截图 (PIL Image)
            title: 窗口标题
            mode: 选择模式 (POINT / RECT)
            on_confirm: 确认回调，接收 PointCoords 或 RectCoords
            on_retake: 重拍回调，返回新截图
            on_cancel: 取消回调
            hint_text: 自定义提示文字（默认根据 mode 生成）
        """
        self._mode = mode
        self._on_confirm = on_confirm
        self._on_retake = on_retake
        self._on_cancel = on_cancel
        self._image = image

        # 交互状态
        self._rect_id: Optional[int] = None
        self._mark_id: Optional[int] = None
        self._start_x = 0
        self._start_y = 0
        self._selected = False
        # 存储最后一次选中的原始坐标（避免从 label 文字解析）
        self._last_point: Optional[Tuple[int, int]] = None

        # 计算显示缩放
        img_w, img_h = image.size
        scale = min(
            self.MAX_DISP_W / img_w,
            self.MAX_DISP_H / img_h,
            1.0,
        )
        self._disp_w = int(img_w * scale)
        self._disp_h = int(img_h * scale)
        self._scale = scale

        # ── 构建 Tkinter UI ──
        self._root = tk.Tk()
        self._root.title(title)
        self._root.resizable(False, False)
        self._root.attributes("-topmost", True)
        self._root.after(100, lambda: self._root.attributes("-topmost", False))

        # 画布
        self._canvas = tk.Canvas(
            self._root, width=self._disp_w, height=self._disp_h,
            cursor="cross" if mode == PickerMode.RECT else "dot", bg="gray20",
        )
        self._canvas.pack(fill="both", expand=False)

        # 提示文字
        if hint_text is None:
            if mode == PickerMode.POINT:
                hint_text = "点击选择目标位置 | 点击「重拍」可重新截图"
            else:
                hint_text = "拖拽鼠标框选区域 | 点击「重拍」可重新截图"

        self._hint = tk.Label(
            self._root, text=hint_text,
            font=("Microsoft YaHei", 10), bg="#1a1a2e", fg="#e0e0e0",
        )
        self._hint.pack(fill="x", pady=(6, 2))

        # 坐标显示
        self._coord_label = tk.Label(
            self._root, text="未选择",
            font=("Consolas", 9), bg="#1a1a2e", fg="#00ff41",
        )
        self._coord_label.pack(fill="x", pady=(0, 2))

        # 按钮栏
        btn_frame = tk.Frame(self._root, bg="#1a1a2e")
        btn_frame.pack(fill="x", pady=(2, 8), padx=8)

        if mode == PickerMode.RECT:
            tk.Button(
                btn_frame, text="预览", command=self._preview,
                font=("Microsoft YaHei", 10), width=10,
            ).pack(side="left", padx=4)

        if on_retake is not None:
            tk.Button(
                btn_frame, text="重拍", command=self._retake,
                font=("Microsoft YaHei", 10), width=10,
            ).pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="重选", command=self._reset,
            font=("Microsoft YaHei", 10), width=10,
        ).pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="取消", command=self._cancel,
            font=("Microsoft YaHei", 10), width=10,
        ).pack(side="left", padx=4)

        # 绑定事件
        if mode == PickerMode.POINT:
            self._canvas.bind("<ButtonPress-1>", self._on_point_click)
        else:
            self._canvas.bind("<ButtonPress-1>", self._on_press)
            self._canvas.bind("<B1-Motion>", self._on_drag)
            self._canvas.bind("<ButtonRelease-1>", self._on_release)
            self._canvas.bind("<Double-Button-1>", self._preview)

        self._root.protocol("WM_DELETE_WINDOW", self._cancel)

        # 绘制图片
        self._update_image(image)
        self._center_window()
        self._root.mainloop()

    # ── 公共方法 ──

    def _update_image(self, image: Image.Image):
        """更新画布上的截图"""
        self._image = image
        disp_img = image.resize((self._disp_w, self._disp_h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(disp_img)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._rect_id = None
        self._mark_id = None
        self._last_point = None
        self._coord_label.config(text="未选择")
        self._selected = False

    # ── 点选模式 ──

    def _on_point_click(self, event):
        disp_x, disp_y = event.x, event.y
        orig_x = int(disp_x / self._scale)
        orig_y = int(disp_y / self._scale)
        img_w, img_h = self._image.size

        # 删除旧标记
        if self._mark_id:
            self._canvas.delete(self._mark_id)

        # 画十字标记
        size = 10
        self._mark_id = self._canvas.create_line(
            disp_x - size, disp_y, disp_x + size, disp_y,
            fill="#00ff41", width=2,
        )
        self._canvas.create_line(
            disp_x, disp_y - size, disp_x, disp_y + size,
            fill="#00ff41", width=2,
        )

        rel_x = round(orig_x / img_w, 4)
        rel_y = round(orig_y / img_h, 4)
        self._last_point = (orig_x, orig_y)
        self._coord_label.config(
            text=f"绝对: ({orig_x}, {orig_y})  相对: ({rel_x}, {rel_y})"
        )
        self._selected = True

        # 弹出确认对话框
        confirmed = messagebox.askyesno(
            "确认", f"确认选择此位置？\n相对坐标: ({rel_x}, {rel_y})",
            parent=self._root,
        )
        if confirmed:
            self._do_confirm()

    def _get_point_coords(self) -> Optional[PointCoords]:
        if not self._selected or self._last_point is None:
            return None
        abs_x, abs_y = self._last_point
        img_w, img_h = self._image.size
        rel_x = round(abs_x / img_w, 4)
        rel_y = round(abs_y / img_h, 4)
        return PointCoords(
            rel_x=rel_x, rel_y=rel_y,
            abs_x=abs_x, abs_y=abs_y,
            window_w=img_w, window_h=img_h,
        )

    # ── 框选模式 ──

    def _on_press(self, event):
        self._start_x = event.x
        self._start_y = event.y
        if self._rect_id:
            self._canvas.delete(self._rect_id)
        self._rect_id = self._canvas.create_rectangle(
            self._start_x, self._start_y, self._start_x, self._start_y,
            outline="#ff4444", width=2, dash=(5, 3),
        )

    def _on_drag(self, event):
        if self._rect_id:
            self._canvas.coords(
                self._rect_id,
                self._start_x, self._start_y, event.x, event.y,
            )
        cx1 = min(self._start_x, event.x)
        cy1 = min(self._start_y, event.y)
        cw = abs(event.x - self._start_x)
        ch = abs(event.y - self._start_y)
        self._coord_label.config(text=f"起点: ({cx1}, {cy1})  尺寸: {cw} x {ch}")

    def _on_release(self, event):
        if self._rect_id:
            self._canvas.coords(
                self._rect_id,
                self._start_x, self._start_y, event.x, event.y,
            )

    def _get_orig_region(self) -> Optional[tuple[int, int, int, int]]:
        if not self._rect_id:
            return None
        coords = self._canvas.coords(self._rect_id)
        x1, y1, x2, y2 = coords
        if abs(x2 - x1) < self.MIN_RECT_SIZE or abs(y2 - y1) < self.MIN_RECT_SIZE:
            return None
        orig_x1 = int(min(x1, x2) / self._scale)
        orig_y1 = int(min(y1, y2) / self._scale)
        orig_x2 = int(max(x1, x2) / self._scale)
        orig_y2 = int(max(y1, y2) / self._scale)
        return (orig_x1, orig_y1, orig_x2 - orig_x1, orig_y2 - orig_y1)

    def _get_rect_coords(self) -> Optional[RectCoords]:
        region = self._get_orig_region()
        if region is None:
            return None
        x, y, w, h = region
        img_w, img_h = self._image.size
        return RectCoords(
            rel_x=round(x / img_w, 4),
            rel_y=round(y / img_h, 4),
            rel_w=round(w / img_w, 4),
            rel_h=round(h / img_h, 4),
            abs_x=x, abs_y=y, abs_w=w, abs_h=h,
            window_w=img_w, window_h=img_h,
        )

    # ── 预览（仅框选模式） ──

    def _preview(self, event=None):
        if self._mode != PickerMode.RECT:
            return
        region = self._get_orig_region()
        if not region:
            messagebox.showwarning("提示", "请先框选一个区域", parent=self._root)
            return

        x, y, w, h = region
        cropped = self._image.crop((x, y, x + w, y + h))

        preview_scale = max(2, 100 // max(w, h, 1))  # 至少放大 2 倍
        preview_w = w * preview_scale
        preview_h = h * preview_scale
        preview_img = cropped.resize((preview_w, preview_h), Image.NEAREST)

        win = tk.Toplevel(self._root)
        win.title(f"预览 {w}x{h}")
        win.attributes("-topmost", True)

        photo = ImageTk.PhotoImage(preview_img)
        lbl = tk.Label(win, image=photo)
        lbl.image = photo
        lbl.pack()

        tk.Label(
            win, text=f"原始: {w}x{h} | 预览 {preview_scale}x",
            font=("Consolas", 9),
        ).pack(pady=4)

        def _do_confirm():
            win.destroy()
            self._do_confirm()

        def _go_back():
            win.destroy()

        btn_f = tk.Frame(win)
        btn_f.pack(pady=6)
        tk.Button(btn_f, text="确认选择", command=_do_confirm, width=12).pack(side="left", padx=6)
        tk.Button(btn_f, text="返回修改", command=_go_back, width=12).pack(side="left", padx=6)

    # ── 按钮回调 ──

    def _do_confirm(self):
        if self._mode == PickerMode.POINT:
            coords = self._get_point_coords()
            if coords is None:
                messagebox.showwarning("提示", "请先点击选择一个位置", parent=self._root)
                return
        else:
            coords = self._get_rect_coords()
            if coords is None:
                messagebox.showwarning("提示", "请先框选一个区域", parent=self._root)
                return
        self._on_confirm(coords)
        self._root.quit()
        self._root.destroy()

    def _retake(self):
        if self._on_retake is None:
            return
        new_image = self._on_retake()
        if new_image is not None:
            self._update_image(new_image)

    def _reset(self):
        if self._rect_id:
            self._canvas.delete(self._rect_id)
            self._rect_id = None
        if self._mark_id:
            self._canvas.delete(self._mark_id)
            self._mark_id = None
        self._last_point = None
        self._coord_label.config(text="未选择")
        self._selected = False

    def _cancel(self):
        if self._on_cancel:
            self._on_cancel()
        self._root.quit()
        self._root.destroy()

    # ── 窗口居中 ──

    def _center_window(self):
        self._root.update_idletasks()
        w = self._disp_w + 20
        h = self._disp_h + 120
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self._root.geometry(f"{w}x{h}+{x}+{y}")
