from abc import ABC, abstractmethod
from typing import Any


class Strategy(ABC):
    code: str
    version: str

    @abstractmethod
    async def evaluate(self, context: Any) -> Any:
        raise NotImplementedError
