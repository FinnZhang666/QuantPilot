from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.database.models import CandidateSignal, TradePlan, TradePlanTransition
from app.trade_lifecycle.adapter import TradePlanAdapter
from app.trade_lifecycle.domain import (
    LifecycleStage, TradeDirection, TradePlanDraft, normalize_direction, normalize_stage,
)
from app.trade_lifecycle.formatter import format_trade_plan
from app.trade_lifecycle.service import TradeLifecycleService


NOW = datetime(2026, 7, 31, 14, 0, tzinfo=timezone.utc)


def signal(db, signal_type="CANDIDATE_BUY"):
    row = CandidateSignal(
        symbol="SOXL", market="US", timeframe="60m", bar_timestamp=NOW,
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        parameters_hash="stable-hash", signal_type=signal_type,
        score=83, confidence=88, status="VALID", summary_zh="测试策略输出",
        reasons_json=["趋势满足"], risks_json=["成交量待确认"],
        feature_refs_json={"ema_20": {"version": "1.0.0"}},
        components_json={"trend_score": 30},
    )
    db.add(row)
    db.commit()
    return row


def test_lifecycle_enum_values():
    assert [stage.value for stage in LifecycleStage] == [
        "DISCOVER", "PLAN", "COMPANION", "REVIEW", "CANCELLED", "EXPIRED",
    ]


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_direction_enum(direction):
    assert normalize_direction(direction).value == direction


def test_invalid_stage_and_direction():
    with pytest.raises(ValueError):
        normalize_stage("TRADE")
    with pytest.raises(ValueError):
        normalize_direction("SIDEWAYS")


def test_adapter_is_deterministic_and_preserves_signal(db):
    row = signal(db)
    original = list(row.reasons_json)
    first = TradePlanAdapter().from_candidate_signal(row)
    second = TradePlanAdapter().from_candidate_signal(row)
    assert first == second
    assert first.direction == TradeDirection.LONG
    assert first.reference_price is None and first.buy_zone_lower is None
    assert first.source_metadata["signal"]["components"]["trend_score"] == 30
    assert row.reasons_json == original


def test_adapter_accepts_explicit_short_without_calculation(db):
    draft = TradePlanAdapter().from_candidate_signal(signal(db), direction="SHORT")
    assert draft.direction == TradeDirection.SHORT
    assert draft.source_metadata["levels"]["availability"] == "UNAVAILABLE"


def test_adapter_rejects_non_entry_signal(db):
    with pytest.raises(ValueError, match="不会创建Trade Plan"):
        TradePlanAdapter().from_candidate_signal(signal(db, "WATCH"))


def test_service_creates_plan_and_creation_history(db):
    source = signal(db)
    row, created = TradeLifecycleService(db).create_from_signal(source.id)
    assert created and row.lifecycle_stage == "DISCOVER" and row.plan_status == "ACTIVE"
    assert row.reference_price is None and row.stop_loss_price is None
    history = TradeLifecycleService(db).history(row.plan_id)
    assert len(history) == 1 and history[0].previous_stage is None
    assert history[0].new_stage == "DISCOVER" and history[0].source == "STRATEGY_ADAPTER"


def test_plan_creation_is_idempotent_per_signal_direction(db):
    source = signal(db)
    service = TradeLifecycleService(db)
    first, created = service.create_from_signal(source.id)
    second, created_again = service.create_from_signal(source.id)
    assert created and not created_again and first.id == second.id
    assert db.scalar(select(func.count()).select_from(TradePlan)) == 1


def test_missing_signal_rejected(db):
    with pytest.raises(KeyError):
        TradeLifecycleService(db).create_from_signal(999)


