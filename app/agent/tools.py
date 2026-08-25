import hashlib
import time
from datetime import datetime, timezone

from app.core.errors import AppError, ControlledServiceError, ErrorCode, map_exception
from app.database.models import AgentToolAuditRecord
from app.dashboard.stock_analysis import StockAnalysisService
from app.market_context.service import MarketContextService
from app.paper_runtime.query import PaperRuntimeQueryService
from app.portfolio_center.service import HoldingService, PortfolioService
from app.qmr_exit.service import QmrExitService
from app.qmr_live.service import QmrLiveSignalService
from app.symbol_registry.service import SymbolRegistryService


class AgentToolService:
    WHITELIST = frozenset({
        "analyze_symbol", "get_market_context", "get_sector_context",
        "get_qmr_analysis", "get_qmr_status", "get_money_flow", "get_position",
        "get_exit_risk", "get_recent_signals", "get_paper_orders",
        "get_order_status", "record_user_trade",
    })

    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.registry = SymbolRegistryService(db, settings.symbol_registry_config_file)

    def call(self, tool_name, chat_id="", intent="UNKNOWN", symbol=None, **arguments):
        started = time.monotonic()
        success, error_code = False, None
        if tool_name not in self.WHITELIST:
            error = AppError(ErrorCode.REAL_TRADING_BLOCKED, "agent_tools",
                             "Tool is not approved", symbol=symbol)
            self._audit(chat_id, intent, tool_name, symbol, started, False, error.error_code.value)
            raise ControlledServiceError(error)
        try:
            result = getattr(self, tool_name)(symbol=symbol, **arguments)
            success = True
            return result
        except ControlledServiceError as exc:
            error_code = exc.error.error_code.value
            raise
        except Exception as exc:
            mapped = map_exception(exc, "agent_tools", symbol=symbol)
            error_code = mapped.error_code.value
            raise ControlledServiceError(mapped) from exc
        finally:
            self._audit(chat_id, intent, tool_name, symbol, started, success, error_code)

    def _canonical(self, symbol):
        resolved = self.registry.resolve(symbol, allow_unknown=True)
        if resolved["status"] == "AMBIGUOUS":
            raise ControlledServiceError(AppError(
                ErrorCode.SYMBOL_NOT_FOUND, "symbol_registry", "Ambiguous company name"))
        return resolved["item"]

    def analyze_symbol(self, symbol=None, execution_requested=False, **_):
        item = self._canonical(symbol)
        if execution_requested:
            return {"symbol": item["symbol"], "execution_blocked": True,
                    "message": "Trade Companion 不提交真实订单；可以分析并记录你的自主交易。"}
        result = StockAnalysisService(self.db, self.settings).get(item["symbol"])
        context = MarketContextService(self.db, self.settings).current_for_symbol(item["symbol"])
        result["instrument"] = item
        result["global"] = context.get("global")
        result["sector"] = context.get("sector")
        result["data_quality"] = {
            "analysis": result.get("data_status"),
            "global": (context.get("global") or {}).get("data_quality"),
            "sector": (context.get("sector") or {}).get("data_quality"),
        }
        return result

    def get_market_context(self, symbol=None, **_):
        item = self._canonical(symbol or "QQQ")
        return MarketContextService(self.db, self.settings).current_for_symbol(item["symbol"])

    def get_sector_context(self, symbol=None, **_):
        item = self._canonical(symbol)
        context = MarketContextService(self.db, self.settings).current_for_symbol(item["symbol"])
        return {"symbol": item["symbol"], "sector": item.get("sector"),
                "benchmarks": [item.get("primary_benchmark"), item.get("secondary_benchmark")],
                "context": context.get("sector")}

    def get_qmr_analysis(self, symbol=None, **_):
        item = self._canonical(symbol)
        return StockAnalysisService(self.db, self.settings).get(item["symbol"])

    def get_qmr_status(self, symbol=None, **kwargs):
        return self.get_qmr_analysis(symbol, **kwargs)

    def get_money_flow(self, symbol=None, **_):
        result = self.get_qmr_analysis(symbol)
        return {"symbol": result["symbol"], "money_flow": result.get("money_flow"),
                "data_status": result.get("data_status")}

    def get_position(self, symbol=None, **_):
        item = self._canonical(symbol) if symbol else None
        return {"positions": PaperRuntimeQueryService(self.db).positions(
            item["symbol"] if item else None)}

    def get_exit_risk(self, symbol=None, **_):
        item = self._canonical(symbol)
        service = QmrExitService(self.db, self.settings)
        rows = service.repository.list(symbol=item["symbol"], limit=1)
        return {"symbol": item["symbol"], "exit": service.serialize(rows[0]) if rows else None}

    def get_recent_signals(self, symbol=None, signal_id=None, **_):
        service = QmrLiveSignalService(self.db, self.settings)
        if signal_id:
            signal, performance = service.query(signal_id)
            return {"signal": self._row(signal), "performance": [self._row(row) for row in performance]}
        item = self._canonical(symbol) if symbol else None
        rows, _ = service.repository.list_signals(symbol=item["symbol"] if item else None, limit=10)
        return {"signals": [self._row(row) for row in rows]}

    def get_order_status(self, symbol=None, order_id=None, signal_id=None, **_):
        if signal_id:
            signal = QmrLiveSignalService(self.db, self.settings).required(signal_id)
            symbol = signal.symbol
            snapshot = signal.signal_snapshot_json
        else:
            snapshot = None
        item = self._canonical(symbol) if symbol else None
        orders = PaperRuntimeQueryService(self.db).orders(
            item["symbol"] if item else None, order_id=order_id, limit=10)
        return {"symbol": item["symbol"] if item else None, "signal_id": signal_id,
                "signal_snapshot": snapshot, "orders": orders,
                "reason": self._order_reason(orders)}

    def get_paper_orders(self, symbol=None, **kwargs):
        return self.get_order_status(symbol, **kwargs)

    def record_user_trade(self, symbol=None, user_id=None, quantity=None,
                          average_cost=None, **_):
        item = self._canonical(symbol)
        owner = str(user_id or "telegram-user")
        portfolios = PortfolioService(self.db)
        portfolio = portfolios.get_default(owner)
        if portfolio is None:
            portfolio = portfolios.create_portfolio(owner, "My Portfolio", is_default=True)
        row = HoldingService(self.db).open_holding(
            portfolio.id, item["symbol"], item.get("market", "US"), "LONG",
            quantity, average_cost, notes="Recorded from Telegram; not a broker fill",
            owner_id=owner)
        return {"recorded": True, "holding_id": row.id, "symbol": row.symbol,
                "quantity": row.quantity, "average_cost": row.average_cost,
                "broker_order_created": False}

    def _audit(self, chat_id, intent, tool_name, symbol, started, success, error_code):
        self.db.add(AgentToolAuditRecord(
            chat_id_hash=hashlib.sha256(str(chat_id).encode()).hexdigest(),
            intent=str(intent), tool_name=tool_name, symbol=symbol,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            success=success, error_code=error_code))
        self.db.commit()

    @staticmethod
    def _row(row):
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}

    @staticmethod
    def _order_reason(orders):
        if not orders:
            return "NO_PAPER_ORDER"
        latest = orders[0]
        return latest.get("rejection_code") or (latest.get("metadata_json") or {}).get("reason") or latest["status"]
