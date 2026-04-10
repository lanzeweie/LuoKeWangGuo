#!/usr/bin/env python3
"""
CV 模板截取工具
用于截取游戏画面并手动框选模板匹配区域，输出模板图片和相对坐标配置。

用法:
    uv run python -m src.tools.template_captor              # 交互式截取
    uv run python -m src.tools.template_captor --capture    # 截取精灵球模式
    uv run python -m src.tools.template_captor --battle     # 截取战斗模式
    uv run python -m src.tools.template_captor --both       # 依次截取两种模式
"""

import os
import time
import json
import tkinter as tk
from tkinter import messagebox
from typing import Optional, Callable, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageTk
import dxcam

from src.core.window_mgr import WindowManager
from src.logger import get_logger

# ── 模板配置导出路径 ──
TEMPLATE_DIR = "data/templates"
CONFIG_PATH = os.path.join(TEMPLATE_DIR, "templates_config.json")


@dataclass
class TemplateRegion:
    """模板区域数据（相对坐标 0.0-1.0）"""
    name: str
    rel_x: float          # 相对 x (0.0-1.0)
    rel_y: float          # 相对 y (0.0-1.0)
    rel_w: float          # 相对宽度 (0.0-1.0)
    rel_h: float          # 相对高度 (0.0-1.0)
    abs_x: int            # 绝对 x (像素，仅供查看)
    abs_y: int            # 绝对 y (像素)
    abs_w: int            # 绝对宽度 (像素)
    abs_h: int            # 绝对高度 (像素)
    screenshot_path: str = ""
    template_path: str = ""
    window_w: int = 0     # 截图时的窗口宽度
    window_h: int = 0     # 截图时的窗口高度

    def to_dict(self) -> dict:
        """转为可序列化字典（排除冗余字段）"""
        return {
            "rel_x": self.rel_x,
            "rel_y": self.rel_y,
            "rel_w": self.rel_w,
            "rel_h": self.rel_h,
            "abs_x": self.abs_x,
            "abs_y": self.abs_y,
            "abs_w": self.abs_w,
            "abs_h": self.abs_h,
            "template_path": self.template_path,
            "window_w": self.window_w,
            "window_h": self.window_h,
        }


# ─────────────────────────── 截图引擎 ───────────────────────────

class CaptureEngine:
    """dxcam 截图引擎"""

    def __init__(self, debug: bool = False):
        self.logger = get_logger(debug=debug)
        self.window_mgr = WindowManager(debug=debug)
        self._camera = None

    def capture(self) -> Optional[Image.Image]:
        """截取游戏窗口画面，返回 PIL Image"""
        if not self.window_mgr.find_window():
            self.logger.error("未找到游戏窗口")
            return None

        screen_region = self.window_mgr.get_screen_region()
        if not screen_region:
            self.logger.error("无法获取窗口区域")
            return None

        left, top, right, bottom = screen_region
        self.logger.info(f"截取区域: ({left}, {top}, {right}, {bottom})")

        try:
            # dxcam 缓存相机实例，必须删除旧实例才能重新初始化
            if self._camera is not None:
                self._camera.stop()
                del self._camera
                self._camera = None
                time.sleep(0.1)  # 给 DXGI 一点时间释放

            camera = dxcam.create(output_color="BGR")
            if camera is None:
                self.logger.error("创建 dxcam 失败")
                return None

            self._camera = camera
            camera.start(target_fps=30, video_mode=True, region=screen_region)

            # dxcam 需要预热
            frame = None
            for _ in range(10):
                frame = camera.grab()
                time.sleep(0.05)
                if frame is not None:
                    break

            camera.stop()

            if frame is None:
                self.logger.error("dxcam 捕获帧失败")
                return None

            self.logger.info(f"dxcam 帧尺寸: {frame.shape}")
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            self.logger.success(f"截图完成: {img.size}")
            return img

        except RuntimeError as e:
            self.logger.error(f"dxcam 运行时错误: {e}")
            return None
        except OSError as e:
            self.logger.error(f"dxcam 系统错误 (DXGI): {e}")
            return None
        except Exception as e:
            self.logger.error(f"dxcam 截图失败: {type(e).__name__}: {e}")
            return None


# ─────────────────────────── 模板配置管理 ───────────────────────────