def test_valid_lifecycle_path_is_audited(db):
    row, _ = TradeLifecycleService(db).create_from_signal(signal(db).id)
    service = TradeLifecycleService(db)
    service.advance(row.plan_id, "PLAN", "管理员确认进入计划阶段", "ADMIN")
    service.advance(row.plan_id, "COMPANION", "计划开始陪伴跟踪", "ADMIN")
    result = service.advance(row.plan_id, "REVIEW", "陪伴结束进入复盘", "SYSTEM")
    assert result.lifecycle_stage == "REVIEW" and result.review_status == "PENDING"
    assert [item.new_stage for item in service.history(row.plan_id)] == [
        "DISCOVER", "PLAN", "COMPANION", "REVIEW",
    ]


@pytest.mark.parametrize("target", ["COMPANION", "REVIEW"])
def test_arbitrary_state_jump_rejected(db, target):
    row, _ = TradeLifecycleService(db).create_from_signal(signal(db).id)
    with pytest.raises(ValueError, match="不允许"):
        TradeLifecycleService(db).advance(row.plan_id, target, "跳转", "TEST")


def test_terminal_state_cannot_advance(db):
    row, _ = TradeLifecycleService(db).create_from_signal(signal(db).id)
    service = TradeLifecycleService(db)
    service.cancel(row.plan_id, "用户取消研究计划", "ADMIN")
    with pytest.raises(ValueError):
        service.advance(row.plan_id, "PLAN", "恢复", "ADMIN")


def test_cancel_and_expire_update_status(db):
    service = TradeLifecycleService(db)
    cancelled = service.create(TradePlanDraft(
        symbol="AAPL", market="US", strategy_name="test", strategy_version="1",
        direction=TradeDirection.LONG, timeframe="1d",
    ))
    expired = service.create(TradePlanDraft(
        symbol="MSFT", market="US", strategy_name="test", strategy_version="1",
        direction=TradeDirection.LONG, timeframe="1d",
    ))
    assert service.cancel(cancelled.plan_id, "取消").plan_status == "CANCELLED"
    assert service.expire(expired.plan_id, "超过有效期").plan_status == "EXPIRED"


def test_transition_requires_reason_and_source(db):
    row, _ = TradeLifecycleService(db).create_from_signal(signal(db).id)
    with pytest.raises(ValueError, match="reason和source"):
        TradeLifecycleService(db).advance(row.plan_id, "PLAN", "", "ADMIN")
    assert row.lifecycle_stage == "DISCOVER"


def test_list_filters_without_full_table_mutation(db):
    service = TradeLifecycleService(db)
    service.create(TradePlanDraft(
        symbol="AAPL", market="US", strategy_name="alpha", strategy_version="1",
        direction=TradeDirection.LONG, timeframe="1d",
    ))
    service.create(TradePlanDraft(
        symbol="MSFT", market="US", strategy_name="beta", strategy_version="1",
        direction=TradeDirection.SHORT, timeframe="60m",
    ))
    assert [row.symbol for row in service.list(symbol="aapl")] == ["AAPL"]
    assert [row.symbol for row in service.list(strategy="beta")] == ["MSFT"]


def test_trade_plan_formatter_marks_missing_levels(db):
    row, _ = TradeLifecycleService(db).create_from_signal(signal(db).id)
    text = format_trade_plan(row)
    assert "Symbol: SOXL" in text and "Stage: DISCOVER" in text
    assert text.count("暂无（策略未提供）") >= 5
    assert "不是订单" in text


def test_formatter_uses_supplied_levels(db):
    row = TradeLifecycleService(db).create(TradePlanDraft(
        symbol="AAPL", market="US", strategy_name="test", strategy_version="1",
        direction=TradeDirection.LONG, timeframe="1d", reference_price=Decimal("100"),
        buy_zone_lower=Decimal("98"), buy_zone_upper=Decimal("101"),
        stop_loss_price=Decimal("95"), target_prices=["110", "120"],
    ))
    text = format_trade_plan(row)
    assert "Buy Zone: 98 - 101" in text
    assert "Targets: 110, 120" in text
    assert db.scalar(select(func.count()).select_from(TradePlanTransition)) == 1
