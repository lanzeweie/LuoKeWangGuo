#!/usr/bin/env python3
"""能力层 - 底层工具库

提供基础能力：屏幕捕获、检测、窗口管理、输入模拟、覆盖层、模式检测、目标评分等。

注意：部分检测器已移至 src.detectors：
- CaptureModeDetector -> src.detectors.CaptureModeDetector
- BattleModeDetector -> src.detectors.BattleModeDetector
- BattleExitConfirmDetector -> src.detectors.BattleExitConfirmDetector

为保持向后兼容，以下导入仍然可用（实际实现已移至 detectors/ 目录）：
"""

from .capabilities.screen_cap import ScreenCapture
from .capabilities.detection import ObjectDetector
from .capabilities.window_mgr import WindowManager
from .capabilities.interception_sim import InterceptionSimulator
from .capabilities.sendinput_sim import SendInputSimulator  # Legacy
from .capabilities.layered_overlay import LayeredOverlay
from .capabilities.target_scoring import TargetScorer, TargetScore
from .capabilities.target_verifier import TargetVerifier
from .capabilities.template_loader import TemplateLoader
from .state_machine import StateMachine
from .game_logic import GameLogic

# 向后兼容：检测器从 src.detectors 重新导出
# 实际实现已移至 src/detectors/ 目录
from src.detectors import CaptureModeDetector
from src.detectors import BattleModeDetector

__all__ = [
    "ScreenCapture",
    "ObjectDetector",
    "WindowManager",
    "InterceptionSimulator",
    "SendInputSimulator",  # Legacy
    "LayeredOverlay",
    "CaptureModeDetector",
    "BattleModeDetector",
    "TargetScorer",
    "TargetScore",
    "TargetVerifier",
    "TemplateLoader",
    "StateMachine",
    "GameLogic",
]
