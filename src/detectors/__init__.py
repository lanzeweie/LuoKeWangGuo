"""模板检测器模块

所有基于 OpenCV 模板匹配的游戏界面检测器。

可用检测器：
- CaptureModeDetector: 检测精灵球捕捉界面
- BattleModeDetector: 检测战斗界面
- BattleExitConfirmDetector: 检测战斗逃跑确认框
"""

from .capture_mode_detector import CaptureModeDetector
from .battle_mode_detector import BattleModeDetector
from .battle_exit_confirm_detector import BattleExitConfirmDetector

__all__ = [
    "CaptureModeDetector",
    "BattleModeDetector",
    "BattleExitConfirmDetector",
]