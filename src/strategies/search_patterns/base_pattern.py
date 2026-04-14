#!/usr/bin/env python3
"""
搜索模式基类与命令结构。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict

from src.strategies.base import Action


@dataclass
class SearchCommand:
    """搜索动作命令。"""

    action: Action
    params: Dict[str, Any] = field(default_factory=dict)
    label: str = ""


class BaseSearchPattern(ABC):
    """搜索模式基类。"""

    name: str = "base"

    def __init__(self) -> None:
        self._finished = False

    def reset(self) -> None:
        self._finished = False

    def is_finished(self) -> bool:
        return self._finished

    @abstractmethod
    def next_command(self, ctx) -> SearchCommand:
        """生成下一条搜索动作命令。"""
