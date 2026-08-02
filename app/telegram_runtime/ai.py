import hashlib
import json
import time
from typing import Callable, Dict, Optional

import httpx
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import (
    CandidateSignal,
    MarketBar,
    MarketRegime,
    SystemPaperPosition,
    TelegramAIInvocation,
    TradeReview,
)


SYSTEM_RULE = (
    "You are Trade Companion, an AI assistant that explains system-provided trading data. "
    "All numbers are supplied by the system. Do not recalculate, change, or invent "
    "numbers, statistics, prices, returns, scores, MFE, or MAE. Explain only. "
    "Never claim to place trades and never present content as financial advice. "
    "Use numbered headings and the Unicode bullet character. Never output Markdown "
    "asterisks or hash characters."
)

ANALYST_RESPONSE_CONTRACT = (
    "Translate technical data into plain language for an ordinary investor. Start with "
    "a direct analyst conclusion. Separate Stock quality (whether it is worth watching) "
    "from Entry timing (whether now is a reasonable time to consider entry). Use only "
    "these decision labels, translated into the requested language: Worth watching; "
    "Wait for an entry; Small-position trial; Not suitable now; Hold and observe; "
    "Consider reducing; High risk and avoid. Then explain: why; why not to buy now when "
    "applicable; who this setup suits; what system-provided conditions to watch next; "
    "and data limitations. A good stock is not automatically a good entry. If data is "
    "missing or signals conflict, say so and avoid a strong conclusion. Never invent an "
    "entry price, stop, target, probability, forecast, or new statistic. Do not output "
    "asterisk or hash characters anywhere. Use plain numbered section titles and Unicode "
    "bullet points only."
)


class GeminiAdapter:
    """Minimal Gemini REST adapter with an injectable transport."""

    def __init__(
        self, settings: Settings,
        transport: Optional[Callable[[str, str, Dict[str, object], float], Dict[str, object]]] = None,
    ):
        self.settings = settings
        self.transport = transport or self._http_transport

    def generate(self, prompt: str) -> Dict[str, object]:
        key = self.settings.ai_companion_api_key or self.settings.gemini_api_key
        model = self.settings.ai_companion_model
        if not model or model.startswith("mock"):
            model = self.settings.llm_model
        if not key:
            raise RuntimeError("Gemini API key is not configured.")
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": min(self.settings.ai_companion_max_output_tokens, 1024),
            },
        }
        raw = self.transport(key, model, payload, self.settings.ai_companion_timeout_seconds)
        candidates = raw.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no text output.")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        if not text:
            raise RuntimeError("Gemini returned no text output.")
        usage = raw.get("usageMetadata") or {}
        return {
            "text": text,
            "model": model,
            "prompt_tokens": int(usage.get("promptTokenCount") or 0),
            "completion_tokens": int(usage.get("candidatesTokenCount") or 0),
        }

    @staticmethod
    def _http_transport(key: str, model: str, payload: Dict[str, object], timeout: float):
        safe_model = model.replace("models/", "")
        url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % safe_model
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers={"x-goog-api-key": key}, json=payload)
        if response.status_code >= 400:
            raise RuntimeError("Gemini request failed with HTTP %s." % response.status_code)
        return response.json()


