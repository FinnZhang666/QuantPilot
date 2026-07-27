from typing import Any

from app.decisions.models import Decision


class DecisionEngine:
    async def evaluate(self, signal: Any, portfolio: Any, market_context: Any) -> Decision:
        return Decision(approved=False, reason="Decision rules are not implemented in Sprint 00.")
