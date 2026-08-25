from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.qmr.providers import DatabaseFundamentalsProvider, EventAssessment, NoNewsProvider
from app.qmr.repository import QmrRepository
from app.qmr.scoring import mispricing_score, quality_score


class QmrService:
    def __init__(self, db, settings, fundamentals=None, news=None, config_path=None):
        self.db = db
        self.settings = settings
        path = config_path or settings.qmr_config_file
        self.config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        self.repository = QmrRepository(db)
        self.fundamentals = fundamentals or DatabaseFundamentalsProvider(db)
        self.news = news or NoNewsProvider()

    def run(self, evaluation_time=None, symbols=None, dry_run=False, limit=None):
        at = evaluation_time or datetime.now(timezone.utc)
        funds = self.config.get("universe_codes", ["QQQ", "SPY"])
        universe, source_metadata, universe_stats = self.repository.unified_universe(
            at, funds, symbols, self.config.get("universe_exclude_source_etfs", True))
        if limit: universe = universe[:limit]
        result = {"evaluation_time": at, "scanned": len(universe), "created": 0,
                  "candidates": 0, "skipped": 0, "failed": 0,
                  "reason_counts": {}, "items": [], "universe": universe_stats}
        for item in universe:
            try:
                payload = self.evaluate(item, at)
                membership = source_metadata[item.symbol]
                payload["mispricing_components"]["source_universes"] = membership["source_universes"]
                payload["mispricing_components"]["source_count"] = membership["source_count"]
                for code in payload.get("reason_codes", []):
                    result["reason_counts"][code] = result["reason_counts"].get(code, 0) + 1
                if not payload.get("reason_codes") and payload["event"].fundamental_risk != "HIGH":
                    result["candidates"] += 1
                if dry_run:
                    result["items"].append(self._serialize_evaluation(item.symbol, payload)); result["skipped"] += 1
                    continue
                row, created = self.repository.save(item, at, **payload, model_version=self.config["version"], thresholds=self.config["thresholds"])
                result["created" if created else "skipped"] += 1
                result["items"].append(self.serialize(row))
            except Exception as exc:
                self.db.rollback(); result["failed"] += 1
                result["items"].append({"symbol": item.symbol, "error": type(exc).__name__})
        return result

    def evaluate(self, item, at):
        configured = set(self.config.get("universe_codes", ["QQQ", "SPY"]))
        memberships = [row for row in self.repository.memberships(item.id, at)
                       if row.fund_symbol in configured]
        weights = {m.fund_symbol: float(m.weight) if m.weight is not None else None for m in memberships}
        prices = self.repository.bars(item.symbol, at)
        average_dollar_volume = None
        if prices:
            sample = prices[-20:]
            average_dollar_volume = sum(float(x.close) * x.volume for x in sample) / len(sample)
        fundamental_symbol = self.repository.fundamental_symbol(item.symbol)
        fundamental = self.fundamentals.get_as_of(fundamental_symbol, at)
        context = {"qqq_weight": weights.get("QQQ"), "spy_weight": weights.get("SPY"),
                   "average_dollar_volume": average_dollar_volume, "industry_relative_strength": None}
        q_score, q_components, coverage = quality_score(fundamental, context, self.config)
        benchmark = "QQQ" if "QQQ" in weights else "SPY"
        benchmark_prices = self.repository.bars(benchmark, at)
        sector_names = self.config.get("sector_benchmarks", {}).get(item.sector, self.config.get("sector_benchmarks", {}).get("default", []))
        industry_prices = []
        industry_symbol = None
        for candidate in sector_names:
            rows = self.repository.bars(candidate, at)
            if rows:
                industry_prices, industry_symbol = rows, candidate
                break
        event = self.news.assess(item.symbol, at)
        financial_risk = self._financial_risk(fundamental)
        small_cap_reasons = []
        memberships_set = set(weights)
        if "IWM" in memberships_set and not memberships_set.intersection({"SPY", "QQQ"}):
            passed, small_cap_reasons = self._small_cap_quality_gate(
                item, fundamental, average_dollar_volume)
            if not passed:
                financial_risk = "HIGH"
        ranks = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
        if ranks.get(financial_risk, 0) > ranks.get(event.fundamental_risk, 0):
            event = EventAssessment(event.event_risk, financial_risk, event.confidence, event.source)
        valuation_context = self._valuation_context(fundamental)
        m_score, m_components = mispricing_score(
            prices, benchmark_prices, industry_prices, event, self.config, valuation_context)
        sources = ["UNIVERSE", "MARKET_BARS"]
        if fundamental: sources.append("FUNDAMENTAL:" + fundamental.source)
        sources.append(event.source)
        confidence = "HIGH" if coverage >= .8 and len(prices) >= 252 and event.confidence == "HIGH" else ("MEDIUM" if coverage >= .65 and len(prices) >= 60 else "LOW")
        m_components["benchmark"] = benchmark
        m_components["industry_benchmark"] = industry_symbol
        m_components["small_cap_quality_gate"] = {"passed": not small_cap_reasons,
                                                   "reasons": small_cap_reasons}
        missing_quality = [name for name, value in q_components.items() if value["coverage"] < 1]
        reason_codes = self._reason_codes(q_score, coverage, m_score, len(prices), fundamental, at)
        m_components["fundamental_symbol"] = fundamental_symbol
        m_components["instrument_mapping_applied"] = fundamental_symbol != item.symbol
        m_components["reason_codes"] = reason_codes
        m_components["source_timestamp"] = fundamental.available_at.isoformat() if fundamental else None
        return {"quality": q_score, "quality_components": q_components, "coverage": coverage,
                "mispricing": m_score, "mispricing_components": m_components,
                "event": event, "sources": sources, "confidence": confidence,
                "reason_codes": reason_codes, "missing_factors": {
                    "quality": missing_quality,
                    "mispricing": m_components.get("missing_factors", []),
                }, "source_timestamp": fundamental.available_at if fundamental else None}

    @staticmethod
    def _valuation_context(fundamental):
        if fundamental is None:
            return {}
        payload = dict(fundamental.source_payload_json or {})
        payload.setdefault("fundamentals", {
            "revenue_growth": float(fundamental.revenue_yoy) if fundamental.revenue_yoy is not None else None,
            "earnings_growth": float(fundamental.eps_yoy) if fundamental.eps_yoy is not None else None,
            "negative_fcf_periods": payload.get("negative_fcf_periods", 0),
            "margin_change": payload.get("margin_change"),
            "leverage_change": payload.get("leverage_change"),
            "guidance_cuts": payload.get("guidance_cuts", 0),
            "relative_strength_20d": payload.get("relative_strength_20d"),
        })
        return payload

    def _reason_codes(self, quality, coverage, mispricing, price_count, fundamental, at):
        reasons = []
        thresholds = self.config["thresholds"]
        if price_count == 0:
            reasons.append("UNIVERSE_DATA_INCOMPLETE")
        if fundamental is None or coverage < thresholds["minimum_quality_coverage"]:
            reasons.append("FUNDAMENTALS_INSUFFICIENT")
        if quality < thresholds["quality_min"]:
            reasons.append("QUALITY_BELOW_THRESHOLD")
        if mispricing < thresholds["mispricing_min"]:
            reasons.append("MISPRICING_NOT_EXTREME")
        if fundamental is not None:
            age_days = (at - fundamental.available_at).days
            if age_days > self.config.get("freshness", {}).get("fundamentals_days", 120):
                reasons.append("DATA_STALE")
        return reasons

    def _small_cap_quality_gate(self, item, fundamental, average_dollar_volume):
        rules = self.config["small_cap_quality_gate"]
        reasons = []
        if item.market_cap is None or float(item.market_cap) < rules["market_cap_min"]:
            reasons.append("small_cap_market_cap_insufficient")
        if average_dollar_volume is None or average_dollar_volume < rules["average_dollar_volume_min"]:
            reasons.append("small_cap_liquidity_insufficient")
        if fundamental is None:
            return False, reasons + ["small_cap_fundamental_data_missing"]
        if rules["require_positive_net_income"] and (fundamental.net_income_ttm is None or fundamental.net_income_ttm <= 0):
            reasons.append("small_cap_profitability_gate_failed")
        if rules["require_positive_free_cash_flow"] and (fundamental.free_cash_flow is None or fundamental.free_cash_flow <= 0):
            reasons.append("small_cap_cashflow_gate_failed")
        if fundamental.debt_to_equity is None or fundamental.debt_to_equity > rules["debt_to_equity_max"]:
            reasons.append("small_cap_debt_gate_failed")
        dilution = (fundamental.source_payload_json or {}).get("share_dilution_yoy")
        if rules["require_dilution_data"] and dilution is None:
            reasons.append("small_cap_dilution_data_missing")
        return not reasons, reasons

    def _financial_risk(self, fundamental):
        if fundamental is None:
            return "UNKNOWN"
        rules = self.config["quality_rules"]
        red = sum((
            fundamental.net_income_ttm is not None and fundamental.net_income_ttm < 0,
            fundamental.free_cash_flow is not None and fundamental.free_cash_flow < 0,
            fundamental.debt_to_equity is not None and fundamental.debt_to_equity > rules["debt_to_equity_high"],
            fundamental.interest_coverage is not None and fundamental.interest_coverage < 0,
        ))
        return "HIGH" if red >= 3 else ("MEDIUM" if red >= 2 else "LOW")

    def list(self, **kwargs):
        rows, total = self.repository.list_candidates(**kwargs)
        return [self.serialize(row) for row in rows], total

    def detail(self, symbol):
        rows = self.repository.history(symbol)
        return [self.serialize(row) for row in rows]

    @staticmethod
    def _serialize_evaluation(symbol, payload):
        event = payload["event"]
        return {
            "symbol": symbol,
            "quality_score": payload["quality"],
            "mispricing_score": payload["mispricing"],
            "quality_coverage": payload["coverage"],
            "fundamental_risk": event.fundamental_risk,
            "event_risk": event.event_risk,
            "news_confidence": event.confidence,
            "score_components": {
                "quality": payload["quality_components"],
                "mispricing": payload["mispricing_components"],
            },
            "data_sources": payload["sources"],
            "data_confidence": payload["confidence"],
            "data_quality": {"coverage": payload["coverage"], "confidence": payload["confidence"],
                             "source_timestamp": payload.get("source_timestamp")},
            "coverage": {"quality": payload["coverage"],
                         "mispricing": payload["mispricing_components"].get("coverage", 0)},
            "confidence": payload["confidence"],
            "reason_codes": payload.get("reason_codes", []),
            "missing_factors": payload.get("missing_factors", {}),
            "source_timestamp": payload.get("source_timestamp"),
            "money_flow_status": "UNAVAILABLE",
            "candidate": not payload.get("reason_codes") and event.fundamental_risk != "HIGH",
        }

    @staticmethod
    def serialize(row):
        score = row.score_components_json or {}
        quality = score.get("quality", {})
        mispricing = score.get("mispricing", {})
        quality_coverage = sum(float(value.get("max", 0)) * float(value.get("coverage", 0))
                               for value in quality.values() if isinstance(value, dict)) / 100 if quality else 0
        reason_codes = mispricing.get("reason_codes", [])
        return {"id": row.id, "symbol": row.symbol, "evaluation_time": row.evaluation_time,
                "quality_score": row.quality_score, "mispricing_score": row.mispricing_score,
                "combined_score": row.combined_score, "fundamental_risk": row.fundamental_risk,
                "event_risk": row.event_risk, "candidate_status": row.candidate_status,
                "score_components": row.score_components_json, "data_sources": row.data_sources_json,
                "data_confidence": row.data_confidence, "model_version": row.model_version,
                "last_update": row.created_at,
                "data_quality": {"coverage": quality_coverage, "confidence": row.data_confidence},
                "coverage": {"quality": quality_coverage, "mispricing": mispricing.get("coverage", 0)},
                "confidence": row.data_confidence, "reason_codes": reason_codes,
                "missing_factors": {"quality": [name for name, value in quality.items()
                    if isinstance(value, dict) and float(value.get("coverage", 0)) < 1],
                    "mispricing": mispricing.get("missing_factors", [])},
                "source_timestamp": mispricing.get("source_timestamp"),
                "money_flow_status": "UNAVAILABLE",
                "source_universes": mispricing.get("source_universes", []),
                "source_count": mispricing.get("source_count", 0)}
