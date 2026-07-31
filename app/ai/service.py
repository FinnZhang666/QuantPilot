import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional

from pydantic import ValidationError
from sqlalchemy import desc, func, select

from app.ai.config import build_provider
from app.ai.prompts import prompt_for, prompt_hash
from app.ai.repository import AIReviewRepository
from app.ai.schemas import (
    AIReviewRequest, AnalysisMetadata, CandidatePoolContext, HistoricalGroup,
    HistoricalStatisticsContext, MarketRegimeContext, OpportunityContext,
    ReviewContext, StrategyContext,
)
from app.ai.validation import validate_review_for_ai
from app.core.config import get_settings
from app.database.models import (
    AIReviewAnalysis, CandidatePoolEntry, MarketRegime, Opportunity,
    OpportunityReview, ReviewStatistic,
)


ANALYSIS_VERSION = "1.0.0"
logger = logging.getLogger(__name__)


class AIReviewService:
    def __init__(self, db, settings=None, provider=None):
        self.db = db
        self.settings = settings or get_settings()
        self.provider = provider or build_provider(self.settings)
        self.repository = AIReviewRepository(db)

    def pending(self, limit=None, symbol=None):
        query = select(OpportunityReview, Opportunity).join(
            Opportunity, Opportunity.id == OpportunityReview.opportunity_id,
        ).outerjoin(
            AIReviewAnalysis,
            (AIReviewAnalysis.opportunity_review_id == OpportunityReview.id)
            & (AIReviewAnalysis.provider == self.provider.name)
            & (AIReviewAnalysis.model == self.provider.model)
            & (AIReviewAnalysis.status == "COMPLETED"),
        ).where(
            OpportunityReview.review_status == "REVIEWED",
            AIReviewAnalysis.id.is_(None),
        )
        if symbol:
            query = query.where(Opportunity.symbol == _symbol(symbol))
        return list(self.db.execute(query.order_by(
            OpportunityReview.review_time,
        ).limit(limit or self.settings.ai_review_batch_size)))

    def run(self, limit=None, review_id=None, symbol=None):
        result = {
            "enabled": self.settings.ai_review_enabled, "scanned": 0,
            "completed": 0, "failed": 0, "skipped": 0,
            "insufficient_data": 0, "existing": 0, "ids": [],
        }
        if not self.settings.ai_review_enabled:
            return result
        rows = self.pending(limit=limit, symbol=symbol)
        if review_id is not None:
            rows = [row for row in rows if row[0].id == review_id]
            if not rows:
                review = self.db.get(OpportunityReview, review_id)
                opportunity = self.db.get(Opportunity, review.opportunity_id) if review else None
                rows = [(review, opportunity)] if review and opportunity else []
        for review, opportunity in rows:
            result["scanned"] += 1
            try:
                analysis, created = self.analyze(review, opportunity)
                bucket = {
                    "COMPLETED": "completed", "FAILED": "failed",
                    "SKIPPED": "skipped", "INSUFFICIENT_DATA": "insufficient_data",
                }.get(analysis.status, "failed")
                result[bucket] += 1
                if not created:
                    result["existing"] += 1
                result["ids"].append(analysis.id)
            except Exception:
                self.db.rollback()
                result["failed"] += 1
        return result

    def analyze(self, review, opportunity=None):
        opportunity = opportunity or self.db.get(Opportunity, review.opportunity_id)
        if opportunity is None:
            raise ValueError("Opportunity不存在。")
        request = self.build_request(opportunity, review)
        snapshot = request.model_dump(mode="json")
        input_hash = _hash(snapshot)
        existing = self.repository.find_identity(
            review.id, ANALYSIS_VERSION, self.provider.name,
            self.provider.model, input_hash,
        )
        if existing:
            return existing, False
        prompt = prompt_for(self.settings.ai_review_prompt_version)
        record = AIReviewAnalysis(
            opportunity_id=opportunity.id, opportunity_review_id=review.id,
            analysis_version=ANALYSIS_VERSION, provider=self.provider.name,
            model=self.provider.model, status="PENDING",
            input_snapshot_json=snapshot, input_hash=input_hash,
            prompt_version=self.settings.ai_review_prompt_version,
            prompt_text_hash=prompt_hash(prompt), retry_count=0,
        )
        self.db.add(record)
        self.db.commit()
        status, reason = validate_review_for_ai(review, self.settings.ai_review_min_window)
        if status:
            record.status = status
            record.error_code = status
            record.error_message = reason
            record.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            return record, True
        return self._execute(record, request), True

    def retry(self, analysis_id: int):
        record = self.repository.get(analysis_id)
        if record is None:
            raise ValueError("AI Review Analysis不存在。")
        if record.status not in {"FAILED", "SKIPPED", "INSUFFICIENT_DATA"}:
            return record
        request = AIReviewRequest.model_validate(record.input_snapshot_json)
        return self._execute(record, request)

    def build_request(self, opportunity, review):
        stats = review.statistics_json or {}
        path = review.price_path_json or []
        prices = [Decimal(str(item["close"])) for item in path if item.get("close") is not None]
        regime = self.db.get(MarketRegime, opportunity.market_regime_id) if opportunity.market_regime_id else None
        candidate = self.db.get(CandidatePoolEntry, opportunity.candidate_pool_entry_id) if opportunity.candidate_pool_entry_id else None
        return AIReviewRequest(
            opportunity=OpportunityContext(
                symbol=opportunity.symbol, direction=opportunity.direction,
                strategy=opportunity.strategy_name, timeframe=opportunity.timeframe,
                entry_price=str(opportunity.entry_reference_price),
                detected_at=_iso(opportunity.detected_at),
                confidence=opportunity.confidence, score=opportunity.score,
                target_price=_value(opportunity.target_reference_price),
                stop_price=_value(opportunity.stop_reference_price),
                expiry=_iso(opportunity.expiry_at),
            ),
            review=ReviewContext(
                final_status=review.review_status, reviewed_at=_iso(review.review_time),
                review_window=review.review_window,
                return_percent=str(review.return_percent),
                mfe_percent=str(review.mfe_percent), mae_percent=str(review.mae_percent),
                holding_duration={
                    "bars": review.holding_bars, "minutes": review.holding_minutes,
                    "days": str(review.holding_days),
                },
                target_hit=review.target_hit, stop_hit=review.stop_hit,
                price_path_summary={
                    "bars": len(path), "first_time": path[0].get("timestamp") if path else None,
                    "last_time": path[-1].get("timestamp") if path else None,
                    "highest_close": str(max(prices)) if prices else None,
                    "lowest_close": str(min(prices)) if prices else None,
                },
                window_returns=stats.get("window_returns", {}),
                data_quality="VALID" if path else "INSUFFICIENT",
                failure_reason=(review.reason_json or {}).get("message"),
            ),
            market_regime=self._regime_context(regime),
            candidate_pool=self._candidate_context(candidate),
            feature_snapshot=opportunity.feature_snapshot_json or None,
            strategy=StrategyContext(
                name=opportunity.strategy_name, version=opportunity.strategy_version,
                opportunity_type=opportunity.opportunity_type,
                decision_snapshot=opportunity.decision_snapshot_json or {},
            ),
            historical_statistics=self._historical(opportunity),
            metadata=AnalysisMetadata(
                analysis_version=ANALYSIS_VERSION,
                prompt_version=self.settings.ai_review_prompt_version,
                generated_at=datetime.now(timezone.utc).isoformat(),
            ),
        )

    def statistics(self, include_mock=False):
        query = select(AIReviewAnalysis)
        if not include_mock:
            query = query.where(AIReviewAnalysis.provider != "mock")
        rows = list(self.db.scalars(query))
        total_reviews = self.db.scalar(select(func.count()).select_from(
            OpportunityReview,
        ).where(OpportunityReview.review_status == "REVIEWED")) or 0
        completed = [row for row in rows if row.status == "COMPLETED"]
        return {
            "total_analyses": len(rows),
            "completed": len(completed),
            "failed": sum(row.status == "FAILED" for row in rows),
            "skipped": sum(row.status == "SKIPPED" for row in rows),
            "insufficient_data": sum(row.status == "INSUFFICIENT_DATA" for row in rows),
            "pending": sum(row.status in {"PENDING", "RUNNING"} for row in rows),
            "coverage_rate": round(len(completed) / total_reviews * 100, 4) if total_reviews else 0,
            "average_confidence": _average([row.confidence_score for row in completed]),
            "average_latency_ms": _average([row.latency_ms for row in completed]),
            "token_input": sum(row.token_input or 0 for row in rows),
            "token_output": sum(row.token_output or 0 for row in rows),
            "estimated_cost": str(sum((row.estimated_cost or Decimal("0")) for row in rows)),
            "provider_distribution": _counts(rows, "provider"),
            "model_distribution": _counts(rows, "model"),
            "classification_distribution": _classification_counts(completed),
            "investigation_priority_distribution": _priority_counts(completed),
            "mock_excluded": not include_mock,
        }

    def _execute(self, record, request):
        record.status = "RUNNING"
        record.started_at = datetime.now(timezone.utc)
        record.error_code = None
        record.error_message = None
        self.db.commit()
        started = time.perf_counter()
        last_error = None
        for attempt in range(self.settings.ai_review_max_retries + 1):
            record.retry_count = attempt
            try:
                result = self.provider.analyze_review(request)
                response = result.response
                record.summary = response.summary
                record.outcome_explanation = response.timing_analysis.mfe_mae_interpretation
                record.positive_factors_json = response.positive_factors
                record.negative_factors_json = response.negative_factors
                record.risk_factors_json = response.risk_factors
                record.timing_analysis_json = response.timing_analysis.model_dump()
                record.market_regime_analysis_json = response.market_regime_analysis.model_dump()
                record.historical_comparison_json = dict(
                    response.historical_comparison.model_dump(),
                    outcome_classification=response.outcome_classification,
                    facts=response.facts,
                )
                record.investigation_items_json = [
                    dict(item.model_dump(), analysis_id=record.id,
                         review_id=record.opportunity_review_id,
                         opportunity_id=record.opportunity_id)
                    for item in response.investigation_items
                ]
                record.confidence_score = response.confidence_score
                record.uncertainty_notes = response.uncertainty_notes
                record.raw_response_json = (
                    result.raw_response if self.settings.ai_review_store_raw_response else None
                )
                record.token_input = result.token_input
                record.token_output = result.token_output
                record.estimated_cost = (
                    Decimal(result.estimated_cost) if result.estimated_cost else None
                )
                record.status = "COMPLETED"
                record.completed_at = datetime.now(timezone.utc)
                record.latency_ms = int((time.perf_counter() - started) * 1000)
                self.db.commit()
                self._sync_research(record.opportunity_id)
                return record
            except Exception as exc:
                last_error = exc
        record.status = "FAILED"
        record.completed_at = datetime.now(timezone.utc)
        record.latency_ms = int((time.perf_counter() - started) * 1000)
        record.error_code = type(last_error).__name__ if last_error else "UNKNOWN_ERROR"
        record.error_message = _safe_error(last_error)
        self.db.commit()
        self._sync_research(record.opportunity_id)
        return record

    def _sync_research(self, opportunity_id):
        try:
            from app.research.service import ResearchService
            workspace = ResearchService(self.db).ensure_workspace(opportunity_id)
            ResearchService(self.db).sync(workspace.id)
        except Exception:
            self.db.rollback()
            logger.exception(
                "Research workspace synchronization failed after AI review",
                extra={
                    "event": "research_workspace_sync_failed",
                    "context": {"opportunity_id": opportunity_id, "source": "ai_review"},
                },
            )

    def _regime_context(self, row):
        if row is None:
            return None
        return MarketRegimeContext(
            regime=row.regime, confidence=row.confidence, trend=row.trend_score,
            volatility=row.volatility_score, breadth=row.breadth_score,
            risk_state=row.risk_score, generated_at=_iso(row.evaluated_at),
        )

    def _candidate_context(self, row):
        if row is None:
            return None
        snapshot = row.reason_snapshot_json or {}
        return CandidatePoolContext(
            pool_score=row.final_score, rank=row.rank, direction=row.direction,
            reasons=snapshot.get("reasons", []),
            rejected_reasons=snapshot.get("risks", []), run_id=None,
        )

    def _historical(self, opportunity):
        return HistoricalStatisticsContext(
            same_strategy=self._group(strategy=opportunity.strategy_name),
            same_symbol=self._group(symbol=opportunity.symbol),
            same_timeframe=self._group(timeframe=opportunity.timeframe),
            same_direction=self._group(direction=opportunity.direction),
            same_market_regime=(
                self._group(regime=opportunity.market_regime)
                if opportunity.market_regime else HistoricalGroup()
            ),
            global_statistics=self._group(),
        )

    def _group(self, strategy=None, symbol=None, timeframe=None, direction=None, regime=None):
        filters = [OpportunityReview.review_status == "REVIEWED"]
        if strategy:
            filters.append(Opportunity.strategy_name == strategy)
        if symbol:
            filters.append(Opportunity.symbol == symbol)
        if timeframe:
            filters.append(Opportunity.timeframe == timeframe)
        if direction:
            filters.append(Opportunity.direction == direction)
        if regime:
            filters.append(Opportunity.market_regime == regime)
        rows = list(self.db.execute(select(OpportunityReview).join(
            Opportunity, Opportunity.id == OpportunityReview.opportunity_id,
        ).where(*filters)).scalars())
        returns = [Decimal(str(row.return_percent)) for row in rows if row.return_percent is not None]
        mfes = [Decimal(str(row.mfe_percent)) for row in rows if row.mfe_percent is not None]
        maes = [Decimal(str(row.mae_percent)) for row in rows if row.mae_percent is not None]
        return HistoricalGroup(
            sample_size=len(rows),
            success_rate=str(sum(value > 0 for value in returns) / len(returns) * 100 if returns else 0),
            average_return=str(_decimal_average(returns)),
            average_mfe=str(_decimal_average(mfes)), average_mae=str(_decimal_average(maes)),
            max_return=str(max(returns) if returns else 0),
            max_drawdown=str(min(maes) if maes else 0),
            coverage_rate="100" if rows else "0",
        )


