"""Read-only composition for the dashboard's on-demand stock analysis.

This module deliberately does not score, persist, or fetch market data.  It
only presents the latest outputs already produced by the existing engines.
"""

from datetime import datetime, timezone

from app.buy_score.service import BuyScoreService
from app.market_snapshot.models import snapshot_dict
from app.market_snapshot.service import MarketSnapshotService, SnapshotNotFound
from app.market_context.service import MarketContextService
from app.qmr.providers import DatabaseFundamentalsProvider
from app.qmr.service import QmrService
from app.qmr_exit.service import QmrExitService
from app.recovery.service import RecoveryService
from app.universe.service import UniverseService
from app.symbol_registry.service import SymbolRegistryService
from app.trade_lifecycle.repository import TradePlanRepository
from app.dashboard.analysis_presentation import (
    freshness, localized_view, risk_reward, score_state, valuation_view,
)


ANALYSIS_UNDERLYINGS = {
    "SOXL": {"symbol": "SOXX", "description": "Semiconductor basket"},
    "SOXS": {"symbol": "SOXX", "description": "Semiconductor basket"},
}


class StockAnalysisService:
    """Compose persisted engine output into one conclusion-first read model."""

    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    def get(self, symbol):
        symbol = str(symbol or "").strip().upper().removeprefix("US.")
        if not symbol or len(symbol) > 16 or not all(char.isalnum() or char in ".-" for char in symbol):
            raise ValueError("股票代码格式无效。")

        universe = UniverseService(self.db, self.settings).get(symbol)
        qmr_service = QmrService(self.db, self.settings)
        recovery_service = RecoveryService(self.db, self.settings)
        buy_service = BuyScoreService(self.db, self.settings)
        exit_service = QmrExitService(self.db, self.settings)

        qmr = self._latest(qmr_service.detail(symbol))
        recovery = self._latest(recovery_service.detail(symbol))
        buy = self._latest(buy_service.detail(symbol))
        exit_rows = exit_service.repository.list(symbol=symbol, limit=1)
        exit_value = exit_service.serialize(exit_rows[0]) if exit_rows else None
        flow_rows = exit_service.repository.money_flow(symbol, datetime.now(timezone.utc), limit=1)
        money_flow = self._money_flow(flow_rows[-1]) if flow_rows else None

        try:
            snapshot = snapshot_dict(MarketSnapshotService(self.db).get_snapshot(symbol))
        except SnapshotNotFound:
            snapshot = None

        underlying = self._underlying(symbol, qmr_service, buy_service)
        instrument = self._instrument(symbol, underlying)
        fundamental = DatabaseFundamentalsProvider(self.db).get_latest(underlying["symbol"])
        market_context = MarketContextService(self.db, self.settings).current_for_symbol(underlying["symbol"])
        trade_plan = self._trade_plan(symbol)
        status = self._status(exit_value, buy, recovery, qmr, snapshot)
        price = self._first(
            exit_value, "current_price", buy, "entry_reference_price",
            recovery, "price", snapshot, "latest_price",
        )
        reasons = self._reasons(exit_value, buy, recovery, qmr)
        levels = {
            "support": self._first(exit_value, "dynamic_support", recovery, "session_low"),
            "observation": self._zone(buy),
            "confirmation": self._first(buy, "first_confirmed_entry_price"),
            "invalidation": self._first(exit_value, "dynamic_support", recovery, "session_low"),
        }
        has_data = any((snapshot, qmr, recovery, buy, exit_value, money_flow))
        payload = {
            "schema_version": "dashboard-stock-analysis-v2",
            "symbol": symbol,
            "market": (universe or {}).get("market", "US"),
            "company_name": (universe or {}).get("company_name"),
            "analysis_scope": "QMR_UNIVERSE" if universe and universe.get("status") == "ACTIVE" else "MANUAL_ANALYSIS",
            "in_qmr_universe": bool(universe and universe.get("status") == "ACTIVE"),
            "data_status": "AVAILABLE" if has_data else "UNAVAILABLE",
            "current_price": price,
            "status": status,
            "advice": self._advice(status),
            "buy_score": None if buy is None else buy.get("final_buy_score"),
            "exit_risk": None if exit_value is None else exit_value.get("exit_risk_score"),
            "qmr_summary": self._qmr_summary(qmr),
            "money_flow": money_flow,
            "core_reasons": reasons[:8],
            "key_levels": levels,
            "underlying": underlying,
            "instrument": instrument,
            "analysis_model": "LEVERAGED_ETF_ANALYSIS" if instrument.get("asset_type") == "LEVERAGED_ETF" else "QMR_ANALYSIS",
            "quality_score": None if qmr is None else qmr.get("quality_score"),
            "quality_state": score_state(None if qmr is None else qmr.get("quality_score")),
            "quality": self._quality(fundamental),
            "valuation": valuation_view(qmr),
            "market_context": market_context,
            "trade_plan": trade_plan,
            "risk_reward": risk_reward(
                (trade_plan or {}).get("reference_price"),
                (trade_plan or {}).get("stop_loss_price"),
                (trade_plan or {}).get("target_prices"),
            ),
            "latest_update": self._first(
                exit_value, "evaluation_time", buy, "timestamp", recovery, "timestamp",
                qmr, "evaluation_time", snapshot, "updated_at",
            ),
            "sections": {
                "universe": universe, "snapshot": snapshot, "qmr": qmr,
                "recovery": recovery, "buy_score": buy, "exit": exit_value,
                "money_flow": money_flow,
                "technical": ((buy or {}).get("score_components") or {}).get("feature_risk"),
                "relative_strength": ((exit_value or {}).get("components_json") or {}).get("relative_strength"),
                "sector_rotation": ((exit_value or {}).get("components_json") or {}).get("sector_rotation"),
                "trading_session": (recovery or {}).get("trading_session"),
            },
            "missing_sections": [name for name, value in {
                "quality_mispricing": qmr, "recovery": recovery, "buy_score": buy,
                "money_flow": money_flow, "exit": exit_value,
            }.items() if value is None],
        }
        payload["freshness"] = freshness(payload["latest_update"])
        payload["decision_factors"] = self._decision_factors(payload)
        payload["model_versions"] = self._model_versions(qmr, buy, exit_value, market_context)
        payload["presentation"] = {
            language: localized_view(payload, language) for language in ("zh-CN", "en-US")
        }
        return payload

    @staticmethod
    def _latest(rows):
        return rows[0] if rows else None

    @staticmethod
    def _first(*values):
        for index in range(0, len(values), 2):
            source, key = values[index:index + 2]
            if source is not None and source.get(key) is not None:
                return source[key]
        return None

    @staticmethod
    def _zone(buy):
        if not buy or buy.get("entry_zone_low") is None or buy.get("entry_zone_high") is None:
            return None
        return {"low": buy["entry_zone_low"], "high": buy["entry_zone_high"]}

    @staticmethod
    def _status(exit_value, buy, recovery, qmr, snapshot):
        if exit_value and exit_value.get("state") in {"PROTECT", "REDUCE", "EXIT"}:
            return exit_value["state"]
        if buy and buy.get("buy_status") not in {None, "WAIT", "REJECT"}:
            return buy["buy_status"]
        if recovery and recovery.get("entry_status") not in {None, "WAIT", "OBSERVE"}:
            return recovery["entry_status"]
        if qmr and qmr.get("candidate_status") == "WATCH":
            return "WATCH"
        if snapshot and snapshot.get("candidate_signal") not in {None, "NONE"}:
            return snapshot["candidate_signal"]
        return "NO_DATA" if not any((exit_value, buy, recovery, qmr, snapshot)) else "WATCH"

    @staticmethod
    def _advice(status):
        return {
            "WATCH": "WAIT_FOR_CONFIRMATION", "PROBE": "SMALL_PROBE",
            "EARLY_ENTRY": "SMALL_POSITION", "CONFIRMED_ENTRY": "CONSIDER_ENTRY",
            "STRONG_ENTRY": "CONSIDER_ENTRY", "HOLD": "HOLD",
            "PROTECT": "PROTECT_PROFIT", "REDUCE": "REDUCE_POSITION",
            "EXIT": "EXIT_POSITION", "NO_DATA": "DATA_INSUFFICIENT",
        }.get(status, "WAIT_FOR_CONFIRMATION")

    @staticmethod
    def _qmr_summary(qmr):
        if not qmr:
            return "DATA_INSUFFICIENT"
        if qmr.get("candidate_status") == "WATCH":
            return "QUALITY_MISPRICING_CANDIDATE"
        return qmr.get("candidate_status") or "NO_SIGNAL"

    @staticmethod
    def _reasons(exit_value, buy, recovery, qmr):
        reasons = list((exit_value or {}).get("reasons_json") or [])
        reasons.extend((qmr or {}).get("reason_codes") or [])
        failure = (recovery or {}).get("failure_reason")
        if failure:
            reasons.append(failure)
        if buy and buy.get("chase_risk_level") not in {None, "LOW"}:
            reasons.append("chase_risk_%s" % buy["chase_risk_level"].lower())
        return list(dict.fromkeys(str(reason) for reason in reasons if reason))

    @staticmethod
    def _money_flow(row):
        return {
            "regime": row.money_flow_regime, "score": row.money_flow_score,
            "accumulation_score": row.accumulation_score,
            "distribution_score": row.distribution_score,
            "absorption_score": row.absorption_score,
            "data_available": row.data_available, "data_quality": row.data_quality,
            "timestamp": row.timestamp, "trading_session": row.trading_session,
        }

    @staticmethod
    def _underlying(symbol, qmr_service, buy_service):
        configured = ANALYSIS_UNDERLYINGS.get(symbol)
        if configured:
            return {**configured, "source": "ANALYSIS_MAPPING"}
        underlying = qmr_service.repository.fundamental_symbol(symbol)
        if underlying != symbol:
            return {"symbol": underlying, "description": "Configured underlying asset", "source": "INSTRUMENT_MAPPING"}
        configured_mapping = next((item for item in buy_service.config.get("instrument_mappings", [])
                                   if item.get("leveraged_symbol") == symbol and item.get("active")), None)
        if configured_mapping:
            return {"symbol": configured_mapping["underlying_symbol"],
                    "description": "Configured underlying asset", "source": "CONFIG_MAPPING"}
        mappings = buy_service.mappings(symbol)
        return {"symbol": symbol, "description": "Direct instrument", "source": "DIRECT", "vehicles": mappings}

    def _instrument(self, symbol, underlying):
        try:
            item = SymbolRegistryService(self.db, self.settings.symbol_registry_config_file).resolve(
                symbol, allow_unknown=True)["item"]
        except Exception:
            item = {"symbol": symbol, "asset_type": "STOCK", "market": "US"}
        item = dict(item)
        item.setdefault("underlying_symbol", underlying["symbol"])
        if underlying["symbol"] != symbol:
            item["underlying_symbol"] = underlying["symbol"]
            item["asset_type"] = "LEVERAGED_ETF"
        return item

    def _trade_plan(self, symbol):
        rows = TradePlanRepository(self.db).list(symbol=symbol, limit=1)
        if not rows:
            return None
        row = rows[0]
        return {
            "plan_id": row.plan_id, "lifecycle_stage": row.lifecycle_stage,
            "reference_price": None if row.reference_price is None else str(row.reference_price),
            "stop_loss_price": None if row.stop_loss_price is None else str(row.stop_loss_price),
            "target_prices": list(row.target_prices_json or []),
            "strategy_version": row.strategy_version, "updated_at": row.updated_at,
        }

    @staticmethod
    def _quality(fundamental):
        if fundamental is None:
            return {"available": False, "source": None, "as_of": None, "groups": {}}
        def values(*names):
            return {name: getattr(fundamental, name, None) for name in names}
        return {"available": True, "source": fundamental.source, "as_of": fundamental.available_at,
                "freshness": fundamental.freshness, "confidence": fundamental.quality,
                "groups": {
                    "growth": values("revenue_yoy", "eps_yoy", "forward_earnings_growth", "quarterly_trend"),
                    "profitability": values("net_income_ttm", "operating_margin"),
                    "capital_efficiency": values("roe", "roic"),
                    "cash_flow": values("operating_cash_flow", "free_cash_flow"),
                    "balance_sheet": values("cash", "debt", "debt_to_equity", "interest_coverage"),
                }}

    @staticmethod
    def _decision_factors(payload):
        positive, caution = [], []
        if (payload.get("quality_score") or 0) >= 65: positive.append("quality_supported")
        elif payload.get("quality_score") is not None and payload["quality_score"] < 45: caution.append("quality_weak")
        valuation = payload.get("valuation") or {}
        if valuation.get("state") == "LOW_VALUATION": positive.append("valuation_below_peers")
        if valuation.get("value_trap_state") == "VALUE_TRAP_PRESENT": caution.append("value_trap_risk")
        global_score = ((payload.get("market_context") or {}).get("global") or {}).get("global_score")
        sector_score = ((payload.get("market_context") or {}).get("sector") or {}).get("sector_score")
        if global_score is not None: (positive if global_score >= 65 else caution if global_score < 45 else positive).append("global_supportive" if global_score >= 45 else "global_weak")
        if sector_score is not None: (positive if sector_score >= 65 else caution if sector_score < 45 else positive).append("sector_supportive" if sector_score >= 45 else "sector_weak")
        if payload.get("status") in {"EARLY_ENTRY", "CONFIRMED_ENTRY", "STRONG_ENTRY", "HOLD"}: positive.append("stock_setup_confirmed")
        if payload.get("status") in {"PROTECT", "REDUCE", "EXIT"}: caution.append("exit_risk_elevated")
        return {"positive": positive, "caution": caution}

    @staticmethod
    def _model_versions(qmr, buy, exit_value, market_context):
        return {"qmr": (qmr or {}).get("model_version"), "buy_score": (buy or {}).get("model_version"),
                "exit": (exit_value or {}).get("model_version"),
                "market_context": ((market_context or {}).get("global") or {}).get("model_version")}
