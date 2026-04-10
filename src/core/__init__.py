#!/usr/bin/env python3
"""能力层 - 底层工具库

提供基础能力：屏幕捕获、检测、窗口管理、输入模拟、覆盖层、模式检测、目标评分等。
"""

from .capabilities.screen_cap import ScreenCapture
from .capabilities.detection import ObjectDetector
from .capabilities.window_mgr import WindowManager
from .capabilities.sendinput_sim import SendInputSimulator
from .capabilities.input_sim import InputSimulator
from .capabilities.layered_overlay import LayeredOverlay
from .capabilities.gdi_overlay import GDIOverlay
from .capabilities.capture_mode_detector import CaptureModeDetector
from .capabilities.battle_mode_detector import BattleModeDetector
from .capabilities.target_scoring import TargetScorer, TargetScore
from .capabilities.target_verifier import TargetVerifier
from .capabilities.template_loader import TemplateLoader
from .state_machine import StateMachine
from .game_logic import GameLogic

__all__ = [
    "ScreenCapture",
    "ObjectDetector",
    "WindowManager",
    "SendInputSimulator",
    "InputSimulator",
    "LayeredOverlay",
    "GDIOverlay",
    "CaptureModeDetector",
    "BattleModeDetector",
    "TargetScorer",
    "TargetScore",
    "TargetVerifier",
    "TemplateLoader",
    "StateMachine",
    "GameLogic",
]
