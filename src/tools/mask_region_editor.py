#!/usr/bin/env python3
"""
遮蔽区域编辑器

让用户在游戏截图上多次框选需要遮蔽（忽略）的区域，保存到统一配置文件。
遮蔽区域会在 YOLO 检测后用于过滤掉这些区域内的检测结果。

用法:
    uv run python -m src.tools.mask_region_editor
    uv run python -m src.tools.mask_region_editor --debug
"""

import os
import sys
import time
import json
from typing import Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime

import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

from src.tools.template_captor import CaptureEngine
from src.logger import get_logger

# ── 配置路径 ──
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "templates", "templates_config.json")


@dataclass
class MaskRegion:
    """遮蔽区域（相对坐标 + 绝对坐标）"""
    rel_x: float
    rel_y: float
    rel_w: float
    rel_h: float
    abs_x: int
    abs_y: int
    abs_w: int
    abs_h: int

    @classmethod
    def from_abs_coords(cls, x: int, y: int, w: int, h: int, img_w: int, img_h: int) -> "MaskRegion":
        return cls(
            rel_x=round(x / img_w, 4),
            rel_y=round(y / img_h, 4),
            rel_w=round(w / img_w, 4),
            rel_h=round(h / img_h, 4),
            abs_x=x, abs_y=y, abs_w=w, abs_h=h,
        )


# ─────────────────────────── 配置读写 ───────────────────────────

def load_mask_regions() -> List[dict]:
    """从配置文件加载已有遮蔽区域"""
    if not os.path.exists(CONFIG_PATH):
        return []
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("mask_regions", [])
    except Exception:
        return []


