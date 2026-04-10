#!/usr/bin/env python3
"""
战斗逃跑确认框检测器

使用灰度图模板匹配检测战斗逃跑确认框。
ROI 区域从 templates_config.json 动态加载。

与其他检测器的区别：
- 使用灰度匹配而非 Canny 边缘检测
- 检测的是弹窗而非固定界面元素
"""

import os
from typing import Tuple

import cv2
import numpy as np

from src.logger import get_logger
from src.detectors.config_loader import load_roi_relative, rel_to_abs

MATCH_THRESHOLD = 0.65

# 初始化时加载相对坐标
_roi_rel = load_roi_relative("battle_exit_confirm")
REL_ROI_X, REL_ROI_Y, REL_ROI_W, REL_ROI_H = _roi_rel


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

        self.logger.info(
            f"战斗逃跑确认框模板加载完成: {template_path} "
            f"(灰度 {self.template_gray.shape})"
        )

    def _compute_roi(self, frame_w: int, frame_h: int) -> Tuple[int, int, int, int]:
        """根据帧尺寸计算 ROI 绝对坐标"""
        return rel_to_abs((REL_ROI_X, REL_ROI_Y, REL_ROI_W, REL_ROI_H), (frame_w, frame_h))

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