from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.ai.config import build_provider
from app.ai.parser import parse_ai_response
from app.ai.providers.mock_provider import MockAIProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.scheduler import AIReviewScheduler
from app.ai.schemas import AIReviewResponse
from app.ai.service import AIReviewService, convert_investigation_item_to_issue
from app.core.config import Settings
from app.database.models import AIReviewAnalysis, Opportunity, OpportunityReview
from app.notifications.telegram_commands import TelegramCommandService


NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


def add_review(db, symbol="SOXL", direction="LONG", status="REVIEWED", value="5"):
    opportunity = Opportunity(
        symbol=symbol, timeframe="1d", direction=direction,
        opportunity_type="PULLBACK_RESTRENGTH",
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        status="REVIEWED", score=80, confidence=75, detected_at=NOW, bar_time=NOW,
        entry_reference_price=Decimal("100"), target_reference_price=Decimal("120"),
        stop_reference_price=Decimal("90"), feature_snapshot_json={"ema_20": "101"},
        strategy_snapshot_json={"signal": "CANDIDATE_BUY"},
        decision_snapshot_json={"gate": "passed"}, notification_status="NOTIFIED",
    )
    db.add(opportunity)
    db.flush()
    review = OpportunityReview(
        opportunity_id=opportunity.id, review_status=status, review_time=NOW,
        holding_bars=20, holding_minutes=28800, holding_days=20,
        entry_reference_price=100, exit_reference_price=105, last_price=105,
        mfe_percent=8, mae_percent=-3, return_percent=Decimal(value),
        max_close_return=7, min_close_return=-2, target_hit=False, stop_hit=False,
        expired=True, review_window="20d",
        price_path_json=[
            {"timestamp": NOW.isoformat(), "open": "100", "high": "102",
             "low": "98", "close": "100", "volume": 1000},
            {"timestamp": NOW.isoformat(), "open": "104", "high": "106",
             "low": "103", "close": "105", "volume": 1200},
        ],
        statistics_json={"window_returns": {"1d": "1", "20d": value}},
        reason_json={"status": "COMPLETED"},
    )
    db.add(review)
    db.commit()
    return opportunity, review


def enabled_settings(**values):
    base = {
        "ai_review_enabled": True, "ai_review_provider": "mock",
        "ai_review_max_retries": 1,
    }
    base.update(values)
    return Settings(**base)


def valid_response():
    return {
        "summary": "复盘摘要", "outcome_classification": "MODERATE_SUCCESS",
        "facts": ["收益为正"], "positive_factors": ["趋势"],
        "negative_factors": [], "risk_factors": ["样本少"],
        "timing_analysis": {
            "entry_timing": "合理", "exit_timing": "窗口结束",
            "mfe_mae_interpretation": "MFE高于最终收益",
            "target_stop_interpretation": "均未触达",
        },
        "market_regime_analysis": {
            "alignment": "UNKNOWN", "evidence": [], "uncertainty": "无数据",
        },
        "historical_comparison": {
            "comparison_summary": "样本不足", "sample_size_warning": "低样本",
            "differences": [],
        },
        "investigation_items": [{
            "title": "检查退出时点", "category": "TIMING",
            "evidence": "MFE高于最终收益", "priority": "HIGH",
        }],
        "confidence_score": 70, "uncertainty_notes": ["无市场环境"],
    }


def test_ai_disabled_does_not_create(db):
    add_review(db)
    result = AIReviewService(db, Settings()).run()
    assert not result["enabled"]
    assert db.scalar(select(func.count()).select_from(AIReviewAnalysis)) == 0


@pytest.mark.parametrize("direction,value,classification", [
    ("LONG", "5", "MODERATE_SUCCESS"),
    ("SHORT", "-5", "MODERATE_FAILURE"),
])
def test_mock_long_and_short(db, direction, value, classification):
    opportunity, review = add_review(db, direction=direction, value=value)
    row, created = AIReviewService(db, enabled_settings()).analyze(review, opportunity)
    assert created and row.status == "COMPLETED" and row.provider == "mock"
    assert row.historical_comparison_json["outcome_classification"] == classification
    assert "TEST / MOCK OUTPUT" in row.summary


def test_input_snapshot_and_missing_optional_context(db):
    opportunity, review = add_review(db)
    request = AIReviewService(db, enabled_settings()).build_request(opportunity, review)
    assert request.opportunity.symbol == "SOXL"
    assert request.market_regime is None and request.candidate_pool is None
    assert request.feature_snapshot["ema_20"] == "101"
    assert request.historical_statistics.same_strategy.sample_size == 1
    assert request.historical_statistics.same_market_regime.sample_size == 0