def convert_investigation_item_to_issue(item, analysis_id, review_id, opportunity_id):
    """Sprint 12 integration seam. This function does not write Development Issues."""
    return {
        **item, "analysis_id": analysis_id, "review_id": review_id,
        "opportunity_id": opportunity_id,
    }


def _hash(value):
    stable = json.loads(json.dumps(value, ensure_ascii=False))
    if isinstance(stable.get("metadata"), dict):
        stable["metadata"].pop("generated_at", None)
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_error(exc):
    if exc is None:
        return "未知错误。"
    if isinstance(exc, ValidationError):
        return "AI结构化输出未通过Schema校验。"
    name = type(exc).__name__
    if "Timeout" in name:
        return "AI Provider请求超时。"
    return "AI Provider调用失败：" + name


def _symbol(value):
    return value.upper().replace("US.", "")


def _iso(value):
    return value.isoformat() if value is not None else None


def _value(value):
    return str(value) if value is not None else None


def _average(values):
    valid = [value for value in values if value is not None]
    return round(sum(valid) / len(valid), 4) if valid else 0


def _decimal_average(values):
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def _counts(rows, field):
    result = {}
    for row in rows:
        value = getattr(row, field) or "UNKNOWN"
        result[value] = result.get(value, 0) + 1
    return result


def _classification_counts(rows):
    result = {}
    for row in rows:
        raw = row.historical_comparison_json or {}
        value = raw.get("outcome_classification") or "UNKNOWN"
        result[value] = result.get(value, 0) + 1
    return result


def _priority_counts(rows):
    result = {}
    for row in rows:
        for item in row.investigation_items_json or []:
            value = item.get("priority", "UNKNOWN")
            result[value] = result.get(value, 0) + 1
    return result
