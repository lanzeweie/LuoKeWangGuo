#!/usr/bin/env python3
"""
CV 模板编辑器 — 通用模板截取与配置工具

完全通用，不硬编码任何业务相关的模板名。用户通过 CLI 参数指定要截取的模板列表，
程序逐个引导完成框选（RECT）或点击（POINT），最终输出到统一配置文件。

配置文件结构 (config/templates/templates_config.json):
├── templates: { "模板名": { rel_x, rel_y, rel_w, rel_h, ... } }   ← ROI 模板
└── click_points: { "点名": { rel_x, rel_y, ... } }                ← 点击位置

用法:
    # 截取单个 ROI 模板
    uv run python -m src.tools.template_captor "capture_mode" rect

    # 截取单个点击点
    uv run python -m src.tools.template_captor "confirm_button" point

    # 一次截取多个模板（混合模式）
    uv run python -m src.tools.template_captor "capture_mode" rect "battle_mode" rect "battle_exit_confirm" rect "confirm_button" point

    # 使用 --file 从文件读取模板列表
    uv run python -m src.tools.template_captor --file task_list.txt

    # 交互式默认模式（不传参数时）
    uv run python -m src.tools.template_captor

task_list.txt 格式（每行: 名称 模式）:
    capture_mode rect
    battle_mode rect
    battle_exit_confirm rect
    confirm_button point

配置加载（其他模块）:
    from src.tools.template_captor import TemplateConfigManager
    config = TemplateConfigManager().load_config()
    roi = config["templates"]["capture_mode"]
    point = config["click_points"]["confirm_button"]
"""

import os
import sys
import time
import json
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np
from PIL import Image
import dxcam

from src.core.capabilities.window_mgr import WindowManager
from src.components.coordinate_picker import (
    RelativeCoordinatePicker,
    PickerMode,
    PointCoords,
    RectCoords,
)
from src.logger import get_logger

# ── 配置路径 ──
TEMPLATE_DIR = "config/templates"
CONFIG_PATH = os.path.join(TEMPLATE_DIR, "templates_config.json")


# ── 数据结构 ──
@dataclass
class TemplateRegion:
    """ROI 模板区域（相对坐标 0.0-1.0）"""
    name: str
    rel_x: float
    rel_y: float
    rel_w: float
    rel_h: float
    abs_x: int
    abs_y: int
    abs_w: int
    abs_h: int
    template_path: str = ""
    window_w: int = 0
    window_h: int = 0

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
            "template_path": self.template_path,
            "window_w": self.window_w,
            "window_h": self.window_h,
        }


