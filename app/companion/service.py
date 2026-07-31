import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.companion.context import CompanionContextBuilder
from app.companion.mock_provider import MockCompanionProvider
from app.companion.provider import GeminiCompanionProvider
from app.companion.repository import CompanionRepository
from app.companion.schemas import CONTEXT_SCHEMA_VERSION, RESPONSE_SCHEMA_VERSION
from app.companion.templates import build_prompt, get_template
from app.companion.validation import CompanionResponseValidator, safe_error
from app.core.config import get_settings
from app.trade_review.service import TradeReviewService


logger = logging.getLogger(__name__)


class CompanionService:
    def __init__(self, db, settings=None, repository=None, provider_factory=None):
        self.settings = settings or get_settings()
        self.repository = repository or CompanionRepository(db)
        self.context_builder = CompanionContextBuilder(
            self.repository, TradeReviewService(db),
        )
        self.provider_factory = provider_factory
        self.validator = CompanionResponseValidator()

    def generate_trade_plan_analysis(self, plan_id, **options):
        return self._generate("TRADE_PLAN", plan_id, **options)

    def generate_position_analysis(self, position_id, **options):
        return self._generate("USER_POSITION", position_id, **options)

    def generate_review_analysis(self, review_id, **options):
        return self._generate("TRADE_REVIEW", review_id, **options)

    def generate_statistics_analysis(self, **options):
        return self._generate("STATISTICS", "global", **options)

    def get(self, analysis_id):
        return self.repository.get_analysis(analysis_id)

    def list(self, **filters):
        return self.repository.list(**filters)

    def count(self, **filters):
        filters.pop("limit", None)
        filters.pop("offset", None)
        return self.repository.count(**filters)

    def source_summary(self, analysis):
        plan = self.repository.get_plan_by_id(analysis.trade_plan_id) if analysis.trade_plan_id else None
        return {
            "symbol": plan.symbol if plan else None,
            "lifecycle_stage": plan.lifecycle_stage if plan else None,
            "direction": plan.direction if plan else None,
            "timeframe": plan.timeframe if plan else None,
        }

    def _generate(
        self, context_type, object_id, language=None, provider=None,
        force=False, dry_run=True,
    ):
        language = language or self.settings.ai_companion_default_language
        configured_provider = provider or self.settings.ai_companion_provider
        if configured_provider not in {"mock", self.settings.ai_companion_provider}:
            raise ValueError("请求的AI Companion Provider不在配置白名单中。")
        context, updated_at, refs = self._context(context_type, object_id)
        template = get_template(self._template_id(context_type), language)
        provider_object = self._provider(configured_provider)
        context_json = context.model_dump_json(indent=2)
        if len(context_json) > 100000:
            raise ValueError("Companion Context超过安全长度限制。")
        prompt = build_prompt(template, context_json)
        input_hash = hashlib.sha256(context.model_dump_json().encode("utf-8")).hexdigest()
        fingerprint = self._analysis_key(
            context_type, object_id, input_hash, template.template_version,
            language, provider_object.name, provider_object.model,
        )
        key = fingerprint if not force else hashlib.sha256(
            (fingerprint + ":" + str(uuid.uuid4())).encode("utf-8"),
        ).hexdigest()
        if dry_run:
            logger.info(
                "Companion dry-run context_type=%s object_id=%s template=%s provider=%s",
                context_type, object_id, template.template_id, provider_object.name,
            )
            return {
                "dry_run": True, "analysis_key": key, "input_hash": input_hash,
                "context": json.loads(context_json), "prompt_preview": prompt,
                "template_id": template.template_id,
                "template_version": template.template_version,
                "provider": provider_object.name, "model": provider_object.model,
            }
        if not self.settings.ai_companion_enabled:
            raise ValueError("AI Companion当前未启用；可使用dry-run预览。")
        existing = None if force else self.repository.find_slot(fingerprint)
        if existing and existing.status == "COMPLETED":
            return {"dry_run": False, "cached": True, "analysis": existing}
        now = datetime.now(timezone.utc)
        values = {
            "analysis_key": key, "request_fingerprint": fingerprint,
            "cache_key": None if force else fingerprint, "input_hash": input_hash,
            "context_type": context_type,
            "trade_plan_id": refs["trade_plan_id"],
            "user_position_id": refs["user_position_id"],
            "trade_review_id": refs["trade_review_id"],
            "user_id": refs["user_id"],
            "language": language, "template_id": template.template_id,
            "template_version": template.template_version,
            "context_schema_version": CONTEXT_SCHEMA_VERSION,
            "response_schema_version": RESPONSE_SCHEMA_VERSION,
            "provider": provider_object.name, "model": provider_object.model,
            "status": "PENDING", "summary": None,
            "structured_response_json": None,
            "context_snapshot_json": json.loads(context_json),
            "error_code": None, "error_summary": None,
            "request_started_at": now, "request_completed_at": None,
            "request_source": "ADMIN_FORCE" if force else "ADMIN_API",
            "token_input": None, "token_output": None, "latency_ms": None,
        }
        row = self.repository.save(values, existing)
        self.repository.commit()
        started = time.monotonic()
        try:
            result = provider_object.generate(context, template)
            response = self.validator.validate(result.response)
            response_value = response.model_dump()
            response_value["provider_metadata"] = {
                **response_value.get("provider_metadata", {}),
                "provider": result.provider, "model": result.model,
                "request_id": result.request_id, "latency_ms": result.latency_ms,
            }
            completed = datetime.now(timezone.utc)
            self.repository.save({
                "status": "COMPLETED", "summary": response.summary,
                "structured_response_json": response_value,
                "request_completed_at": completed,
                "token_input": result.token_input, "token_output": result.token_output,
                "latency_ms": result.latency_ms,
            }, row)
            self.repository.commit()
            logger.info(
                "Companion completed analysis_id=%s type=%s object_id=%s template=%s "
                "provider=%s language=%s force=%s latency_ms=%s validation=passed",
                row.id, context_type, object_id, template.template_id,
                provider_object.name, language, force,
                int((time.monotonic() - started) * 1000),
            )
            return {"dry_run": False, "cached": False, "analysis": row}
        except Exception as exc:
            self.repository.rollback()
            current = self.repository.find_key(key)
            code = "RESPONSE_REJECTED" if isinstance(exc, ValueError) else "PROVIDER_FAILED"
            self.repository.save({
                "status": "REJECTED" if isinstance(exc, ValueError) else "FAILED",
                "error_code": code, "error_summary": safe_error(exc),
                "request_completed_at": datetime.now(timezone.utc),
            }, current)
            self.repository.commit()
            logger.warning(
                "Companion failed analysis_id=%s type=%s object_id=%s provider=%s "
                "status=%s error_code=%s",
                current.id, context_type, object_id, provider_object.name,
                current.status, code,
            )
            return {"dry_run": False, "cached": False, "analysis": current}

    def _context(self, context_type, object_id):
        if context_type == "TRADE_PLAN":
            return self.context_builder.build_trade_plan_context(str(object_id))
        if context_type == "USER_POSITION":
            return self.context_builder.build_user_position_context(int(object_id))
        if context_type == "TRADE_REVIEW":
            return self.context_builder.build_trade_review_context(int(object_id))
        return self.context_builder.build_statistics_context()

    def _provider(self, name):
        if self.provider_factory:
            return self.provider_factory(name)
        if name == "mock":
            return MockCompanionProvider()
        return GeminiCompanionProvider(
            self.settings.ai_companion_api_key, self.settings.ai_companion_model,
            self.settings.ai_companion_timeout_seconds,
            self.settings.ai_companion_max_output_tokens,
        )

    @staticmethod
    def _template_id(context_type):
        return {
            "TRADE_PLAN": "TRADE_PLAN_EXPLANATION",
            "USER_POSITION": "POSITION_COMPANION",
            "TRADE_REVIEW": "REVIEW_SUMMARY",
            "STATISTICS": "STATISTICS_EXPLANATION",
        }[context_type]

    @staticmethod
    def _analysis_key(context_type, object_id, input_hash, template_version,
                      language, provider, model):
        value = json.dumps({
            "context_type": context_type, "object_id": str(object_id),
            "input_hash": input_hash,
            "template_version": template_version, "language": language,
            "provider": provider, "model": model,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
