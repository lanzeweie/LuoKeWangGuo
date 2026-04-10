#!/usr/bin/env python3
"""
配置加载工具 - 公共函数

统一处理模板配置的加载和坐标换算
"""

import json
import os
from typing import Tuple

# 配置文件路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "..", "data", "templates", "templates_config.json")

# 各模板的默认相对坐标（配置文件缺失时使用）
DEFAULT_REL_ROI = {
    "capture_mode": (0.9, 0.8, 0.05, 0.05),
    "battle_mode": (0.9, 0.7, 0.05, 0.05),
    "battle_exit_confirm": (0.4, 0.3, 0.2, 0.15),
}


def load_roi_relative(name: str) -> Tuple[float, float, float, float]:
    """从配置文件加载相对坐标 (0.0-1.0)

    Args:
        name: 模板名称 (capture_mode, battle_mode, battle_exit_confirm)

    Returns:
        (rel_x, rel_y, rel_w, rel_h) 相对坐标
    """
    defaults = DEFAULT_REL_ROI.get(name, (0.0, 0.0, 1.0, 1.0))

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        tpl = config.get("templates", {}).get(name, {})
        return (
            tpl.get("rel_x", defaults[0]),
            tpl.get("rel_y", defaults[1]),
            tpl.get("rel_w", defaults[2]),
            tpl.get("rel_h", defaults[3]),
        )
    except Exception:
        return defaults


def rel_to_abs(
    rel: Tuple[float, float, float, float],
    frame_size: Tuple[int, int]
) -> Tuple[int, int, int, int]:
    """相对坐标转换为绝对坐标

    Args:
        rel: (rel_x, rel_y, rel_w, rel_h) 相对坐标
        frame_size: (width, height) 帧尺寸

    Returns:
        (abs_x, abs_y, abs_w, abs_h) 绝对坐标
    """
    rel_x, rel_y, rel_w, rel_h = rel
    fw, fh = frame_size
    return (
        int(rel_x * fw),
        int(rel_y * fh),
        int(rel_w * fw),
        int(rel_h * fh),
    )


def load_click_point(name: str) -> Tuple[float, float]:
    """从配置文件加载点击点相对坐标

    Args:
        name: 点击点名称 (如 confirm_button)

    Returns:
        (rel_x, rel_y) 相对坐标
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        point = config.get("click_points", {}).get(name, {})
        return (
            point.get("rel_x", 0.5),
            point.get("rel_y", 0.5),
        )
    except Exception:
        return (0.5, 0.5)
