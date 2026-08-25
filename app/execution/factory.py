from app.core.enums import TradingMode
from app.execution.internal_paper import InternalPaperBroker
from app.execution.live_blocked import LiveTradingBlockedBroker
from app.execution.moomoo_paper import MoomooPaperBroker


def execution_broker(settings, db=None, manager=None):
    """Fail-closed broker selection; there is no real-account fallback."""
    mode = settings.trading_mode
    if mode == TradingMode.INTERNAL_PAPER:
        if not settings.enable_internal_paper or db is None:
            return LiveTradingBlockedBroker()
        return InternalPaperBroker(db, settings.default_slippage_bps)
    if mode == TradingMode.MOOMOO_PAPER:
        return MoomooPaperBroker(settings, manager)
    return LiveTradingBlockedBroker()
