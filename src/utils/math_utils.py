#!/usr/bin/env python3
"""
纯数学工具函数
不依赖任何游戏逻辑，只做数学计算
"""

import math
from typing import Tuple


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """
    计算两点之间的欧氏距离

    Args:
        p1: 第一个点 (x, y)
        p2: 第二个点 (x, y)

    Returns:
        两点之间的距离
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.sqrt(dx ** 2 + dy ** 2)


def center_offset(
    point: Tuple[int, int],
    screen_w: int,
    screen_h: int
) -> Tuple[int, int]:
    """
    计算点相对于屏幕中心的偏移量

    Args:
        point: 目标点 (x, y)
        screen_w: 屏幕宽度
        screen_h: 屏幕高度

    Returns:
        (offset_x, offset_y) - 相对于中心的偏移量
    """
    center_x = screen_w // 2
    center_y = screen_h // 2
    offset_x = point[0] - center_x
    offset_y = point[1] - center_y
    return offset_x, offset_y


def bbox_area(x1: int, y1: int, x2: int, y2: int) -> float:
    """
    计算边界框面积

    Args:
        x1: 左上角 x 坐标
        y1: 左上角 y 坐标
        x2: 右下角 x 坐标
        y2: 右下角 y 坐标

    Returns:
        边界框面积（像素）
    """
    width = abs(x2 - x1)
    height = abs(y2 - y1)
    return width * height


def angle_between(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """
    计算从 p1 到 p2 的角度（弧度）

    Args:
        p1: 起点 (x, y)
        p2: 终点 (x, y)

    Returns:
        角度（弧度），范围 [-π, π]
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.atan2(dy, dx)


def angle_to_degrees(angle_rad: float) -> float:
    """
    将弧度转换为角度，并归一化到 [0, 360)

    Args:
        angle_rad: 角度（弧度）

    Returns:
        角度（度），范围 [0, 360)
    """
    angle_deg = math.degrees(angle_rad)
    return (angle_deg + 360) % 360