@dataclass
class ClickPoint:
    """点击位置（相对坐标 0.0-1.0）"""
    name: str
    rel_x: float
    rel_y: float
    abs_x: int
    abs_y: int
    window_w: int = 0
    window_h: int = 0

    def to_dict(self) -> dict:
        return {
            "rel_x": self.rel_x,
            "rel_y": self.rel_y,
            "abs_x": self.abs_x,
            "abs_y": self.abs_y,
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
            if self._camera is not None:
                self._camera.stop()
                del self._camera
                self._camera = None
                time.sleep(0.1)

            camera = dxcam.create(output_color="BGR")
            if camera is None:
                self.logger.error("创建 dxcam 失败")
                return None

            self._camera = camera
            camera.start(target_fps=30, video_mode=True, region=screen_region)

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


# ─────────────────────────── 配置管理 ───────────────────────────

class TemplateConfigManager:
    """统一配置管理 — 读写 ROI 模板和点击点"""

    def __init__(self, template_dir: str = TEMPLATE_DIR, config_path: str = CONFIG_PATH):
        self.template_dir = template_dir
        self.config_path = config_path
        os.makedirs(template_dir, exist_ok=True)

    def save_template(self, image: Image.Image, region: Tuple[int, int, int, int], name: str) -> TemplateRegion:
        """裁剪模板图片并保存

        注意：保存的 ROI 区域会比模板稍大（向四周各扩展 5px），
        以确保模板匹配时有足够的搜索空间。
        """
        x, y, w, h = region
        img_w, img_h = image.size

        # 1. 裁剪并保存模板（使用用户框选的精确区域）
        template = image.crop((x, y, x + w, y + h))
        template_path = os.path.join(self.template_dir, f"{name}.png")
        template.save(template_path)

        # 2. 保存到配置的 ROI 区域比模板大（向四周各扩展 5px）
        ROI_EXPAND_PX = 5
        roi_x = max(0, x - ROI_EXPAND_PX)
        roi_y = max(0, y - ROI_EXPAND_PX)
        roi_w = min(w + ROI_EXPAND_PX * 2, img_w - roi_x)
        roi_h = min(h + ROI_EXPAND_PX * 2, img_h - roi_y)

        return TemplateRegion(
            name=name,
            rel_x=round(roi_x / img_w, 4),
            rel_y=round(roi_y / img_h, 4),
            rel_w=round(roi_w / img_w, 4),
            rel_h=round(roi_h / img_h, 4),
            abs_x=roi_x, abs_y=roi_y, abs_w=roi_w, abs_h=roi_h,
            window_w=img_w, window_h=img_h,
            template_path=template_path,
        )

    def save_config(self, regions: Optional[list] = None, points: Optional[list] = None):
        """增量写入配置 — 保留已有条目，更新或新增传入的"""
        existing = self.load_config()
        templates = existing.get("templates", {})
        click_points = existing.get("click_points", {})

        if regions:
            for r in regions:
                templates[r.name] = r.to_dict()
        if points:
            for p in points:
                click_points[p.name] = p.to_dict()

        config = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "templates": templates,
            "click_points": click_points,
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def load_config(self) -> dict:
        """加载配置，返回 {templates: {}, click_points: {}}"""
        if not os.path.exists(self.config_path):
            return {"templates": {}, "click_points": {}}
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("templates", {})
            data.setdefault("click_points", {})
            return data


# ─────────────────────────── 模板验证 ───────────────────────────

def verify_template(template_path: str, image: Image.Image) -> float:
    """模板匹配自测 — 返回最佳匹配分数"""
    template = cv2.imread(template_path)
    if template is None:
        return 0.0
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    img_gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return round(max_val, 4)


# ─────────────────────────── 主编辑器 ───────────────────────────

class TemplateCaptor:
    """
    通用 CV 模板编辑器

    调用方式:
        captor = TemplateCaptor(debug=False)
        # 单个 ROI 模板
        captor.run_one("my_template", "rect", image)
        # 单个点击点
        captor.run_one("my_button", "point", image)
        # 批量
        captor.run_batch([
            ("capture_mode", "rect"),
            ("confirm_button", "point"),
        ])
    """

    def __init__(self, debug: bool = False):
        self.logger = get_logger(debug=debug)
        self.capture = CaptureEngine(debug=debug)
        self.config_mgr = TemplateConfigManager()

    def run_one(
        self,
        name: str,
        mode: str,
        image: Image.Image,
    ) -> tuple:
        """执行单个模板的截取流程

        Args:
            name: 模板/点名（写入配置文件的 key）
            mode: "rect" 或 "point"
            image: 当前截图

        Returns:
            (TemplateRegion | ClickPoint | None, updated_image)
        """
        mode_lower = mode.lower()
        picker_mode = PickerMode.RECT if mode_lower == "rect" else PickerMode.POINT

        result = [None]

        def make_retake():
            def _retake():
                self.logger.info(f"[{name}] 重新截图...")
                return self.capture.capture()
            return _retake

        def on_rect(coords: RectCoords):
            tr = self.config_mgr.save_template(
                image,
                (coords.abs_x, coords.abs_y, coords.abs_w, coords.abs_h),
                name,
            )
            result[0] = tr
            score = verify_template(tr.template_path, image)
            self.logger.info(f"[{name}] 模板匹配验证: {score}")
            if score < 0.6:
                self.logger.warning(f"[{name}] 匹配分数较低，建议重新框选")

        def on_point(coords: PointCoords):
            result[0] = ClickPoint(
                name=name,
                rel_x=coords.rel_x, rel_y=coords.rel_y,
                abs_x=coords.abs_x, abs_y=coords.abs_y,
                window_w=coords.window_w, window_h=coords.window_h,
            )

        hint = (
            f"框选 '{name}' 区域 | 双击预览 | 重拍刷新截图"
            if picker_mode == PickerMode.RECT
            else f"点击 '{name}' 位置 | 重拍刷新截图"
        )

        mode_label = mode_lower.upper()
        self.logger.info(f"[{name}] 模式: {mode_label}")
        RelativeCoordinatePicker(
            image=image,
            title=f"[{mode_label}] {name}",
            mode=picker_mode,
            on_confirm=on_rect if picker_mode == PickerMode.RECT else on_point,
            on_retake=make_retake(),
            hint_text=hint,
        )

        # 更新 image 为最新截图（如果有重拍）
        if isinstance(result[0], TemplateRegion) and result[0].template_path:
            # 截图已保存到文件，但 image 本身没变，返回原 image
            pass

        return result[0], image

    def run_batch(self, tasks: list[tuple[str, str]]):
        """批量截取 — 依次引导用户完成每个模板

        Args:
            tasks: [(name, mode), ...]  mode 为 "rect" 或 "point"
        """
        self.logger.info("=" * 60)
        self.logger.info("CV 模板编辑器")
        self.logger.info(f"待截取: {len(tasks)} 项")
        for i, (n, m) in enumerate(tasks, 1):
            self.logger.info(f"  {i}. [{m.upper()}] {n}")
        self.logger.info("=" * 60)

        self.logger.info("正在截取游戏画面...")
        image = self.capture.capture()
        if not image:
            self.logger.error("截图失败")
            return

        all_regions = []
        all_points = []

        for name, mode in tasks:
            mode_lower = mode.lower()
            if mode_lower not in ("rect", "point"):
                self.logger.warning(f"[{name}] 未知模式 '{mode}'，跳过")
                continue

            self.logger.info(f"\n>>> [{name}] ({mode_lower}) — 请在弹出的窗口中操作")
            result, image = self.run_one(name, mode_lower, image)

            if result is None:
                self.logger.warning(f"[{name}] 已取消，跳过")
                continue

            if isinstance(result, TemplateRegion):
                all_regions.append(result)
            elif isinstance(result, ClickPoint):
                all_points.append(result)

        if all_regions or all_points:
            self.config_mgr.save_config(regions=all_regions, points=all_points)
            self._print_summary(all_regions, all_points)
        else:
            self.logger.warning("未保存任何模板")

        self.logger.info("\n完成!")

    def _print_summary(self, regions: list, points: list):
        print("=" * 60)
        print("已保存的配置")
        print("=" * 60)

        if regions:
            print("\n[ROI 模板]")
            for r in regions:
                print(f"  {r.name}: rel=({r.rel_x}, {r.rel_y}, {r.rel_w}, {r.rel_h}) | {r.template_path}")

        if points:
            print("\n[点击点]")
            for p in points:
                print(f"  {p.name}: rel=({p.rel_x}, {p.rel_y})")

        print(f"\n配置文件: {self.config_mgr.config_path}")
        print(f"其他模块加载方式:")
        print(f'  config = TemplateConfigManager().load_config()')
        print(f'  roi = config["templates"]["<模板名>"]')
        print(f'  pt  = config["click_points"]["<点名>"]')


# ─────────────────────────── CLI ───────────────────────────

def print_usage():
    print("""
CV 模板编辑器 — 通用模板截取工具

用法:
    # 交互式（不传参数，进入默认流程）
    uv run python -m src.tools.template_captor

    # 单个模板
    uv run python -m src.tools.template_captor "<名称>" <rect|point>

    # 多个模板（交替传入名称和模式）
    uv run python -m src.tools.template_captor "<名称1>" rect "<名称2>" rect "<名称3>" point

    # 从文件读取任务列表
    uv run python -m src.tools.template_captor --file <任务文件.txt>

任务文件格式 (每行: 名称 模式):
    capture_mode rect
    battle_mode rect
    confirm_button point

配置加载 (其他模块):
    from src.tools.template_captor import TemplateConfigManager
    config = TemplateConfigManager().load_config()
    roi = config["templates"]["capture_mode"]
    pt  = config["click_points"]["confirm_button"]
""")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="CV 模板编辑器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file", type=str, help="从文件读取模板任务列表")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("tasks", nargs="*", help="<名称> <模式> 交替传入，如: my_template rect")
    args = parser.parse_args()

    if not args.tasks and not args.file:
        print_usage()
        print(">>> 未指定任务，使用默认模板列表...")
        tasks = [
            ("capture_mode", "rect"),
            ("battle_mode", "rect"),
            ("battle_exit_confirm", "rect"),
            ("confirm_button", "point"),
        ]
    elif args.file:
        if not os.path.exists(args.file):
            print(f"错误: 文件不存在: {args.file}")
            sys.exit(1)
        tasks = []
        with open(args.file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    tasks.append((parts[0], parts[1]))
        if not tasks:
            print(f"错误: {args.file} 中没有有效任务")
            sys.exit(1)
    else:
        # 解析命令行参数: name1 mode1 name2 mode2 ...
        raw = args.tasks
        if len(raw) % 2 != 0:
            print(f"错误: 参数数量必须为偶数（名称+模式配对），当前: {raw}")
            sys.exit(1)
        tasks = [(raw[i], raw[i + 1]) for i in range(0, len(raw), 2)]

    captor = TemplateCaptor(debug=args.debug)
    captor.run_batch(tasks)


if __name__ == "__main__":
    main()