def test_historical_low_sample_is_explicit(db):
    opportunity, review = add_review(db)
    request = AIReviewService(db, enabled_settings()).build_request(opportunity, review)
    assert request.historical_statistics.global_statistics.sample_size == 1


def test_parser_valid_json():
    assert parse_ai_response(valid_response()).confidence_score == 70


def test_parser_invalid_json():
    with pytest.raises(ValueError, match="合法JSON"):
        parse_ai_response("<html>bad</html>")


def test_schema_validation_failure():
    invalid = valid_response()
    invalid["confidence_score"] = 101
    with pytest.raises(ValidationError):
        AIReviewResponse.model_validate(invalid)


def test_openai_compatible_request_preview_has_no_key(db):
    opportunity, review = add_review(db)
    request = AIReviewService(db, enabled_settings()).build_request(opportunity, review)
    provider = OpenAICompatibleProvider(
        "https://example.test/v1", "super-secret", "review-model", 10,
    )
    preview = provider.request_preview(request)
    assert preview["url"].endswith("/chat/completions")
    assert "super-secret" not in str(preview)


def test_local_provider_base_url():
    provider = build_provider(Settings(
        ai_review_enabled=True, ai_review_provider="local",
        ai_review_base_url="http://127.0.0.1:11434/v1", ai_review_model="local-model",
    ))
    assert provider.name == "local"
    assert provider.base_url == "http://127.0.0.1:11434/v1"


class TimeoutProvider:
    name = "openai_compatible"
    model = "timeout-model"

    def __init__(self):
        self.calls = 0

    def analyze_review(self, request):
        self.calls += 1
        raise httpx.TimeoutException("secret should not escape")


def test_provider_timeout_retry_and_safe_error(db):
    opportunity, review = add_review(db)
    provider = TimeoutProvider()
    row, _ = AIReviewService(db, enabled_settings(), provider).analyze(review, opportunity)
    assert row.status == "FAILED" and provider.calls == 2
    assert row.error_message == "AI Provider请求超时。"
    assert "secret" not in row.error_message


def test_provider_single_failure_isolated(db):
    add_review(db, symbol="SOXL")
    add_review(db, symbol="TQQQ")
    result = AIReviewService(db, enabled_settings(), TimeoutProvider()).run(limit=20)
    assert result["scanned"] == 2 and result["failed"] == 2


def test_idempotency(db):
    opportunity, review = add_review(db)
    service = AIReviewService(db, enabled_settings())
    first, created = service.analyze(review, opportunity)
    second, created_again = service.analyze(review, opportunity)
    assert created and not created_again and first.id == second.id
    assert db.scalar(select(func.count()).select_from(AIReviewAnalysis)) == 1


def test_incomplete_review_is_insufficient(db):
    opportunity, review = add_review(db, status="REVIEW_FAILED")
    review.return_percent = None
    db.commit()
    row, _ = AIReviewService(db, enabled_settings()).analyze(review, opportunity)
    assert row.status == "SKIPPED"


def test_mock_excluded_from_real_statistics(db):
    opportunity, review = add_review(db)
    AIReviewService(db, enabled_settings()).analyze(review, opportunity)
    service = AIReviewService(db, enabled_settings())
    assert service.statistics()["total_analyses"] == 0
    assert service.statistics(include_mock=True)["total_analyses"] == 1


def test_investigation_conversion_is_pure():
    value = convert_investigation_item_to_issue(
        {"title": "调查"}, analysis_id=1, review_id=2, opportunity_id=3,
    )
    assert value == {"title": "调查", "analysis_id": 1, "review_id": 2, "opportunity_id": 3}


def test_env_config_defaults():
    settings = Settings(_env_file=None)
    assert not settings.ai_review_enabled
    assert settings.ai_review_batch_size == 20
    assert settings.ai_review_prompt_version == "v1"


def test_scheduler_disabled_returns_immediately():
    scheduler = AIReviewScheduler(Settings(ai_review_auto_run=True, ai_review_enabled=False))
    assert scheduler.trigger() is False and scheduler.thread is None


def test_telegram_ai_review_admin_and_mock_hidden(db):
    opportunity, review = add_review(db)
    AIReviewService(db, enabled_settings()).analyze(review, opportunity)
    service = TelegramCommandService(db, Settings(telegram_admin_ids="42"))
    ok, text = service.handle("42", "/ai_review")
    assert ok and "暂无已完成" in text
    assert service.handle("7", "/ai_review")[0] is False
