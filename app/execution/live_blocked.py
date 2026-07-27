from typing import Any

from app.core.exceptions import LiveTradingDisabledError
from app.execution.base import ExecutionBroker


class LiveTradingBlockedBroker(ExecutionBroker):
    @staticmethod
    def _blocked() -> None:
        raise LiveTradingDisabledError("Live trading is disabled in V1.")

    async def submit_order(self, order: Any) -> Any:
        self._blocked()

    async def cancel_order(self, order_id: Any) -> Any:
        self._blocked()

    async def get_order(self, order_id: Any) -> Any:
        self._blocked()
