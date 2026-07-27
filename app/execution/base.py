from abc import ABC, abstractmethod
from typing import Any


class ExecutionBroker(ABC):
    @abstractmethod
    async def submit_order(self, order: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, order_id: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def get_order(self, order_id: Any) -> Any:
        raise NotImplementedError
