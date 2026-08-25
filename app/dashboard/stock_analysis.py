"""Read-only composition for the dashboard's on-demand stock analysis.

This module deliberately does not score, persist, or fetch market data.  It
only presents the latest outputs already produced by the existing engines.
"""

from datetime import datetime, timezone

from app.buy_score.service import BuyScoreService
from app.market_snapshot.models import snapshot_dict
from app.market_snapshot.service import MarketSnapshotService, SnapshotNotFound
from app.qmr.service import QmrService
from app.qmr_exit.service import QmrExitService
from app.recovery.service import RecoveryService
from app.universe.service import UniverseService


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
        return {
            "schema_version": "dashboard-stock-analysis-v1",
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
