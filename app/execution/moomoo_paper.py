from typing import Any

from app.execution.base import ExecutionBroker


class MoomooPaperBroker(ExecutionBroker):
    """Sprint 00 placeholder. It never connects or submits automatically."""

    async def submit_order(self, order: Any) -> Any:
        raise NotImplementedError("Moomoo paper order submission is outside Sprint 00.")

    async def cancel_order(self, order_id: Any) -> Any:
        raise NotImplementedError("Moomoo paper cancellation is outside Sprint 00.")

    async def get_order(self, order_id: Any) -> Any:
        raise NotImplementedError("Moomoo paper order lookup is outside Sprint 00.")
