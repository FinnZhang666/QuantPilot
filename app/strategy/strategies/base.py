from abc import ABC, abstractmethod

from app.strategy.models import SignalEvaluation, StrategyInput


class CandidateStrategy(ABC):
    @abstractmethod
    def evaluate(self, value: StrategyInput) -> SignalEvaluation:
        raise NotImplementedError