class TelegramAIService:
    def __init__(self, db: Session, settings: Settings, adapter: Optional[GeminiAdapter] = None):
        self.db = db
        self.settings = settings
        self.adapter = adapter or GeminiAdapter(settings)

    def explain(
        self, operation: str, language: str, bot_alias: str,
        user_id: Optional[int], symbol: Optional[str] = None,
        question: Optional[str] = None,
        related_symbols: Optional[list] = None,
    ) -> str:
        context = self._context(operation, symbol)
        if related_symbols:
            context["related_symbols"] = [str(value)[:12] for value in related_symbols[:5]]
        if question:
            context["user_question"] = str(question)[:1000]
        prompt = "%s\n%s\nLanguage: %s\nOperation: %s\nSystem context: %s" % (
            SYSTEM_RULE, ANALYST_RESPONSE_CONTRACT, language, operation,
            json.dumps(context, ensure_ascii=False, default=str),
        )
        fingerprint = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        started = time.perf_counter()
        provider = "gemini" if self.settings.ai_companion_enabled else "fallback"
        status = "FALLBACK"
        error_code = None
        prompt_tokens = completion_tokens = 0
        model = self.settings.ai_companion_model
        try:
            if not self.settings.ai_companion_enabled:
                raise RuntimeError("AI Companion is disabled.")
            result = self.adapter.generate(prompt)
            text = result["text"]
            model = str(result["model"])
            prompt_tokens = int(result["prompt_tokens"])
            completion_tokens = int(result["completion_tokens"])
            status = "SUCCESS"
        except Exception as exc:
            error_code = type(exc).__name__[:64]
            text = self._fallback(operation, language, context)
        latency_ms = int((time.perf_counter() - started) * 1000)
        self.db.add(TelegramAIInvocation(
            user_id=user_id, bot_alias=bot_alias, operation=operation,
            symbol=symbol, provider=provider, model=model or "fallback-v1",
            status=status, input_hash=fingerprint, latency_ms=latency_ms,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            error_code=error_code,
        ))
        self.db.commit()
        return text

    def _context(self, operation: str, symbol: Optional[str]) -> Dict[str, object]:
        context: Dict[str, object] = {
            "operation": operation, "data_source": "Trade Companion Backend",
        }
        if symbol:
            normalized = symbol.upper().replace("US.", "")
            variants = (normalized, "US." + normalized)
            bar = self.db.scalar(select(MarketBar).where(
                MarketBar.symbol.in_(variants), MarketBar.interval == "1d",
            ).order_by(desc(MarketBar.timestamp_utc), desc(MarketBar.id)).limit(1))
            signal = self.db.scalar(select(CandidateSignal).where(
                CandidateSignal.symbol.in_(variants),
            ).order_by(desc(CandidateSignal.bar_timestamp), desc(CandidateSignal.id)).limit(1))
            context["symbol"] = normalized
            context["latest_bar"] = None if bar is None else {
                "timestamp": bar.timestamp_utc, "close": bar.close,
                "change_rate": bar.change_rate, "volume": bar.volume,
            }
            context["signal"] = None if signal is None else {
                "type": signal.signal_type, "score": signal.score,
                "confidence": signal.confidence, "status": signal.status,
                "reasons": signal.reasons_json, "risks": signal.risks_json,
            }
        regime = self.db.scalar(select(MarketRegime).order_by(
            desc(MarketRegime.bar_time), desc(MarketRegime.id),
        ).limit(1))
        if regime:
            context["market"] = {
                "regime": regime.regime, "trend_score": regime.trend_score,
                "momentum_score": regime.momentum_score, "risk_score": regime.risk_score,
                "confidence": regime.confidence, "bar_time": regime.bar_time,
            }
        if operation == "POSITION_EXPLAIN" and symbol:
            position = self.db.scalar(select(SystemPaperPosition).where(
                SystemPaperPosition.symbol == symbol.upper().replace("US.", ""),
                SystemPaperPosition.status == "OPEN",
            ).order_by(desc(SystemPaperPosition.open_time)).limit(1))
            if position:
                context["position"] = {
                    "direction": position.direction, "entry": position.average_entry,
                    "current_price": position.current_price, "unrealized_pnl": position.unrealized_pnl,
                    "mfe": position.mfe, "mae": position.mae, "stop": position.stop_price,
                    "targets": position.targets_json,
                }
        if operation in {"TRADE_EXPLAIN", "STRATEGY_REVIEW"}:
            review = self.db.scalar(select(TradeReview).where(
                TradeReview.review_type == "SYSTEM",
            ).order_by(desc(TradeReview.review_time), desc(TradeReview.id)).limit(1))
            if review:
                context["review"] = {
                    "result": review.result, "realized_return": review.realized_return,
                    "mfe": review.mfe, "mae": review.mae,
                    "exit_reason": review.exit_reason, "strategy": review.strategy_name,
                }
        return context

    @staticmethod
    def _fallback(operation: str, language: str, context: Dict[str, object]) -> str:
        zh = language == "zh-CN"
        if zh:
            return "AI 暂时不可用。以下为系统数据快照（未重新计算）：\n%s" % json.dumps(
                context, ensure_ascii=False, default=str, indent=2,
            )[:3000]
        return "AI is temporarily unavailable. System snapshot (not recalculated):\n%s" % json.dumps(
            context, ensure_ascii=False, default=str, indent=2,
        )[:3000]
