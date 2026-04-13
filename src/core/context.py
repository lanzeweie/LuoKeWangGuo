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

    # ========== 瞄准投掷依赖 ==========
    # 这些引用用于在持续瞄准期间获取实时目标
    screen_capture: Optional[Any] = None  # ScreenCapture 实例
    detection_overlay: Optional[Any] = None  # DetectionOverlay 实例
    aim_and_throw: Optional[Any] = None  # AimAndThrow 实例

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

    def get_realtime_target_center(self) -> Optional[Tuple[int, int]]:
        """
        获取实时目标的中心位置（用于持续瞄准期间）

        此方法会在 aim_and_throw 的 3 秒瞄准循环中持续被调用，
        用于获取最新的 YOLO 检测结果。

        Returns:
            (center_x, center_y) 目标中心坐标，或 None
        """
        if self.screen_capture is None or self.detection_overlay is None:
            self._log_warning("screen_capture 或 detection_overlay 未初始化")
            return None

        # 获取当前帧
        current_frame = self.screen_capture.capture()
        if current_frame is None:
            self._log_debug("获取帧失败，返回 None")
            return None

        # 更新 DetectionOverlay
        try:
            tracked = self.detection_overlay.update(current_frame)
        except Exception as e:
            self._log_warning(f"DetectionOverlay 更新失败: {e}")
            return None

        # 过滤出活跃状态的目标
        active_targets = [t for t in tracked if t.state == "active"]
        if not active_targets:
            self._log_debug("无活跃目标")
            return None

        # 返回第一个活跃目标的中心
        target = active_targets[0]
        cx = int((target.bbox[0] + target.bbox[2]) / 2)
        cy = int((target.bbox[1] + target.bbox[3]) / 2)

        self._log_debug(f"实时目标中心: ({cx}, {cy})")

        return cx, cy

    def _log_debug(self, message: str) -> None:
        """兼容的 debug 日志"""
        if hasattr(self.logger, 'debug_msg'):
            self.logger.debug_msg(message)
        elif self.logger:
            self.logger.debug(message)

    def _log_warning(self, message: str) -> None:
        """兼容的 warning 日志"""
        if hasattr(self.logger, 'warning'):
            self.logger.warning(message)
        elif self.logger:
            self.logger.warning(message)

    def execute_aim_and_throw(
        self,
        target: Any,
        fine_tune_ms: int = 500,
    ) -> bool:
        """
        执行瞄准投掷（集成持续瞄准逻辑）

        Args:
            target: 初始目标（TargetScore 对象）
            fine_tune_ms: 微调时长（毫秒）

        Returns:
            True 表示成功，False 表示失败
        """
        if self.aim_and_throw is None:
            self.logger.error("aim_and_throw 未初始化")
            return False

        return self.aim_and_throw.aim_and_throw(
            target=target,
            screen_width=self.frame_width,
            screen_height=self.frame_height,
            fine_tune_ms=fine_tune_ms,
            get_target_func=self.get_realtime_target_center,
        )
