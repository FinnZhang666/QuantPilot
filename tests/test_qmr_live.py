from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy import select

from app.core.config import Settings
from app.database.models import (
    QmrLiveSignal, QmrSignalDelivery, QmrSignalParticipation,
    TelegramFeedbackRecord, TelegramRuntimeUser,
)
from app.qmr_live.formatter import qmr_signal_message
from app.qmr_live.repository import QmrLiveRepository
from app.qmr_live.service import QmrLiveSignalService
from app.qmr_live.telegram import QmrTelegramNotifier
from app.qmr_live.tracking import QmrPerformanceTracker
from app.telegram_runtime.service import TelegramProductService


NOW = datetime(2026, 8, 14, 15, 32, tzinfo=timezone.utc)


def signal(signal_id="QMR-20260814-001", level="EARLY_ENTRY", samples=12):
    return QmrLiveSignal(signal_id=signal_id, buy_score_id=1, symbol="MU",
        signal_level=level, signal_mode="LIVE", status="ACTIVE", strategy_status="VALIDATED",
        strategy_version="QMR-v1.0", model_version="buy-score-v1",
        telegram_template_version="qmr-telegram-v1", signal_time=NOW,
        signal_price=Decimal("100"), latest_price=Decimal("105"), buy_score=86,
        buy_grade="A", quality_score=88, mispricing_score=91, recovery_score=82,
        market_state="MARKET_RECOVERY", sector="Semiconductors", trading_session="REGULAR",
        session_confidence="HIGH", chase_risk_level="LOW",
        similar_statistics_json={"status": "AVAILABLE", "sample_count": samples,
            "win_rate_5d": .717, "average_return_5d": 6.3,
            "average_return_10d": 8.2, "mae": -3.8, "mfe": 11.6},
        signal_snapshot_json={"reasons": ["Higher Low", "VWAP"]},
        invalidation_reason_json=[], last_state_change_at=NOW)


def user(db):
    row = TelegramRuntimeUser(telegram_user_id="100", chat_id="100", language="zh-CN",
                              last_bot_alias="bot", status="ACTIVE",
                              pending_context_json={"language_selected": True})
    db.add(row); db.commit(); return row


def test_qmr_message_is_conclusion_first_and_warns_for_small_sample():
    text = qmr_signal_message(signal()).text
    assert text.index("MU") < text.index("历史相似信号")
    assert "买入评分：86 / 100" in text
    assert "历史样本较少" in text
    assert "#QMR-20260814-001" in text


def test_qmr_message_sample_bands_and_session_markers():
    preliminary = qmr_signal_message(signal(samples=40)).text
    normal = qmr_signal_message(signal(samples=100)).text
    overnight = signal(); overnight.trading_session = "OVERNIGHT"
    assert "历史样本：初步" in preliminary
    assert "样本：100" in normal
    assert "【夜盘】" in qmr_signal_message(overnight).text


def test_delivery_unique_event_prevents_repeat(db):
    row = signal(); db.add(row); db.commit()
    repository = QmrLiveRepository(db)
    repository.save_delivery(QmrSignalDelivery(signal_id=row.signal_id, chat_id="100",
        bot_alias="bot", event_type="EARLY_ENTRY", status="SUCCESS"))
    assert repository.delivery(row.signal_id, "100", "EARLY_ENTRY") is not None


def test_failed_delivery_never_removes_signal(db, monkeypatch):
    row = signal(); db.add(row); db.commit()
    repository = QmrLiveRepository(db)
    monkeypatch.setattr(repository, "recipients", lambda _research: [{
        "chat_id": "100", "language": "zh-CN", "bot_alias": "trade_companion_ai"}])
    class BadTransport:
        def send_message(self, *_args): raise RuntimeError("offline")
    cfg = SimpleNamespace(telegram_enabled=True)
    from app.telegram_product.bot_profiles import TelegramBotProfile
    profile = TelegramBotProfile(alias="trade_companion_ai", language="zh-CN",
        display_name="Bot", short_description="short", description="description",
        welcome="welcome", commands=(), main_menu=(), token_setting="TOKEN",
        fallback_token_settings=(), token="secret", enabled=True)
    monkeypatch.setattr("app.qmr_live.telegram.load_bot_profiles", lambda _settings: [profile])
    assert QmrTelegramNotifier(repository, cfg, BadTransport()).send(row, "EARLY_ENTRY") == ["FAILED"]
    assert repository.signal(row.signal_id) is not None


