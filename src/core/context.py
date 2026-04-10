#!/usr/bin/env python3
"""
AppContext — 黑板模式
各模块通过 context 共享运行时数据，避免函数参数过长
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Any

import numpy as np


@dataclass
class AppContext:
    """
    应用上下文 — 黑板模式

    各模块（策略、检测、执行）通过这个对象共享实时数据
    """

    # ========== 配置与基础设施 ==========
    config: dict
    logger: logging.Logger

    # ========== 窗口与屏幕 ==========
    window_handle: Optional[int] = None
    window_region: Tuple[int, int, int, int] = (0, 0, 1280, 720)  # (x, y, w, h)

    # ========== 实时检测数据（每帧更新） ==========
    current_frame: Optional[np.ndarray] = None
    detections: List[Any] = field(default_factory=list)  # YOLO 检测结果
    verified_target: Optional[Any] = None  # 已验证的目标
    throw_count: int = 0  # 当前投掷次数

    # ========== 游戏状态（CV 判断） ==========
    is_capture_mode: bool = False  # 精灵球界面
    is_battle_mode: bool = False   # 战斗界面

    # ========== 状态机 ==========
    current_state: str = "SEARCH"  # 当前状态名

    # ========== 辅助字段 ==========
    last_detection_time: float = 0.0  # 上次检测时间戳
    consecutive_failures: int = 0      # 连续失败次数

    @property
    def frame_width(self) -> int:
        """获取帧宽度"""
        return self.window_region[2]

    @property
    def frame_height(self) -> int:
        """获取帧高度"""
        return self.window_region[3]

    @property
    def screen_center(self) -> Tuple[int, int]:
        """获取屏幕中心坐标"""
        return (self.frame_width // 2, self.frame_height // 2)

    def reset_throw_count(self) -> None:
        """重置投掷计数"""
        self.throw_count = 0

    def increment_throw_count(self) -> None:
        """增加投掷计数"""
        self.throw_count += 1

    def clear_target(self) -> None:
        """清除当前目标"""
        self.verified_target = None
        self.reset_throw_count()
