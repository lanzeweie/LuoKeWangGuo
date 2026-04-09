#!/usr/bin/env python3
"""
核心业务模块包
"""

from .window_mgr import WindowManager
from .screen_cap import ScreenCapture
from .detection import ObjectDetector, DetectionResult
from .input_sim import InputSimulator
from .game_logic import GameLogic
from .state_machine import StateMachine, State

__all__ = [
    "WindowManager",
    "ScreenCapture",
    "ObjectDetector",
    "DetectionResult",
    "InputSimulator",
    "GameLogic",
    "StateMachine",
    "State",
]