class TemplateConfigManager:
    """模板配置读写"""

    def __init__(self, template_dir: str = TEMPLATE_DIR, config_path: str = CONFIG_PATH):
        self.template_dir = template_dir
        self.config_path = config_path
        os.makedirs(template_dir, exist_ok=True)

    def save_template(
        self,
        image: Image.Image,
        region: Tuple[int, int, int, int],
        name: str
    ) -> TemplateRegion:
        """裁剪模板、保存图片、生成 TemplateRegion"""
        x, y, w, h = region
        img_w, img_h = image.size

        # 裁剪并保存模板
        template = image.crop((x, y, x + w, y + h))
        template_path = os.path.join(self.template_dir, f"{name}.png")
        template.save(template_path)

        # 保存完整截图
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(self.template_dir, f"screenshot_{name}_{timestamp}.png")
        image.save(screenshot_path)

        return TemplateRegion(
            name=name,
            rel_x=round(x / img_w, 4),
            rel_y=round(y / img_h, 4),
            rel_w=round(w / img_w, 4),
            rel_h=round(h / img_h, 4),
            abs_x=x, abs_y=y, abs_w=w, abs_h=h,
            window_w=img_w, window_h=img_h,
            screenshot_path=screenshot_path,
            template_path=template_path,
        )

    def save_config(self, regions: list[TemplateRegion]):
        """将模板配置写入 JSON 文件，供其他模块直接加载"""
        config = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "templates": {r.name: r.to_dict() for r in regions},
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def load_config(self) -> dict:
        """加载已保存的模板配置"""
        if not os.path.exists(self.config_path):
            return {}
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)


# ─────────────────────────── GUI: 截图 + 框选 + 放大预览 ───────────────────────────

