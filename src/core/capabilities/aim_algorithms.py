#!/usr/bin/env python3
"""
瞄准算法模块

实现 docs/aim_algorithm.md 中阶段2的算法：
- 距离补偿（Drop Compensation）
- 动量预测（Movement Predictor）
- 平滑滤波（Smooth Filter）
- 距离分类（Distance Classifier）
"""

from __future__ import annotations

import time
from typing import Tuple, Optional, List


# ═══════════════════════════════════════════════════════════
# 距离补偿（Drop Compensation）
# ═══════════════════════════════════════════════════════════


def calculate_drop_compensation(
    bbox_area: float,
    screen_area: float = 921600,
    min_compensation: int = -25,
    max_compensation: int = 0,
    far_ratio: float = 0.005,
    near_ratio: float = 0.015,
) -> int:
    """根据目标面积线性插值计算 Y 轴补偿量。

    精灵球投掷存在抛物线下落，距离越远需要向上补偿越多。

    Args:
        bbox_area: 目标边界框面积（像素²）
        screen_area: 屏幕总面积，默认 1280x720=921600
        min_compensation: 最远距离的补偿量（负值，向上），默认 -25
        max_compensation: 最近距离的补偿量，默认 0
        far_ratio: 远距离阈值（屏幕面积占比），默认 0.5%
        near_ratio: 近距离阈值（屏幕面积占比），默认 1.5%

    Returns:
        y_compensation: Y 轴补偿量（负值表示向上）
    """
    min_area = screen_area * far_ratio
    max_area = screen_area * near_ratio

    if bbox_area >= max_area:
        return max_compensation
    elif bbox_area <= min_area:
        return min_compensation

    # 线性插值
    t = (bbox_area - min_area) / (max_area - min_area)
    compensation = int(min_compensation + t * (max_compensation - min_compensation))
    return compensation


# ═══════════════════════════════════════════════════════════
# 动量预测（Movement Predictor）
# ═══════════════════════════════════════════════════════════


class MovementPredictor:
    """基于历史轨迹的目标移动预测器。

    使用最近 N 帧的位置记录，计算速度并预测精灵球飞行时间内的目标位置。
    """

    def __init__(self, history_size: int = 3, max_predict_step: int = 50):
        """
        Args:
            history_size: 保留的历史帧数
            max_predict_step: 最大预测步长限制（像素/秒），防止闪现导致预测飞走
        """
        self._history: List[Tuple[float, float, float]] = []  # [(x, y, timestamp), ...]
        self._history_size = history_size
        self._max_predict_step = max_predict_step

    def update(self, cx: float, cy: float) -> None:
        """更新目标位置历史。

        Args:
            cx: 目标中心 X
            cy: 目标中心 Y
        """
        self._history.append((cx, cy, time.time()))
        if len(self._history) > self._history_size:
            self._history.pop(0)

    def predict(self, flight_time: float = 0.5) -> Tuple[float, float]:
        """预测未来位置的瞄准点。

        Args:
            flight_time: 精灵球预估飞行时间（秒），默认 0.5s

        Returns:
            (predicted_x, predicted_y) — 预测的瞄准位置
        """
        if len(self._history) < 2:
            return self._history[-1][:2] if self._history else (0.0, 0.0)

        # 计算真实时间差 dt
        p1 = self._history[-2]
        p2 = self._history[-1]
        dt = p2[2] - p1[2]

        if dt <= 0:
            return p2[:2]

        # 计算速度（像素/秒）
        vx = (p2[0] - p1[0]) / dt
        vy = (p2[1] - p1[1]) / dt

        # 限制最大预测步长
        vx = max(-self._max_predict_step, min(self._max_predict_step, vx))
        vy = max(-self._max_predict_step, min(self._max_predict_step, vy))

        # 预测位置
        predicted_x = p2[0] + vx * flight_time
        predicted_y = p2[1] + vy * flight_time

        return (predicted_x, predicted_y)

    def reset(self) -> None:
        """重置历史记录。"""
        self._history.clear()


# ═══════════════════════════════════════════════════════════
# 平滑滤波（Smooth Filter）
# ═══════════════════════════════════════════════════════════


class SmoothFilter:
    """一阶低通滤波平滑器。

    消除 YOLO 检测输出的帧间抖动。

    公式：smoothed = last + alpha * (current - last)
    alpha 越小越平滑，但响应越慢。
    """

    def __init__(self, alpha: float = 0.3):
        """
        Args:
            alpha: 平滑系数，0 < alpha <= 1。值越小越平滑。
        """
        if not (0 < alpha <= 1):
            raise ValueError(f"alpha 必须在 (0, 1] 范围内，当前值: {alpha}")
        self._alpha = alpha
        self._last_x: Optional[float] = None
        self._last_y: Optional[float] = None

    def process(self, x: float, y: float) -> Tuple[float, float]:
        """对输入坐标进行平滑处理。

        Args:
            x: 输入 X 坐标
            y: 输入 Y 坐标

        Returns:
            (smoothed_x, smoothed_y)
        """
        if self._last_x is None:
            self._last_x = x
            self._last_y = y
            return (x, y)

        # 一阶低通滤波公式
        smoothed_x = self._last_x + self._alpha * (x - self._last_x)
        smoothed_y = self._last_y + self._alpha * (y - self._last_y)

        self._last_x = smoothed_x
        self._last_y = smoothed_y

        return (smoothed_x, smoothed_y)

    def reset(self) -> None:
        """重置平滑状态。"""
        self._last_x = None
        self._last_y = None


# ═══════════════════════════════════════════════════════════
# 距离分类（Distance Classifier）
# ═══════════════════════════════════════════════════════════


class DistanceClassifier:
    """基于屏幕面积百分比的距离分类器。

    使用 bbox 面积占屏幕面积的百分比来判断距离状态，
    替代绝对像素阈值，适配不同分辨率。
    """

    def __init__(
        self,
        screen_width: int = 1280,
        screen_height: int = 720,
        far_ratio: float = 0.005,
        near_ratio: float = 0.015,
    ):
        """
        Args:
            screen_width: 屏幕宽度
            screen_height: 屏幕高度
            far_ratio: FAR 阈值（屏幕面积占比），默认 0.5%
            near_ratio: CLOSE 阈值（屏幕面积占比），默认 1.5%
        """
        self._screen_area = screen_width * screen_height
        self._far_threshold = self._screen_area * far_ratio     # < 0.5% → FAR
        self._near_threshold = self._screen_area * near_ratio   # > 1.5% → CLOSE

    @property
    def screen_area(self) -> int:
        return self._screen_area

    @property
    def far_threshold(self) -> float:
        return self._far_threshold

    @property
    def near_threshold(self) -> float:
        return self._near_threshold

    def classify(self, bbox_area: float) -> str:
        """根据 bbox 面积分类距离状态。

        Args:
            bbox_area: 目标边界框面积

        Returns:
            "FAR" / "MEDIUM" / "CLOSE"
        """
        if bbox_area < self._far_threshold:
            return "FAR"
        elif bbox_area < self._near_threshold:
            return "MEDIUM"
        else:
            return "CLOSE"
