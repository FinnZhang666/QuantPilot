from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.database.models import CandidateSignal, RuntimeStatus, TradePlan, TradePlanTransition
from app.trade_lifecycle.repository import TradePlanRepository
from app.trade_lifecycle.runtime import TradePlanRuntime
from app.trade_lifecycle.scheduler import TradePlanGeneratorScheduler
from app.trade_lifecycle.service import TradeLifecycleService


def add_signal(db, minute=0, signal_type="CANDIDATE_BUY", status="VALID"):
    row = CandidateSignal(
        symbol="SOXL", market="US", timeframe="60m",
        bar_timestamp=datetime(2026, 7, 31, 14, minute, tzinfo=timezone.utc),
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        parameters_hash="hash-%s" % minute, signal_type=signal_type,
        score=80 + minute, confidence=85, status=status, summary_zh="测试",
        reasons_json=[], risks_json=[], feature_refs_json={}, components_json={},
    )
    db.add(row)
    db.commit()
    return row


def test_runtime_generates_and_promotes_confirmed_signal(db):
    source = add_signal(db)
    result = TradePlanRuntime(db).run()
    plan = db.scalar(select(TradePlan))
    assert result["created"] == 1 and result["promoted"] == 1
    assert plan.signal_id == source.id and plan.lifecycle_stage == "PLAN"
    assert [x.new_stage for x in TradeLifecycleService(db).history(plan.plan_id)] == [
        "DISCOVER", "PLAN",
    ]


def test_runtime_is_idempotent_across_repeated_runs(db):
    add_signal(db)
    first = TradePlanRuntime(db).run()
    second = TradePlanRuntime(db).run()
    assert first["created"] == 1 and second["scanned"] == 0
    assert db.scalar(select(func.count()).select_from(TradePlan)) == 1
    assert db.scalar(select(func.count()).select_from(TradePlanTransition)) == 2


def test_runtime_promotes_existing_discover_plan(db):
    source = add_signal(db)
    plan, _ = TradeLifecycleService(db).create_from_signal(source.id)
    assert plan.lifecycle_stage == "DISCOVER"
    result = TradePlanRuntime(db).run()
    assert result["created"] == 0 and result["refreshed"] == 1
    assert result["promoted"] == 1 and plan.lifecycle_stage == "PLAN"


def test_runtime_ignores_watch_and_invalid_signals(db):
    add_signal(db, signal_type="WATCH")
    add_signal(db, minute=1, status="MISSING_FEATURE")
    assert TradePlanRuntime(db).run()["scanned"] == 0
    assert db.scalar(select(func.count()).select_from(TradePlan)) == 0


def test_repository_crud_search_count_and_exists(db):
    source = add_signal(db)
    service = TradeLifecycleService(db)
    plan, _ = service.create_from_signal(source.id)
    repository = TradePlanRepository(db)
    assert repository.exists(source.id)
    assert repository.get(plan.plan_id).id == plan.id
    assert repository.count(symbol="soxl", lifecycle_stage="DISCOVER") == 1
    assert repository.list(strategy="pullback_restrength")[0].id == plan.id
    assert repository.history(plan.id)[0].new_stage == "DISCOVER"


def test_runtime_processes_distinct_signals_independently(db):
    add_signal(db)
    add_signal(db, minute=1)
    result = TradePlanRuntime(db).run()
    assert result["created"] == 2 and result["errors_count"] == 0
    assert db.scalar(select(func.count()).select_from(TradePlan)) == 2


def test_repository_date_filters(db):
    add_signal(db)
    TradePlanRuntime(db).run()
    repository = TradePlanRepository(db)
    now = datetime.now(timezone.utc)
    assert repository.count(start_time=now - timedelta(minutes=1)) == 1
    assert repository.count(end_time=now - timedelta(days=1)) == 0


def test_scheduler_generates_plans_and_persists_health(db):
    add_signal(db)
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    scheduler = TradePlanGeneratorScheduler(factory, batch_size=10)
    scheduler._run()
    with factory() as check:
        plan = check.scalar(select(TradePlan))
        status = check.scalar(select(RuntimeStatus).where(
            RuntimeStatus.service_name == "trade_plan_generator",
        ))
        assert plan.lifecycle_stage == "PLAN"
        assert status.status == "CONNECTED" and status.metadata_json["created"] == 1
    assert scheduler.last_run_at is not None


def test_scheduler_repeated_run_is_idempotent(db):
    add_signal(db)
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    scheduler = TradePlanGeneratorScheduler(factory)
    scheduler._run()
    scheduler._run()
    with factory() as check:
        assert check.scalar(select(func.count()).select_from(TradePlan)) == 1
        assert check.scalar(select(func.count()).select_from(TradePlanTransition)) == 2