class TemplateCaptureGUI:
    """
    一站式 GUI：截图 → 框选 → 放大预览 → 确认保存 / 重拍 / 重选 / 取消
    """

    def __init__(
        self,
        image: Image.Image,
        title: str,
        on_retake: Callable[[], Optional[Image.Image]],
        on_confirm: Callable[[Image.Image, Tuple[int, int, int, int]], None],
        on_cancel: Callable[[], None],
    ):
        self._on_retake = on_retake
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self._image = image
        self._rect = None
        self._start_x = 0
        self._start_y = 0

        # 显示缩放
        max_w, max_h = 1280, 720
        img_w, img_h = image.size
        scale = min(max_w / img_w, max_h / img_h, 1.0)
        self._disp_w = int(img_w * scale)
        self._disp_h = int(img_h * scale)
        self._scale = scale

        # 主窗口
        self._root = tk.Tk()
        self._root.title(title)
        self._root.resizable(False, False)
        self._root.attributes("-topmost", True)
        self._root.after(100, lambda: self._root.attributes("-topmost", False))

        # 画布
        self._canvas = tk.Canvas(
            self._root, width=self._disp_w, height=self._disp_h,
            cursor="cross", bg="gray20"
        )
        self._canvas.pack(fill="both", expand=False)

        # 提示
        self._hint = tk.Label(
            self._root, text="拖拽鼠标框选模板区域 | 点击「重拍」可重新截图",
            font=("Microsoft YaHei", 10), bg="#1a1a2e", fg="#e0e0e0"
        )
        self._hint.pack(fill="x", pady=(6, 2))

        # 坐标
        self._coord_label = tk.Label(
            self._root, text="未选择区域", font=("Consolas", 9), bg="#1a1a2e", fg="#00ff41"
        )
        self._coord_label.pack(fill="x", pady=(0, 2))

        # 按钮
        btn_frame = tk.Frame(self._root, bg="#1a1a2e")
        btn_frame.pack(fill="x", pady=(2, 8), padx=8)
        tk.Button(btn_frame, text="预览", command=self._preview,
                  font=("Microsoft YaHei", 10), width=10).pack(side="left", padx=4)
        tk.Button(btn_frame, text="重拍", command=self._retake,
                  font=("Microsoft YaHei", 10), width=10).pack(side="left", padx=4)
        tk.Button(btn_frame, text="重选", command=self._reset,
                  font=("Microsoft YaHei", 10), width=10).pack(side="left", padx=4)
        tk.Button(btn_frame, text="取消", command=self._cancel,
                  font=("Microsoft YaHei", 10), width=10).pack(side="left", padx=4)

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Double-Button-1>", self._preview)

        self._root.protocol("WM_DELETE_WINDOW", self._cancel)
        self._update_image(image)
        self._center_window()
        self._root.mainloop()

    # ── 内部方法 ──

    def _update_image(self, image: Image.Image):
        self._image = image
        disp_img = image.resize((self._disp_w, self._disp_h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(disp_img)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._rect = None
        self._coord_label.config(text="未选择区域")

    def _center_window(self):
        self._root.update_idletasks()
        w = self._disp_w + 20
        h = self._disp_h + 120
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self._root.geometry(f"{w}x{h}+{x}+{y}")

    def _on_press(self, event):
        self._start_x = event.x
        self._start_y = event.y
        if self._rect:
            self._canvas.delete(self._rect)
        self._rect = self._canvas.create_rectangle(
            self._start_x, self._start_y, self._start_x, self._start_y,
            outline="#ff4444", width=2, dash=(5, 3)
        )

    def _on_drag(self, event):
        if self._rect:
            self._canvas.coords(
                self._rect,
                self._start_x, self._start_y, event.x, event.y
            )
        cx1 = min(self._start_x, event.x)
        cy1 = min(self._start_y, event.y)
        cw = abs(event.x - self._start_x)
        ch = abs(event.y - self._start_y)
        self._coord_label.config(text=f"起点: ({cx1}, {cy1})  尺寸: {cw} x {ch}")

    def _on_release(self, event):
        if self._rect:
            self._canvas.coords(
                self._rect,
                self._start_x, self._start_y, event.x, event.y
            )

    def _get_orig_region(self) -> Optional[Tuple[int, int, int, int]]:
        if not self._rect:
            return None
        coords = self._canvas.coords(self._rect)
        x1, y1, x2, y2 = coords
        if abs(x2 - x1) < 5 or abs(y2 - y1) < 5:
            return None
        orig_x1 = int(x1 / self._scale)
        orig_y1 = int(y1 / self._scale)
        orig_x2 = int(x2 / self._scale)
        orig_y2 = int(y2 / self._scale)
        return (
            min(orig_x1, orig_x2), min(orig_y1, orig_y2),
            abs(orig_x2 - orig_x1), abs(orig_y2 - orig_y1)
        )

    def _preview(self, event=None):
        """放大预览裁剪后的模板"""
        region = self._get_orig_region()
        if not region:
            messagebox.showwarning("提示", "请先框选一个区域", parent=self._root)
            return

        x, y, w, h = region
        cropped = self._image.crop((x, y, x + w, y + h))

        # 放大 2 倍预览
        preview_scale = 2
        preview_w = w * preview_scale
        preview_h = h * preview_scale
        preview_img = cropped.resize((preview_w, preview_h), Image.NEAREST)

        # 预览窗口
        win = tk.Toplevel(self._root)
        win.title(f"模板预览 {w}x{h}")
        win.attributes("-topmost", True)

        photo = ImageTk.PhotoImage(preview_img)
        lbl = tk.Label(win, image=photo)
        lbl.image = photo  # 防止 GC
        lbl.pack()

        info = tk.Label(
            win, text=f"原始尺寸: {w}x{h} | 预览放大 {preview_scale}x",
            font=("Consolas", 9)
        )
        info.pack(pady=4)

        btn_f = tk.Frame(win)
        btn_f.pack(pady=6)

        def _do_save():
            # 预检查：模板过小则提示
            x, y, w, h = region
            if w < 15 or h < 15:
                messagebox.showwarning(
                    "模板过小",
                    f"模板尺寸 {w}x{h} 过小，可能导致匹配不稳定。\n建议框选更大的特征区域。",
                    parent=win
                )
                return  # 不关闭预览窗口，让用户重新选择

            win.destroy()
            self._on_confirm(self._image, region)
            self._root.quit()
            self._root.destroy()

        def _go_back():
            win.destroy()

        tk.Button(btn_f, text="确认保存", command=_do_save, width=12).pack(side="left", padx=6)
        tk.Button(btn_f, text="返回修改", command=_go_back, width=12).pack(side="left", padx=6)

    def _retake(self):
        new_image = self._on_retake()
        if new_image is not None:
            self._update_image(new_image)

    def _reset(self):
        if self._rect:
            self._canvas.delete(self._rect)
            self._rect = None
        self._coord_label.config(text="未选择区域")

    def _cancel(self):
        self._on_cancel()
        self._root.quit()
        self._root.destroy()


# ─────────────────────────── 模板验证 ───────────────────────────

def verify_template(template_path: str, image: Image.Image) -> float:
    """验证模板匹配效果，返回最佳匹配分数"""
    template = cv2.imread(template_path)
    if template is None:
        return 0.0
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    img_gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return round(max_val, 4)


# ─────────────────────────── 主流程 ───────────────────────────

class TemplateCaptor:
    """模板截取工具"""

    def __init__(self, debug: bool = False):
        self.logger = get_logger(debug=debug)
        self.capture = CaptureEngine(debug=debug)
        self.config_mgr = TemplateConfigManager()

    def print_config(self, regions: list[TemplateRegion]):
        """打印配置信息"""
        print("=" * 60)
        print("模板配置")
        print("=" * 60)

        for r in regions:
            print(f"\n--- {r.name} ---")
            print(
                f"相对坐标: rel_x={r.rel_x}, rel_y={r.rel_y}, "
                f"rel_w={r.rel_w}, rel_h={r.rel_h}"
            )
            print(
                f"绝对坐标: x={r.abs_x}, y={r.abs_y}, w={r.abs_w}, h={r.abs_h}"
            )
            print(f"窗口尺寸: {r.window_w}x{r.window_h}")
            print(f"模板文件: {r.template_path}")

        # 输出 JSON 配置路径
        print(f"\n配置文件已保存: {self.config_mgr.config_path}")
        print("其他模块可直接加载此配置，使用相对坐标进行模板匹配")

    def run(self, modes: list[str]) -> list[TemplateRegion]:
        """执行模板截取流程"""
        self.logger.info("=" * 60)
        self.logger.info("CV 模板截取工具")
        self.logger.info("请确保游戏窗口已打开，并显示到需要截取的模式")
        self.logger.info("=" * 60)

        # 首次截图
        self.logger.info("正在截取游戏画面...")
        image = self.capture.capture()
        if not image:
            self.logger.error("截图失败")
            return []

        regions = []
        mode_map = {
            "capture": "capture_mode",
            "battle": "battle_mode",
        }

        for mode in modes:
            name = mode_map.get(mode)
            if not name:
                self.logger.warning(f"未知模式: {mode}")
                continue

            def make_retake():
                def _retake():
                    self.logger.info("重新截取游戏画面...")
                    return self.capture.capture()
                return _retake

            saved = []

            def make_confirm_handler():
                def _on_confirm(img, region):
                    tr = self.config_mgr.save_template(img, region, name)
                    saved.append(tr)
                    score = verify_template(tr.template_path, img)
                    self.logger.info(f"模板匹配验证: 最佳分数 = {score}")
                    if score < 0.6:
                        self.logger.warning("匹配分数较低，建议重新框选更大的特征区域")
                return _on_confirm

            def _on_cancel():
                pass

            self.logger.info(f"\n--- {name} ---")
            self.logger.info("框选截图中的模板区域，不满意可点击「重拍」重新截图")

            TemplateCaptureGUI(
                image=image,
                title=f"框选 {name} 区域",
                on_retake=make_retake(),
                on_confirm=make_confirm_handler(),
                on_cancel=_on_cancel,
            )

            if saved:
                regions.append(saved[0])
                if len(modes) == 1:
                    break
                # 下一轮使用最新截图
                try:
                    image = Image.open(regions[-1].screenshot_path)
                except Exception as e:
                    self.logger.error(f"加载截图失败: {e}")
                    break
            else:
                self.logger.warning(f"跳过 {name}")

        # 保存配置文件
        if regions:
            self.config_mgr.save_config(regions)
            self.print_config(regions)
        else:
            self.logger.warning("未保存任何模板")

        self.logger.info("\n完成!")
        return regions


# ─────────────────────────── CLI ───────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="CV 模板截取工具")
    parser.add_argument("--capture", action="store_true", help="截取精灵球模式模板")
    parser.add_argument("--battle", action="store_true", help="截取战斗模式模板")
    parser.add_argument("--both", action="store_true", help="依次截取两种模式")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    if not any([args.capture, args.battle, args.both]):
        modes = ["capture", "battle"]
    elif args.both:
        modes = ["capture", "battle"]
    else:
        modes = []
        if args.capture:
            modes.append("capture")
        if args.battle:
            modes.append("battle")

    captor = TemplateCaptor(debug=args.debug)
    captor.run(modes)


if __name__ == "__main__":
    main()
