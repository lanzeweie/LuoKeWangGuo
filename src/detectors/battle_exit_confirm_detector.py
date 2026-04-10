#!/usr/bin/env python3
"""
战斗逃跑确认框检测器

使用灰度图模板匹配检测战斗逃跑确认框。
ROI 区域从 templates_config.json 动态加载。

与其他检测器的区别：
- 使用灰度匹配而非 Canny 边缘检测
- 检测的是弹窗而非固定界面元素
"""

import json
import os
from typing import Tuple

import cv2
import numpy as np

from src.logger import get_logger

# 默认配置
DEFAULT_ROI_REL_X = 0.3
DEFAULT_ROI_REL_Y = 0.35
DEFAULT_ROI_REL_W = 0.4
DEFAULT_ROI_REL_H = 0.3
MATCH_THRESHOLD = 0.65

# 配置路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "templates", "templates_config.json")


def _load_roi_from_config(name: str) -> Tuple[float, float, float, float]:
    """从配置文件加载 ROI（相对坐标）"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        roi = config.get("templates", {}).get(name, {})
        return (
            roi.get("rel_x", DEFAULT_ROI_REL_X),
            roi.get("rel_y", DEFAULT_ROI_REL_Y),
            roi.get("rel_w", DEFAULT_ROI_REL_W),
            roi.get("rel_h", DEFAULT_ROI_REL_H),
        )
    except Exception:
        return (DEFAULT_ROI_REL_X, DEFAULT_ROI_REL_Y, DEFAULT_ROI_REL_W, DEFAULT_ROI_REL_H)


class BattleExitConfirmDetector:
    """检测战斗逃跑确认框。

    使用灰度图模板匹配，适合检测弹窗类界面元素。
    """

    def __init__(self, template_path: str, debug: bool = False):
        """
        Args:
            template_path: 模板图片路径
            debug: 是否启用调试日志
        """
        self.debug = debug
        self.logger = get_logger(debug=debug)

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"模板图不存在: {template_path}")

        # 加载模板并转为灰度图
        raw = cv2.imread(template_path)
        if raw is None:
            raise ValueError(f"无法读取模板图: {template_path}")

        self.template_gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
        self.template_h, self.template_w = self.template_gray.shape

        # 加载 ROI 配置
        self.rel_x, self.rel_y, self.rel_w, self.rel_h = _load_roi_from_config("battle_exit_confirm")

        self.logger.info(
            f"战斗逃跑确认框模板加载完成: {template_path} "
            f"(灰度 {self.template_gray.shape})"
        )

    def _compute_roi(self, frame_w: int, frame_h: int) -> Tuple[int, int, int, int]:
        """根据帧尺寸计算 ROI 绝对坐标"""
        return (
            int(self.rel_x * frame_w),
            int(self.rel_y * frame_h),
            int(self.rel_w * frame_w),
            int(self.rel_h * frame_h),
        )

    def is_confirm_box_visible(self, frame: np.ndarray) -> Tuple[bool, float]:
        """检测当前帧是否显示确认框。

        Args:
            frame: 当前帧 (BGR)

        Returns:
            (is_visible, confidence)
        """
        frame_h, frame_w = frame.shape[:2]
        rx, ry, rw, rh = self._compute_roi(frame_w, frame_h)

        # 边界检查
        if rx < 0 or ry < 0 or rx + rw > frame_w or ry + rh > frame_h or rw <= 0 or rh <= 0:
            return False, 0.0

        # 提取 ROI 并转灰度
        roi = frame[ry:ry + rh, rx:rx + rw]
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # 模板匹配
        result = cv2.matchTemplate(roi_gray, self.template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)

        is_match = max_val >= MATCH_THRESHOLD

        if self.debug:
            self.logger.debug_msg(
                f"确认框匹配: confidence={max_val:.4f} "
                f"(阈值 {MATCH_THRESHOLD}) → {'是' if is_match else '否'}"
            )

        return is_match, float(max_val)


if __name__ == "__main__":
    # 测试代码
    import sys

    template_path = os.path.join(PROJECT_ROOT, "data", "templates", "battle_exit_confirm.png")

    if not os.path.exists(template_path):
        print(f"模板不存在: {template_path}")
        sys.exit(1)

    detector = BattleExitConfirmDetector(template_path, debug=True)

    print(f"模板已加载: {detector.template_w}x{detector.template_h}")
    print(f"ROI 配置: rel=({detector.rel_x}, {detector.rel_y}, {detector.rel_w}, {detector.rel_h})")