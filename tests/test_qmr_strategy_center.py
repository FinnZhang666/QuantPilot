from datetime import datetime, timezone
from decimal import Decimal

from app.core.config import Settings
from app.database.models import QmrLiveSignal, StrategyRecord
from app.qmr_live.formatter import qmr_signal_message
from app.qmr_live.service import QmrLiveSignalService
from app.strategy.qmr_registry import QMR_CODE, QMR_NAME, StrategyCenterService


NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)


def test_qmr_appears_as_one_formal_strategy(db):
    items = StrategyCenterService(db, Settings(_env_file=None)).list()
    qmr = next(item for item in items if item["strategy_code"] == QMR_CODE)
    assert qmr["strategy_name"] == QMR_NAME
    assert qmr["strategy_version"] == "QMR-v1.1"
    assert "SOXX" in qmr["universe"] and "IWM" in qmr["universe"]
    assert qmr["historical_win_rate_5d"] is None


def test_qmr_detail_contains_six_sprint_pipeline(db):
    service = StrategyCenterService(db, Settings(_env_file=None)); service.ensure_qmr()
    detail = service.get(QMR_CODE)
    assert "统一股票池" in detail["logic"][0]
    assert detail["logic"][-1] == "案例跟踪"
    assert {"current_candidates", "current_signals", "backtest", "live_performance", "cases"} <= set(detail)


def test_disable_stops_new_qmr_signal_generation(db):
    center = StrategyCenterService(db, Settings(_env_file=None)); center.ensure_qmr()
    center.set_enabled(QMR_CODE, False)
    result = QmrLiveSignalService(db, Settings(_env_file=None)).run(NOW)
    assert result["strategy_status"] == "DISABLED" and result["created"] == 0


def test_reenable_restores_detection(db):
    center = StrategyCenterService(db, Settings(_env_file=None)); center.ensure_qmr()
    center.set_enabled(QMR_CODE, False); center.set_enabled(QMR_CODE, True)
    result = QmrLiveSignalService(db, Settings(_env_file=None)).run(NOW)
    assert result["strategy_status"] == "RESEARCH" and result["scanned"] == 0


def test_future_registry_version_does_not_overwrite_v1_history(db):
    center = StrategyCenterService(db, Settings(_env_file=None)); row = center.ensure_qmr()
    signal = QmrLiveSignal(signal_id="QMR-20260824-001", buy_score_id=1, symbol="MU",
        signal_level="EARLY_ENTRY", signal_mode="PAPER", status="ACTIVE", strategy_status="RESEARCH",
        strategy_version="QMR-v1.0", model_version="buy-score-v1", telegram_template_version="v1",
        signal_time=NOW, signal_price=Decimal("100"), buy_score=75, buy_grade="B",
        quality_score=80, mispricing_score=80, recovery_score=70, session_confidence="HIGH",
        chase_risk_level="LOW", similar_statistics_json={}, signal_snapshot_json={},
        invalidation_reason_json=[], last_state_change_at=NOW)
    db.add(signal); db.commit()
    row.version = "QMR-v1.1"; db.commit()
    assert signal.strategy_version == "QMR-v1.0"


def test_other_registered_strategy_is_unchanged(db):
    other = StrategyRecord(code="other", name="Other", version="1", is_enabled=False,
                           config_json={})
    db.add(other); db.commit()
    StrategyCenterService(db, Settings(_env_file=None)).ensure_qmr()
    assert db.get(StrategyRecord, other.id).is_enabled is False


def test_qmr_telegram_names_strategy_and_version():
    signal = type("Signal", (), {"symbol": "MU", "signal_mode": "LIVE",
        "trading_session": "REGULAR", "signal_level": "EARLY_ENTRY", "buy_score": 80,
        "buy_grade": "A", "signal_price": 100, "chase_risk_level": "LOW",
        "session_confidence": "HIGH", "quality_score": 85, "mispricing_score": 88,
        "recovery_score": 75, "signal_snapshot_json": {}, "similar_statistics_json": {},
        "signal_id": "QMR-20260824-001", "strategy_version": "QMR-v1.1"})()
    text = qmr_signal_message(signal).text
    assert "策略：优质错杀修复" in text and "QMR v1.1" in text
