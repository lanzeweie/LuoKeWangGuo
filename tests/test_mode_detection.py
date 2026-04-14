#!/usr/bin/env python3
"""
通用模板检测实时测试脚本

功能：
- 自动加载 config/templates/templates_config.json 中的所有模板
- 实时检测所有模板的匹配状态
- 显示每个模板的置信度

运行方式：
    uv run python -m tests.test_mode_detection
    uv run python -m tests.test_mode_detection --threshold 0.8
    uv run python -m tests.test_mode_detection --debug
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.core import WindowManager
from src.core.capabilities.screen_cap import ScreenCaptureWithRegion
from src.logger import get_logger


class TemplateConfig(NamedTuple):
    """模板配置"""
    name: str
    template_path: str
    rel_x: float
    rel_y: float
    rel_w: float
    rel_h: float
    threshold: float


class TemplateDetector:
    """通用模板检测器（使用 Canny 边缘检测）"""

    def __init__(self, config: TemplateConfig, debug: bool = False):
        self.config = config
        self.debug = debug
        self.template_edge = self._load_template_edge()
        self.template_h, self.template_w = self.template_edge.shape

    def _load_template_edge(self) -> np.ndarray:
        """加载模板图像并提取边缘"""
        template_path = Path(self.config.template_path)
        if not template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_path}")

        # 加载为灰度图
        template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            raise ValueError(f"无法加载模板: {template_path}")

        # Canny 边缘检测
        template_edge = cv2.Canny(template, 50, 150)
        return template_edge

    def detect(self, frame: np.ndarray, frame_size: tuple[int, int]) -> tuple[bool, float]:
        """
        检测模板是否匹配

        Args:
            frame: 输入帧
            frame_size: 帧尺寸 (width, height)

        Returns:
            (是否匹配, 置信度)
        """
        frame_w, frame_h = frame_size

        # 计算 ROI 绝对坐标
        roi_x = int(self.config.rel_x * frame_w)
        roi_y = int(self.config.rel_y * frame_h)
        roi_w = int(self.config.rel_w * frame_w)
        roi_h = int(self.config.rel_h * frame_h)

        # 边界检查
        roi_x = max(0, min(roi_x, frame_w - 1))
        roi_y = max(0, min(roi_y, frame_h - 1))
        roi_w = max(1, min(roi_w, frame_w - roi_x))
        roi_h = max(1, min(roi_h, frame_h - roi_y))

        # 提取 ROI
        roi = frame[roi_y : roi_y + roi_h, roi_x : roi_x + roi_w]

        # 转换为灰度图
        if roi.ndim == 3:
            roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        else:
            roi_gray = roi

        # Canny 边缘检测
        roi_edge = cv2.Canny(roi_gray, 50, 150)

        # 检查尺寸
        if roi_h < self.template_h or roi_w < self.template_w:
            if self.debug:
                print(f"[{self.config.name}] ROI 过小: {roi_w}x{roi_h}, 模板: {self.template_w}x{self.template_h}")
            return False, 0.0

        # 模板匹配（边缘图）
        result = cv2.matchTemplate(roi_edge, self.template_edge, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)

        is_match = max_val >= self.config.threshold

        if self.debug:
            print(f"[{self.config.name}] 置信度: {max_val:.3f}, 匹配: {is_match}")

        return is_match, float(max_val)


def load_template_configs(config_path: Path, threshold: float) -> list[TemplateConfig]:
    """加载所有模板配置"""
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    configs = []
    templates = data.get("templates", {})

    for name, template_data in templates.items():
        config = TemplateConfig(
            name=name,
            template_path=template_data["template_path"],
            rel_x=template_data["rel_x"],
            rel_y=template_data["rel_y"],
            rel_w=template_data["rel_w"],
            rel_h=template_data["rel_h"],
            threshold=threshold,
        )
        configs.append(config)

    return configs


def main():
    parser = argparse.ArgumentParser(description="通用模板检测实时测试")
    parser.add_argument("--process-name", default="NRC-Win64-Shipping.exe", help="游戏进程名")
    parser.add_argument("--fps", type=int, default=30, help="屏幕捕获帧率")
    parser.add_argument("--threshold", type=float, default=0.7, help="匹配阈值 (0.0-1.0)")
    parser.add_argument("--config", default="config/templates/templates_config.json", help="配置文件路径")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    logger = get_logger(debug=args.debug)

    # 加载配置
    project_root = Path(__file__).parent.parent
    config_path = project_root / args.config
    template_configs = load_template_configs(config_path, args.threshold)

    if not template_configs:
        logger.error("未找到任何模板配置")
        sys.exit(1)

    logger.info(f"加载了 {len(template_configs)} 个模板: {[c.name for c in template_configs]}")

    # 初始化窗口管理器
    window_mgr = WindowManager(process_name=args.process_name, client_size=(1280, 720), debug=args.debug)
    if not window_mgr.find_window():
        logger.error("未找到游戏窗口")
        sys.exit(1)

    # dxcam 初始化
    temp_region = window_mgr.get_screen_region()
    temp_cap = ScreenCaptureWithRegion(fps=5, debug=False, region=temp_region)
    with temp_cap:
        time.sleep(0.3)

    region = window_mgr.get_screen_region()
    left, top, right, bottom = region
    game_width = right - left
    game_height = bottom - top

    logger.info(f"游戏窗口尺寸: {game_width}x{game_height}")

    cap = ScreenCaptureWithRegion(fps=args.fps, debug=False, region=region)

    # 创建所有检测器
    detectors = []
    for config in template_configs:
        try:
            detector = TemplateDetector(config, debug=args.debug)
            detectors.append(detector)
            logger.info(f"✓ 加载模板: {config.name}")
        except Exception as e:
            logger.error(f"✗ 加载模板失败 {config.name}: {e}")

    if not detectors:
        logger.error("没有可用的检测器")
        sys.exit(1)

    print(f"\n模板检测启动 (阈值: {args.threshold})")
    print(f"检测 {len(detectors)} 个模板: {', '.join([d.config.name for d in detectors])}")
    print("按 Ctrl+C 退出\n")

    # 主循环
    capture_interval = 1.0 / args.fps
    last_status = None

    try:
        with cap:
            while True:
                loop_start = time.time()
                frame = cap.capture()

                if frame is None:
                    time.sleep(0.01)
                    continue

                # 检测所有模板
                results = []
                for detector in detectors:
                    is_match, confidence = detector.detect(frame, (game_width, game_height))
                    results.append((detector.config.name, is_match, confidence))

                # 构建状态字符串
                status_parts = []
                for name, is_match, confidence in results:
                    status = "✓" if is_match else "✗"
                    status_parts.append(f"{name}: {status} ({confidence:.3f})")

                current_status = " | ".join(status_parts)

                # 只在状态变化时打印
                if current_status != last_status:
                    print(f"\r{current_status}", end="", flush=True)
                    last_status = current_status

                # 帧率限制
                elapsed = time.time() - loop_start
                if elapsed < capture_interval:
                    time.sleep(capture_interval - elapsed)

    except KeyboardInterrupt:
        print("\n\n退出")


if __name__ == "__main__":
    main()