def save_mask_regions(regions: List[dict]) -> None:
    """保存遮蔽区域到配置文件（增量写入）"""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

    existing: dict = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    existing["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing["mask_regions"] = regions

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


# ─────────────────────────── GUI 编辑器 ───────────────────────────

class MaskRegionEditor:
    """遮蔽区域编辑器 — 多次框选、实时预览、确认保存"""

    MAX_DISP_W = 1280
    MAX_DISP_H = 720
    MIN_RECT_SIZE = 5

    def __init__(self, image: Image.Image, existing_regions: List[dict], debug: bool = False):
        self.logger = get_logger(debug=debug)
        self._image = image
        self._img_w, self._img_h = image.size
        self._regions: List[MaskRegion] = []  # 已确认的遮蔽区域
        self._existing_regions = existing_regions  # 配置文件中已有的区域

        # 计算显示缩放
        scale = min(
            self.MAX_DISP_W / self._img_w,
            self.MAX_DISP_H / self._img_h,
            1.0,
        )
        self._disp_w = int(self._img_w * scale)
        self._disp_h = int(self._img_h * scale)
        self._scale = scale

        # 交互状态
        self._rect_id: Optional[int] = None
        self._start_x = 0
        self._start_y = 0

        # 构建 Tkinter UI
        self._root = tk.Tk()
        self._root.title("遮蔽区域编辑器")
        self._root.resizable(False, False)
        self._root.attributes("-topmost", True)
        self._root.after(100, lambda: self._root.attributes("-topmost", False))

        # 画布
        self._canvas = tk.Canvas(
            self._root, width=self._disp_w, height=self._disp_h,
            cursor="cross", bg="gray20",
        )
        self._canvas.pack(fill="both", expand=False)

        # 提示文字
        self._hint = tk.Label(
            self._root, text="拖拽鼠标框选遮蔽区域 | 可多次框选",
            font=("Microsoft YaHei", 10), bg="#1a1a2e", fg="#e0e0e0",
        )
        self._hint.pack(fill="x", pady=(6, 2))

        # 坐标 / 计数显示
        self._info_label = tk.Label(
            self._root, text=f"已框选: 0 个区域",
            font=("Consolas", 9), bg="#1a1a2e", fg="#00ff41",
        )
        self._info_label.pack(fill="x", pady=(0, 2))

        # 按钮栏
        btn_frame = tk.Frame(self._root, bg="#1a1a2e")
        btn_frame.pack(fill="x", pady=(2, 8), padx=8)

        tk.Button(
            btn_frame, text="重拍", command=self._retake,
            font=("Microsoft YaHei", 10), width=10,
        ).pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="删除最后一个", command=self._undo_last,
            font=("Microsoft YaHei", 10), width=10,
        ).pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="清空", command=self._clear_all,
            font=("Microsoft YaHei", 10), width=10,
        ).pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="确认保存", command=self._confirm,
            font=("Microsoft YaHei", 10, "bold"), width=10, bg="#4CAF50",
        ).pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="取消", command=self._cancel,
            font=("Microsoft YaHei", 10), width=10,
        ).pack(side="left", padx=4)

        # 绑定事件
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

        self._root.protocol("WM_DELETE_WINDOW", self._cancel)

        # 绘制图片和已有区域
        self._draw_image(image)
        self._center_window()
        self._root.mainloop()

    def _draw_image(self, image: Image.Image):
        """在画布上绘制截图"""
        self._image = image
        self._img_w, self._img_h = image.size
        disp_img = image.resize((self._disp_w, self._disp_h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(disp_img)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)

    def _redraw_all(self):
        """重绘图片 + 所有已确认遮蔽区域"""
        self._draw_image(self._image)

        # 绘制配置文件中已有的区域（绿色半透明）
        for region in self._existing_regions:
            rx = int(region["rel_x"] * self._img_w * self._scale)
            ry = int(region["rel_y"] * self._img_h * self._scale)
            rw = int(region["rel_w"] * self._img_w * self._scale)
            rh = int(region["rel_h"] * self._img_h * self._scale)
            self._canvas.create_rectangle(
                rx, ry, rx + rw, ry + rh,
                fill="green", stipple="gray50", outline="green", width=2,
            )

        # 绘制本次新增的区域（红色半透明）
        for region in self._regions:
            rx = int(region.abs_x * self._scale)
            ry = int(region.abs_y * self._scale)
            rw = int(region.abs_w * self._scale)
            rh = int(region.abs_h * self._scale)
            self._canvas.create_rectangle(
                rx, ry, rx + rw, ry + rh,
                fill="red", stipple="gray50", outline="red", width=2,
            )

        self._update_info()

    def _update_info(self):
        total = len(self._regions) + len(self._existing_regions)
        self._info_label.config(
            text=f"已框选: {len(self._regions)} 个 | 总计: {total} 个遮蔽区域"
        )

    # ── 交互 ──

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

    def _on_release(self, event):
        if self._rect_id:
            self._canvas.coords(
                self._rect_id,
                self._start_x, self._start_y, event.x, event.y,
            )
            x1 = min(self._start_x, event.x)
            y1 = min(self._start_y, event.y)
            x2 = max(self._start_x, event.x)
            y2 = max(self._start_y, event.y)

            w = x2 - x1
            h = y2 - y1

            if w < self.MIN_RECT_SIZE or h < self.MIN_RECT_SIZE:
                self._canvas.delete(self._rect_id)
                self._rect_id = None
                return

            # 换算为原始图片坐标
            orig_x = int(x1 / self._scale)
            orig_y = int(y1 / self._scale)
            orig_w = int(w / self._scale)
            orig_h = int(h / self._scale)

            region = MaskRegion.from_abs_coords(orig_x, orig_y, orig_w, orig_h, self._img_w, self._img_h)
            self._regions.append(region)
            self._rect_id = None
            self._redraw_all()

    # ── 按钮 ──

    def _retake(self):
        """重新截图并刷新"""
        # 判断是否 debug：logger 有 debug 属性
        is_debug = getattr(self.logger, "debug", False)
        engine = CaptureEngine(debug=is_debug)
        new_image = engine.capture()
        if new_image is not None:
            self._image = new_image
            self._img_w, self._img_h = new_image.size
            self._scale = min(
                self.MAX_DISP_W / self._img_w,
                self.MAX_DISP_H / self._img_h,
                1.0,
            )
            self._disp_w = int(self._img_w * self._scale)
            self._disp_h = int(self._img_h * self._scale)
            self._canvas.config(width=self._disp_w, height=self._disp_h)
            self._redraw_all()
            self.logger.info("截图已刷新")
        else:
            messagebox.showerror("错误", "截图失败", parent=self._root)

    def _undo_last(self):
        if self._regions:
            self._regions.pop()
            self._redraw_all()
            self.logger.info("已删除最后一个遮蔽区域")
        else:
            messagebox.showinfo("提示", "没有可删除的区域", parent=self._root)

    def _clear_all(self):
        if self._regions:
            confirmed = messagebox.askyesno(
                "确认", f"确定清空所有 {len(self._regions)} 个区域？",
                parent=self._root,
            )
            if confirmed:
                self._regions.clear()
                self._redraw_all()
                self.logger.info("已清空所有遮蔽区域")
        else:
            messagebox.showinfo("提示", "没有可清空的区域", parent=self._root)

    def _confirm(self):
        if not self._regions:
            messagebox.showwarning("提示", "请至少框选一个遮蔽区域", parent=self._root)
            return

        # 合并已有区域和新增区域
        all_regions = list(self._existing_regions)
        all_regions.extend([
            {"rel_x": r.rel_x, "rel_y": r.rel_y, "rel_w": r.rel_w, "rel_h": r.rel_h}
            for r in self._regions
        ])

        save_mask_regions(all_regions)

        self.logger.success(f"已保存 {len(self._regions)} 个遮蔽区域")
        messagebox.showinfo(
            "成功", f"已保存 {len(self._regions)} 个遮蔽区域\n配置文件: {CONFIG_PATH}",
            parent=self._root,
        )
        self._root.quit()
        self._root.destroy()

    def _cancel(self):
        self._root.quit()
        self._root.destroy()

    def _center_window(self):
        self._root.update_idletasks()
        w = self._disp_w + 20
        h = self._disp_h + 120
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self._root.geometry(f"{w}x{h}+{x}+{y}")


# ─────────────────────────── 主入口 ───────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="遮蔽区域编辑器 — 在游戏截图上框选需要忽略的区域",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    logger = get_logger(debug=args.debug)
    logger.info("=" * 60)
    logger.info("遮蔽区域编辑器")
    logger.info("=" * 60)

    # 加载已有遮蔽区域
    existing = load_mask_regions()
    if existing:
        logger.info(f"已有 {len(existing)} 个遮蔽区域，将在编辑器中显示（绿色）")

    # 截图
    logger.info("正在截取游戏画面...")
    engine = CaptureEngine(debug=args.debug)
    image = engine.capture()
    if not image:
        logger.error("截图失败")
        sys.exit(1)

    logger.info("截图完成，打开编辑器...")

    # 打开编辑器
    MaskRegionEditor(image, existing_regions=existing, debug=args.debug)

    logger.info("完成!")


if __name__ == "__main__":
    main()
