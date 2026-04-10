#!/usr/bin/env python3
"""
策略层基础协议
定义 Action 枚举和 BaseStrategy 抽象类
"""

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.context import AppContext


class Action(Enum):
    """
    策略返回的动作类型
    状态机根据 Action 调度具体执行模块
    """

    NO_OP = auto()          # 什么都不做
    SEARCH_PAN = auto()     # 平移搜索（鼠标微调方向）
    MOVE_WASD = auto()      # WASD 移动（方向 + 时长）
    AIM = auto()            # 瞄准（目标位置）
    THROW = auto()          # 投掷（直接触发）
    ESCAPE = auto()         # ESC 退出战斗
    PRESS_E = auto()        # 按 E 进入捕捉模式


class BaseStrategy(ABC):
    """
    策略基类

    所有策略必须实现 execute 方法：
    - 从 ctx 读取需要的数据
    - 不做状态管理（那是 state_machine 的职责）
    - 不直接执行操作（返回 Action，由 state_machine 调度）
    """

    @abstractmethod
    def execute(self, ctx: "AppContext") -> Action:
        """
        执行策略逻辑

        Args:
            ctx: 应用上下文，包含所有运行时数据

        Returns:
            要执行的 Action
        """
        pass
