from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.database.models import TradePlan, UserPosition
from app.participation.repository import UserPositionRepository
from app.participation.service import UserParticipationService
from app.participation.telegram_callback import (
    participation_callback_data, trade_plan_participation_callbacks,
)
from app.trade_lifecycle.domain import TradeDirection, TradePlanDraft
from app.trade_lifecycle.service import TradeLifecycleService


def plan(db, direction=TradeDirection.LONG):
    lifecycle = TradeLifecycleService(db)
    row = lifecycle.create(TradePlanDraft(
        symbol="SOXL", market="US", strategy_name="pullback_restrength",
        strategy_version="1.0.0", direction=direction, timeframe="60m",
        reference_price=Decimal("30"), stop_loss_price=Decimal("27"),
        target_prices=["33", "36"],
    ))
    return lifecycle.advance(row.plan_id, "PLAN", "策略确认", "TEST")


def test_open_position_copies_plan_identity_without_mutating_plan(db):
    source = plan(db)
    before = (source.lifecycle_stage, source.user_participation_status, source.reference_price)
    row = UserParticipationService(db).open("user-a", source.plan_id, "30.25", "10")
    db.refresh(source)
    assert row.symbol == "SOXL" and row.direction == "LONG" and row.status == "OPEN"
    assert row.entry_price == Decimal("30.25000000") and row.quantity == Decimal("10.00000000")
    assert (source.lifecycle_stage, source.user_participation_status, source.reference_price) == before


def test_one_plan_supports_multiple_users(db):
    source = plan(db)
    service = UserParticipationService(db)
    first = service.open("user-a", source.plan_id, "30")
    second = service.open("user-b", source.plan_id, "31")
    assert first.trade_plan_id == second.trade_plan_id and first.user_id != second.user_id
    assert db.scalar(select(func.count()).select_from(UserPosition)) == 2


def test_same_user_cannot_duplicate_open_position(db):
    source = plan(db)
    service = UserParticipationService(db)
    service.open("user-a", source.plan_id, "30")
    with pytest.raises(ValueError, match="重复"):
        service.open("user-a", source.plan_id, "31")


def test_closed_user_can_participate_again(db):
    source = plan(db)
    service = UserParticipationService(db)
    first = service.open("user-a", source.plan_id, "30")
    service.close(first.id, "31")
    second = service.open("user-a", source.plan_id, "32")
    assert second.id != first.id and second.status == "OPEN"


@pytest.mark.parametrize("value", ["0", "-1", "nan", "not-number"])
def test_entry_price_validation(db, value):
    source = plan(db)
    with pytest.raises(ValueError):
        UserParticipationService(db).open("user-a", source.plan_id, value)


def test_quantity_is_optional_but_positive_when_present(db):
    source = plan(db)
    service = UserParticipationService(db)
    assert service.open("user-a", source.plan_id, "30").quantity is None
    with pytest.raises(ValueError):
        service.open("user-b", source.plan_id, "30", "0")


def test_only_active_plan_stage_can_be_joined(db):
    row = TradeLifecycleService(db).create(TradePlanDraft(
        symbol="QQQ", market="US", strategy_name="test", strategy_version="1",
        direction=TradeDirection.LONG, timeframe="1d",
    ))
    with pytest.raises(ValueError, match="PLAN阶段"):
        UserParticipationService(db).open("user-a", row.plan_id, "500")


def test_close_position_and_statistics(db):
    source = plan(db)
    service = UserParticipationService(db)
    winner = service.open("user-a", source.plan_id, "30")
    service.close(winner.id, "32", notes="手工平仓")
    assert winner.status == "CLOSED" and winner.exit_price == Decimal("32.00000000")
    assert service.statistics("user-a") == {
        "open_positions": 0, "closed_positions": 1, "total_trades": 1,
        "win_count": 1, "loss_count": 0,
    }


def test_short_win_and_loss_counts(db):
    source = plan(db, TradeDirection.SHORT)
    service = UserParticipationService(db)
    win = service.open("user-a", source.plan_id, "30")
    service.close(win.id, "28")
    loss = service.open("user-a", source.plan_id, "30")
    service.close(loss.id, "32")
    assert service.statistics("user-a")["win_count"] == 1
    assert service.statistics("user-a")["loss_count"] == 1


def test_close_is_not_repeatable_and_time_is_validated(db):
    source = plan(db)
    service = UserParticipationService(db)
    row = service.open("user-a", source.plan_id, "30")
    with pytest.raises(ValueError, match="早于"):
        service.close(row.id, "31", closed_at=datetime.now(timezone.utc) - timedelta(days=1))
    assert row.status == "OPEN"
    service.close(row.id, "31")
    with pytest.raises(ValueError, match="OPEN"):
        service.close(row.id, "32")


def test_repository_filters_exists_and_get(db):
    source = plan(db)
    row = UserParticipationService(db).open("user-a", source.plan_id, "30")
    repository = UserPositionRepository(db)
    assert repository.exists_open("user-a", source.id)
    assert repository.get(row.id).symbol == "SOXL"
    assert repository.count(user_id="user-a", status="OPEN") == 1
    assert repository.list(symbol="us.soxl")[0].id == row.id


def test_telegram_callback_data_only(db):
    source = plan(db)
    data = trade_plan_participation_callbacks(source.plan_id)
    assert data["我买入"] == "participation:open:" + source.plan_id
    assert data["忽略"].startswith("participation:ignore:")
    assert len(data["加入关注"].encode("utf-8")) <= 64
    with pytest.raises(ValueError):
        participation_callback_data("sell", source.plan_id)
