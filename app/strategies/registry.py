from typing import Dict

from app.strategies.base import Strategy


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: Dict[str, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        self._strategies[strategy.code] = strategy

    def get(self, code: str) -> Strategy:
        return self._strategies[code]