def test_feedback_is_upserted_not_double_counted(db):
    row = signal(); actor = user(db); db.add(row); db.commit()
    service = QmrLiveSignalService(db, Settings(_env_file=None))
    service.feedback(actor, row.signal_id, True, "bot")
    service.feedback(actor, row.signal_id, False, "bot")
    items = list(db.scalars(select(TelegramFeedbackRecord).where(
        TelegramFeedbackRecord.related_id == row.signal_id)))
    assert len(items) == 1 and items[0].category == "NOT_HELPFUL"


def test_bought_is_idempotent_and_uses_reference_price(db):
    row = signal(); actor = user(db); db.add(row); db.commit()
    service = QmrLiveSignalService(db, Settings(_env_file=None))
    first, created = service.bought(actor, row.signal_id)
    second, created_again = service.bought(actor, row.signal_id)
    assert created is True and created_again is False and first.id == second.id
    assert first.entry_price_source == "SIGNAL_REFERENCE" and first.entry_price == row.signal_price


def test_reply_message_resolves_signal_id(db):
    row = signal(); db.add(row); db.flush()
    db.add(QmrSignalDelivery(signal_id=row.signal_id, chat_id="100", bot_alias="bot",
        event_type="EARLY_ENTRY", status="SUCCESS", telegram_message_id="77")); db.commit()
    assert QmrLiveSignalService(db, Settings(_env_file=None)).resolve_reply("100", "77") == row.signal_id


def test_existing_telegram_service_answers_reply_without_ai_guessing(db):
    row = signal(); actor = user(db); db.add(row); db.flush()
    db.add(QmrSignalDelivery(signal_id=row.signal_id, chat_id="100", bot_alias="bot",
        event_type="EARLY_ENTRY", status="SUCCESS", telegram_message_id="77")); db.commit()
    product = TelegramProductService(db, Settings(_env_file=None), Mock())
    result = product._incoming_text(SimpleNamespace(alias="bot"), actor, "现在怎么样？", "77")
    assert row.signal_id in result.text and "当前状态：ACTIVE" in result.text


def test_existing_telegram_callbacks_update_feedback_and_participation(db):
    row = signal(); actor = user(db); db.add(row); db.commit()
    product = TelegramProductService(db, Settings(_env_file=None), Mock())
    profile = SimpleNamespace(alias="bot")
    product._action(profile, actor, "qmr-feedback:%s:helpful" % row.signal_id, None)
    product._action(profile, actor, "qmr-feedback:%s:not-helpful" % row.signal_id, None)
    product._action(profile, actor, "qmr-bought:%s" % row.signal_id, None)
    product._action(profile, actor, "qmr-bought:%s" % row.signal_id, None)
    feedback = list(db.scalars(select(TelegramFeedbackRecord).where(
        TelegramFeedbackRecord.related_id == row.signal_id)))
    participation = list(db.scalars(select(QmrSignalParticipation).where(
        QmrSignalParticipation.signal_id == row.signal_id)))
    assert len(feedback) == 1 and feedback[0].category == "NOT_HELPFUL"
    assert len(participation) == 1


def test_case_labels_cover_winners_and_false_recovery(db):
    tracker = QmrPerformanceTracker(db, Settings(_env_file=None))
    assert tracker._case_label(55, -2) == "OUTLIER_WINNER"
    assert tracker._case_label(25, -2) == "MAJOR_WINNER"
    assert tracker._case_label(5, -11) == "FALSE_RECOVERY"


