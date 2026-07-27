from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from app.core.enums import BarInterval, FeatureJobType
from app.features.pipeline import FeatureCalculationService
from app.features.registry import FeatureRegistry
from app.strategy.constants import FEATURE_ALIASES, OPTIONAL_ALIASES, REQUIRED_ALIASES
from app.strategy.repository import StrategyRepository


class FeatureDependencyResolver:
    def __init__(
        self, repository: StrategyRepository,
        feature_service: Optional[FeatureCalculationService] = None,
        registry: Optional[FeatureRegistry] = None,
    ):
        self.repository = repository
        self.feature_service = feature_service
        self.registry = registry or FeatureRegistry.defaults()
        self._verify_registry_names()

    def dependency_names(self, benchmark_symbol: Optional[str]) -> Tuple[List[str], List[str], Optional[str]]:
        required = [FEATURE_ALIASES[name] for name in REQUIRED_ALIASES]
        optional = [FEATURE_ALIASES[name] for name in OPTIONAL_ALIASES]
        relative = None
        if benchmark_symbol == "QQQ":
            relative = "relative_return_qqq_20"
        elif benchmark_symbol == "SOXX":
            relative = "relative_return_soxx_20"
        if relative:
            optional.append(relative)
        return required, optional, relative

    def resolve(
        self, symbol: str, timeframe: str, timestamp: datetime,
        benchmark_symbol: Optional[str], auto_calculate: bool = True,
        realtime: bool = False,
    ) -> Dict[str, object]:
        required, optional, relative = self.dependency_names(benchmark_symbol)
        names = required + optional
        source = "MOOMOO_REALTIME" if realtime else "MOOMOO"
        rows = self.repository.feature_values(symbol, timeframe, timestamp, names, source)
        missing_names = [name for name in names if name not in rows]
        calculated = []
        calculation_error = None
        if missing_names and auto_calculate and self.feature_service:
            try:
                job = self.feature_service.calculate_symbol(
                    "US." + symbol, BarInterval(timeframe), missing_names,
                    timestamp, timestamp, FeatureJobType.REPAIR,
                    realtime=realtime,
                )
                if job.status in ("SUCCESS", "PARTIAL"):
                    calculated = missing_names
                    rows = self.repository.feature_values(symbol, timeframe, timestamp, names, source)
                else:
                    calculation_error = job.error_message or job.status
            except Exception as exc:
                calculation_error = type(exc).__name__ + "：" + str(exc)
        values: Dict[str, Optional[Decimal]] = {}
        statuses: Dict[str, str] = {}
        refs: Dict[str, dict] = {}
        for name in names:
            row = rows.get(name)
            statuses[name] = row.quality_status if row else "MISSING"
            values[name] = self._row_value(row)
            if row:
                refs[name] = {
                    "version": row.feature_version,
                    "parameters_hash": row.parameters_hash,
                    "timestamp_utc": row.timestamp_utc.isoformat(),
                    "quality_status": row.quality_status,
                }
        previous = self.repository.previous_feature_value(
            symbol, timeframe, timestamp, FEATURE_ALIASES["close_vs_ema20"], source,
        )
        values["_previous_close_vs_ema20"] = self._row_value(previous)
        statuses["_previous_close_vs_ema20"] = previous.quality_status if previous else "MISSING"
        core_missing = [name for name in required if statuses[name] != "VALID" or values[name] is None]
        optional_missing = [name for name in optional if statuses[name] != "VALID" or values[name] is None]
        return {
            "values": values, "statuses": statuses, "refs": refs,
            "required": required, "optional": optional, "relative_name": relative,
            "core_missing": core_missing, "optional_missing": optional_missing,
            "calculated": calculated, "calculation_error": calculation_error,
        }

    def _verify_registry_names(self) -> None:
        names = {item.feature_name for item in self.registry.list()}
        expected = set(FEATURE_ALIASES.values()) | {
            "relative_return_qqq_20", "relative_return_soxx_20",
        }
        missing = expected - names
        if missing:
            raise RuntimeError("Feature Registry缺少策略依赖：" + "、".join(sorted(missing)))

    @staticmethod
    def _row_value(row) -> Optional[Decimal]:
        if not row or row.quality_status != "VALID":
            return None
        if row.value_decimal is not None:
            return Decimal(row.value_decimal)
        if row.value_integer is not None:
            return Decimal(row.value_integer)
        if row.value_boolean is not None:
            return Decimal(1 if row.value_boolean else 0)
        return None
