#!/usr/bin/env python3
"""
捕捉模式检测器

通过 Canny 边缘检测 + 模板匹配识别游戏是否处于精灵球捕捉界面。
ROI 区域从 templates_config.json 动态加载，避免硬编码。

使用边缘检测避免背景颜色干扰。
"""

import json
import os
import time
from typing import Tuple

import cv2
import numpy as np

from src.detectors.config_loader import load_roi_relative, rel_to_abs

MATCH_THRESHOLD = 0.80
TIMEOUT_SECONDS = 3.0

# 初始化时加载相对坐标（无 frame_size 时无法换算）
_roi_rel = load_roi_relative("capture_mode")
REL_ROI_X, REL_ROI_Y, REL_ROI_W, REL_ROI_H = _roi_rel


class CaptureModeDetector:
    """检测游戏是否处于精灵球捕捉模式。

    流程：
    1. 初始化时加载模板图 → 灰度化 → Canny 边缘提取
    2. 运行时每帧截取 ROI → 灰度化 → Canny 边缘提取
    3. cv2.matchTemplate 匹配，返回 (is_match, confidence)

    支持动态分辨率：构造函数可传入 frame_size，ROI 会根据相对坐标自动换算
    """

    def __init__(self, template_path: str, frame_size: Tuple[int, int] = None, debug: bool = False):
        """
        Args:
            template_path: 模板图片路径
            frame_size: 当前帧尺寸 (width, height)，用于动态换算 ROI
            debug: 是否启用调试日志
        """
        self.debug = debug
        self.logger = get_logger(debug=debug)
        self.frame_size = frame_size

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"模板图不存在: {template_path}")

        # 加载模板并生成边缘模板
        raw = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if raw is None:
            raise ValueError(f"无法读取模板图: {template_path}")

        self.template_edge = cv2.Canny(raw, 50, 150)
        self.template_h, self.template_w = self.template_edge.shape
        self.logger.info(
            f"捕捉模式模板加载完成: {template_path} "
            f"(原始 {raw.shape}, 边缘 {self.template_edge.shape})"
        )

    def _get_roi(self) -> Tuple[int, int, int, int]:
        """获取当前帧尺寸对应的 ROI 坐标"""
        if self.frame_size is not None:
            rel = load_roi_relative("capture_mode")
            return rel_to_abs(rel, self.frame_size)
        # 无 frame_size 时使用默认的相对坐标（适用于 1280x720）
        return (int(REL_ROI_X * 1280), int(REL_ROI_Y * 720), int(REL_ROI_W * 1280), int(REL_ROI_H * 720))

    def _extract_roi_edge(self, frame: np.ndarray) -> np.ndarray:
        """从帧中截取 ROI 区域并提取边缘。

        Args:
            frame: 完整帧 (HxWxC 或 HxW)

        Returns:
            ROI 区域的 Canny 边缘图
        """
        # 获取当前帧对应的 ROI
        roi_x, roi_y, roi_w, roi_h = self._get_roi()
        h, w = frame.shape[:2]

        # 边界保护
        x1 = max(0, roi_x)
        y1 = max(0, roi_y)
        x2 = min(w, roi_x + roi_w)
        y2 = min(h, roi_y + roi_h)

        roi = frame[y1:y2, x1:x2]

        # 边界保护：确保 ROI 区域有效
        if roi.size == 0:
            self.logger.warning(
                f"ROI 区域为空: ({x1},{y1})->({x2},{y2}), 帧尺寸 {frame.shape[:2]}"
            )
            return np.zeros((10, 10), dtype=np.uint8)

        if roi.ndim == 3:
            roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        else:
            roi_gray = roi

        return cv2.Canny(roi_gray, 50, 150)

    def is_capture_mode(self, frame: np.ndarray) -> Tuple[bool, float]:
        """检测当前帧是否处于捕捉模式。

        Args:
            frame: 当前帧

        Returns:
            (is_capture_mode, confidence)
        """
        roi_edge = self._extract_roi_edge(frame)
        roi_h, roi_w = roi_edge.shape

        if roi_h < self.template_h or roi_w < self.template_w:
            self.logger.warning(
                f"ROI 区域过小 ({roi_w}x{roi_h})，"
                f"模板大小 ({self.template_w}x{self.template_h})"
            )
            return False, 0.0

        # 模板匹配
        result = cv2.matchTemplate(
            roi_edge, self.template_edge, cv2.TM_CCOEFF_NORMED
        )
        _, max_val, _, _ = cv2.minMaxLoc(result)

        is_match = max_val >= MATCH_THRESHOLD

        if self.debug:
            self.logger.debug_msg(
                f"捕捉模式匹配: confidence={max_val:.4f} "
                f"(阈值 {MATCH_THRESHOLD}) → {'是' if is_match else '否'}"
            )

        return is_match, float(max_val)

    def wait_for_capture_mode(
        self, frame_provider, timeout: float = TIMEOUT_SECONDS
    ) -> Tuple[bool, float]:
        """等待进入捕捉模式（轮询检测直到超时）。

        Args:
            frame_provider: 可调用对象，返回当前帧
            timeout: 最大等待时间（秒）

        Returns:
            (is_detected, best_confidence)
        """
        start = time.time()
        best_conf = 0.0

        while time.time() - start < timeout:
            frame = frame_provider()
            if frame is None:
                continue

            matched, conf = self.is_capture_mode(frame)
            best_conf = max(best_conf, conf)

            if matched:
                self.logger.success(
                    f"检测到捕捉模式 (confidence={conf:.4f})"
                )
                return True, conf

        self.logger.warning(
            f"等待捕捉模式超时 ({timeout}s)，最佳匹配={best_conf:.4f}"
        )
        return False, best_conf


def test_capture_mode_detector() -> bool:
    """测试捕捉模式检测器。

    用模板图本身作为输入，验证自匹配能达到高置信度。
    """
    print("=" * 50)
    print("捕捉模式检测器测试")
    print("=" * 50)

    template_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "templates", "capture_mode.png"
    )

    if not os.path.exists(template_path):
        print(f"跳过测试: 模板图不存在 ({template_path})")
        return True

    detector = CaptureModeDetector(template_path, debug=True)

    # 测试 1: 模板图自匹配应该达到高置信度
    print("\n[测试1] 模板图自匹配...")
    raw = cv2.imread(template_path)
    if raw is None:
        print("  [FAIL] 无法读取模板图")
        return False

    # 创建一个 1280x720 的帧，把模板放到 ROI 区域内
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    th, tw = raw.shape[:2]
    frame[ROI_Y:ROI_Y + th, ROI_X:ROI_X + tw] = raw

    matched, conf = detector.is_capture_mode(frame)
    print(f"  置信度: {conf:.4f}, 匹配: {matched}")

    ok = conf >= MATCH_THRESHOLD
    print(f"  结果: {'PASS' if ok else 'FAIL'}")

    print(f"\n{'=' * 50}")
    return ok


if __name__ == "__main__":
    test_capture_mode_detector()
