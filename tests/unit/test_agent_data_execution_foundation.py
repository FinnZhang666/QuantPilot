import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.agent.intents import AgentIntent, parse_intent
from app.agent.tools import AgentToolService
from app.core.config import Settings
from app.core.enums import TradingMode
from app.core.errors import ControlledServiceError, ErrorCode, map_exception
from app.data_manager import DataFreshness, DataRequestManager
from app.database.models import AgentToolAuditRecord, PortfolioHolding
from app.execution.factory import execution_broker
from app.execution.live_blocked import LiveTradingBlockedBroker
from app.execution.moomoo_paper import MoomooPaperBroker
from app.execution.order_audit import OrderStateAuditService
from app.execution.state_machine import normalize_broker_status, validate_transition
from app.symbol_registry import SymbolRegistryService


def test_unified_error_mapping_and_safe_message():
    error = map_exception(TimeoutError("secret provider detail"), "opend", "APP")
    assert error.error_code == ErrorCode.OPEND_TIMEOUT
    assert error.action == "RETRY"
    assert "secret" not in error.safe_dict()["message"]
    assert "稍后重试" in error.user_message("zh-CN")


def test_data_manager_cache_freshness_and_invalidation():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    calls = []
    manager = DataRequestManager(clock=lambda: now)
    one = manager.request("APP", "latest_quote_regular", lambda: calls.append(1) or {"price": 1})
    two = manager.request("APP", "latest_quote_regular", lambda: calls.append(2) or {"price": 2})
    assert len(calls) == 1
    assert one.freshness == DataFreshness.FRESH and two.value["price"] == 1
    assert manager.invalidate("APP", "latest_quote_regular") == 1


def test_data_manager_coalesces_simultaneous_requests():
    manager = DataRequestManager()
    calls, results = [], []
    def loader():
        calls.append(1); time.sleep(.03); return "ok"
    threads = [threading.Thread(target=lambda: results.append(
        manager.request("MU", "latest_quote_regular", loader).value)) for _ in range(4)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert calls == [1]
    assert results == ["ok"] * 4


def test_data_manager_reports_aging_from_market_timestamp():
    current = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)
    manager = DataRequestManager(clock=lambda: current)
    value = manager.request("APP", "latest_quote_regular", lambda: 1,
                            market_timestamp=current - timedelta(seconds=8))
    assert value.freshness == DataFreshness.AGING
    assert value.safe_metadata()["age_seconds"] == 8


def test_symbol_registry_normalizes_and_maps_leveraged_assets(db):
    service = SymbolRegistryService(db)
    summary = service.sync()
    assert summary["created"] >= 10
    assert service.resolve("$app")["item"]["symbol"] == "APP"
    soxl = service.resolve("US.SOXL")["item"]
    assert soxl["underlying_symbol"] == "SOXX"
    assert float(soxl["leverage_ratio"]) == 3
    assert service.resolve("SNDU")["item"]["underlying_symbol"] == "SNDK"


def test_symbol_registry_rejects_invalid_symbol(db):
    with pytest.raises(ControlledServiceError) as exc:
        SymbolRegistryService(db).resolve("APP; DROP TABLE")
    assert exc.value.error.error_code == ErrorCode.SYMBOL_NOT_FOUND


@pytest.mark.parametrize("text,intent,tool", [
    ("分析 APP", AgentIntent.SYMBOL_ANALYSIS, "analyze_symbol"),
    ("APP资金流怎么样", AgentIntent.MONEY_FLOW, "get_money_flow"),
    ("APP退出风险", AgentIntent.EXIT_RISK, "get_exit_risk"),
    ("我的APP持仓", AgentIntent.POSITION, "get_position"),
])
def test_natural_language_intent_routing(text, intent, tool):
    parsed = parse_intent(text)
    assert parsed.intent == intent and parsed.tool_name == tool


def test_buy_request_is_never_an_execution_tool():
    parsed = parse_intent("帮我买 APP")
    assert parsed.intent == AgentIntent.EXPLANATION
    assert parsed.tool_name == "analyze_symbol"
    assert parsed.arguments["execution_requested"] is True


def test_reply_to_signal_routes_saved_order_explanation():
    parsed = parse_intent("为什么没买", "QMR-20260825-001")
    assert parsed.tool_name == "get_paper_orders"
    assert parsed.arguments["signal_id"] == "QMR-20260825-001"


def test_agent_tool_whitelist_rejects_sql_and_audits(db):
    tools = AgentToolService(db, Settings())
    with pytest.raises(ControlledServiceError):
        tools.call("execute_sql", chat_id="123", intent="TEST")
    audit = db.query(AgentToolAuditRecord).one()
    assert audit.tool_name == "execute_sql" and not audit.success
    assert "123" not in audit.chat_id_hash


def test_agent_blocks_broker_request_without_order(db):
    result = AgentToolService(db, Settings()).call(
        "analyze_symbol", chat_id="123", intent="EXPLANATION", symbol="APP",
        execution_requested=True)
    assert result["execution_blocked"] is True


def test_record_user_trade_only_creates_internal_holding(db):
    result = AgentToolService(db, Settings()).call(
        "record_user_trade", chat_id="123", intent="USER_TRADE_RECORD",
        symbol="APP", user_id="tg-1", quantity="10", average_cost="100")
    assert result["broker_order_created"] is False
    assert db.query(PortfolioHolding).one().symbol == "APP"


def test_order_state_machine_supports_partial_and_rejects_terminal_change():
    assert normalize_broker_status("FILLED_PART").value == "PARTIALLY_FILLED"
    assert validate_transition("SUBMITTED", "PARTIALLY_FILLED").value == "PARTIALLY_FILLED"
    assert validate_transition("PARTIALLY_FILLED", "FILLED").value == "FILLED"
    with pytest.raises(ControlledServiceError):
        validate_transition("FILLED", "SUBMITTED")


def test_order_transition_writes_existing_audit_trail(db):
    event = OrderStateAuditService(db).record_transition(
        42, "SUBMITTED", "FILLED_PART", "partial fill")
    assert event.details_json["previous_state"] == "SUBMITTED"
    assert event.details_json["new_state"] == "PARTIALLY_FILLED"


def test_execution_factory_fails_closed_for_live_or_unknown_mode(db):
    blocked = SimpleNamespace(trading_mode=TradingMode.LIVE, enable_internal_paper=True,
                              default_slippage_bps=0)
    assert isinstance(execution_broker(blocked, db), LiveTradingBlockedBroker)
    with pytest.raises(Exception):
        asyncio.run(execution_broker(blocked, db).submit_order(None))


def test_moomoo_adapter_requires_explicit_simulate_account():
    settings = SimpleNamespace(
        trading_mode=TradingMode.MOOMOO_PAPER, enable_moomoo_paper=True,
        moomoo_live_trading_enabled=False, moomoo_allow_order_submission=False,
        moomoo_opend_host="127.0.0.1", moomoo_opend_port=11111,
        moomoo_connection_timeout_seconds=1,
    )
    broker = MoomooPaperBroker(settings, SimpleNamespace())
    class Context:
        def get_acc_list(self): return 0, SimpleNamespace(to_dict=lambda *_: [{"trd_env": "REAL", "acc_id": 1}])
    sdk = SimpleNamespace(RET_OK=0)
    with pytest.raises(RuntimeError, match="SIMULATE"):
        broker._paper_account(Context(), sdk)