def test_empty_statistics_are_not_fabricated(db):
    stats = QmrPerformanceTracker(db, Settings(_env_file=None)).statistics(5)
    assert stats["sample_count"] == 0 and stats["win_rate"] is None


def test_tracking_without_bars_preserves_active_signal(db):
    row = signal(); db.add(row); db.commit()
    result = QmrPerformanceTracker(db, Settings(_env_file=None)).run(NOW + timedelta(days=30))
    assert result["scanned"] == 1 and result["failed"] == 0
    assert QmrLiveRepository(db).signal(row.signal_id).status == "ACTIVE"
    assert len(QmrLiveRepository(db).performances(row.signal_id)) == 5


def live_service_with(score, active=None, recovery_stage="RECOVERY_CONFIRMED"):
    service = QmrLiveSignalService.__new__(QmrLiveSignalService)
    service.db = Mock()
    service.settings = SimpleNamespace()
    service.config = {"max_signal_age_minutes": 15, "telegram_template_version": "v1",
                      "similarity_limit": 100, "similarity_fields": {}}
    recovery = SimpleNamespace(recovery_stage=recovery_stage, failure_reason="跌破关键低点",
        price=95, trading_session="REGULAR", market_state="MARKET_RECOVERY",
        score_components_json={})
    repository = Mock()
    repository.latest_strategy_run.return_value = SimpleNamespace(strategy_status="VALIDATED",
                                                                   parameter_set_id=1)
    repository.latest_scores.return_value = [score]
    repository.recovery.return_value = recovery
    repository.active_signal.return_value = active
    repository.latest_signal.return_value = active
    repository.instrument.return_value = SimpleNamespace(sector="Semiconductors")
    repository.next_sequence.return_value = 1
    repository.similar_cases.return_value = []
    service.repository = repository
    service.notifier = Mock()
    service.notifier.send.return_value = ["SUCCESS"]
    return service, repository


def score(level="EARLY_ENTRY"):
    return SimpleNamespace(id=1, symbol="MU", buy_status=level, evaluation_time=NOW,
        entry_reference_price=100, final_buy_score=80, buy_grade="A", recovery_score=80,
        quality_score=85, mispricing_score=88, data_confidence="HIGH",
        model_version="buy-v1", chase_risk_level="LOW", score_components_json={})


def test_first_early_entry_is_saved_and_notified_once():
    service, repository = live_service_with(score())
    result = service.run(NOW)
    assert result["created"] == 1
    repository.save_signal.assert_called_once()
    service.notifier.send.assert_called_once()


def test_repeated_same_state_is_not_notified():
    active = signal(level="EARLY_ENTRY")
    service, _ = live_service_with(score(), active)
    result = service.run(NOW)
    assert result["skipped"] == 1
    service.notifier.send.assert_not_called()


def test_early_to_confirmed_is_upgrade_notification():
    active = signal(level="EARLY_ENTRY")
    service, repository = live_service_with(score("CONFIRMED_ENTRY"), active)
    service.snapshot = Mock(return_value={})
    service.similar_statistics = Mock(return_value={})
    result = service.run(NOW)
    assert result["upgraded"] == 1 and active.signal_level == "CONFIRMED_ENTRY"
    repository.commit.assert_called_once()
    service.notifier.send.assert_called_once_with(active, "CONFIRMED_ENTRY")


def test_confirmed_to_failed_invalidates_and_notifies():
    active = signal(level="CONFIRMED_ENTRY")
    service, repository = live_service_with(score("CONFIRMED_ENTRY"), active, "FAILED_RECOVERY")
    result = service.run(NOW)
    assert result["invalidated"] == 1 and active.status == "INVALIDATED"
    repository.commit.assert_called_once()
    service.notifier.send.assert_called_once_with(active, "INVALIDATED")
