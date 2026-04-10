"""策略层 - 业务决策

定义"怎么做"：搜索策略、导航策略、瞄准策略。
策略本身无状态，状态由 StateMachine 管理。
"""

from src.strategies.base import Action, BaseStrategy
from src.strategies.search_strategy import SearchStrategy
from src.strategies.navigation_strategy import NavigationStrategy
from src.strategies.aim_strategy import AimStrategy

__all__ = [
    "Action",
    "BaseStrategy",
    "SearchStrategy",
    "NavigationStrategy",
    "AimStrategy",
]
