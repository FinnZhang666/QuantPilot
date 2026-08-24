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
        universe = self.repository.active_universe(at, [s.upper() for s in symbols] if symbols else None)
        if limit: universe = universe[:limit]
        result = {"evaluation_time": at, "scanned": len(universe), "created": 0, "skipped": 0, "failed": 0, "items": []}
        for item in universe:
            try:
                payload = self.evaluate(item, at)
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
        memberships = self.repository.memberships(item.id, at)
        weights = {m.fund_symbol: float(m.weight) if m.weight is not None else None for m in memberships}
        prices = self.repository.bars(item.symbol, at)
        average_dollar_volume = None
        if prices:
            sample = prices[-20:]
            average_dollar_volume = sum(float(x.close) * x.volume for x in sample) / len(sample)
        fundamental = self.fundamentals.latest(item.symbol, at)
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
        ranks = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
        if ranks.get(financial_risk, 0) > ranks.get(event.fundamental_risk, 0):
            event = EventAssessment(event.event_risk, financial_risk, event.confidence, event.source)
        m_score, m_components = mispricing_score(prices, benchmark_prices, industry_prices, event, self.config)
        sources = ["UNIVERSE", "MARKET_BARS"]
        if fundamental: sources.append("FUNDAMENTAL:" + fundamental.source)
        sources.append(event.source)
        confidence = "HIGH" if coverage >= .8 and len(prices) >= 252 and event.confidence == "HIGH" else ("MEDIUM" if coverage >= .65 and len(prices) >= 60 else "LOW")
        m_components["benchmark"] = benchmark
        m_components["industry_benchmark"] = industry_symbol
        return {"quality": q_score, "quality_components": q_components, "coverage": coverage,
                "mispricing": m_score, "mispricing_components": m_components,
                "event": event, "sources": sources, "confidence": confidence}

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
        }

    @staticmethod
    def serialize(row):
        return {"id": row.id, "symbol": row.symbol, "evaluation_time": row.evaluation_time,
                "quality_score": row.quality_score, "mispricing_score": row.mispricing_score,
                "combined_score": row.combined_score, "fundamental_risk": row.fundamental_risk,
                "event_risk": row.event_risk, "candidate_status": row.candidate_status,
                "score_components": row.score_components_json, "data_sources": row.data_sources_json,
                "data_confidence": row.data_confidence, "model_version": row.model_version,
                "last_update": row.created_at}
