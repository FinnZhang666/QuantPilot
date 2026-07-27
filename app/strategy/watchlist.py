from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database.models import (
    Instrument, StrategyParameterSet, WatchlistItem, WatchlistTimeframe,
)
from app.strategy.classifier import TickerClassifier
from app.strategy.constants import (
    CLASSIFICATION_SOURCES, DEFAULT_WATCHLIST, ROLES, ROLE_TIMEFRAMES,
    STRATEGY_NAME, STRATEGY_VERSION, SYMBOL_PATTERN, TEMPLATES,
)
from app.strategy.templates import (
    parameters_for_template, parameters_hash, validate_parameter_update,
)


class WatchlistService:
    def __init__(self, db: Session, classifier: Optional[TickerClassifier] = None):
        self.db = db
        self.classifier = classifier or TickerClassifier()

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        value = symbol.strip().upper()
        if value.startswith("US."):
            value = value[3:]
        if not SYMBOL_PATTERN.fullmatch(value):
            raise ValueError("Ticker格式无效。")
        return value

    def add_symbol(self, symbol: str, market: str = "US", notes: Optional[str] = None) -> Dict[str, object]:
        value = self.normalize_symbol(symbol)
        market = market.strip().upper()
        existing = self.get_symbol(value, market)
        if existing:
            result = "already_exists"
            if not existing.enabled:
                existing.enabled = True
                result = "reactivated"
            if notes is not None:
                existing.notes = notes
            self.db.commit()
            return self.serialize(existing, result)
        instrument = self.db.scalar(select(Instrument).where(
            Instrument.symbol == market + "." + value,
        ))
        classified = self.classifier.classify(value, instrument)
        item = WatchlistItem(
            symbol=value, market=market, notes=notes, classification_source="AUTO",
            enabled=True, **classified,
        )
        self.db.add(item)
        self.db.flush()
        self._ensure_timeframes(item)
        self._ensure_parameters(item)
        self.db.commit()
        return self.serialize(item, "created")

    def initialize_defaults(self) -> Dict[str, int]:
        stats = {"added": 0, "existing": 0, "reactivated": 0, "failed": 0, "pending_validation": 0}
        for symbol in DEFAULT_WATCHLIST:
            try:
                result = self.add_symbol(symbol)
                key = {"created": "added", "already_exists": "existing", "reactivated": "reactivated"}[result["result"]]
                stats[key] += 1
                if result["validation_status"] == "PENDING_VALIDATION":
                    stats["pending_validation"] += 1
            except Exception:
                self.db.rollback()
                stats["failed"] += 1
        return stats

    def get_symbol(self, symbol: str, market: str = "US") -> Optional[WatchlistItem]:
        value = self.normalize_symbol(symbol)
        return self.db.scalar(select(WatchlistItem).where(
            WatchlistItem.symbol == value, WatchlistItem.market == market.upper(),
        ))

    def list_symbols(
        self, enabled_only: bool = False, role: Optional[str] = None,
        validation_status: Optional[str] = None,
    ) -> List[WatchlistItem]:
        query = select(WatchlistItem)
        if enabled_only:
            query = query.where(WatchlistItem.enabled.is_(True))
        if role:
            query = query.where(WatchlistItem.role == role)
        if validation_status:
            query = query.where(WatchlistItem.validation_status == validation_status)
        return list(self.db.scalars(query.order_by(WatchlistItem.symbol)))

    def update_symbol(self, symbol: str, **changes) -> WatchlistItem:
        item = self.get_symbol(symbol)
        if not item:
            raise KeyError("Ticker不存在于观察池中。")
        allowed = {"role", "benchmark_symbol", "strategy_template", "sector", "notes", "enabled"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError("不允许修改字段：" + "、".join(sorted(unknown)))
        if "role" in changes and changes["role"] not in ROLES:
            raise ValueError("Role无效。")
        if "strategy_template" in changes and changes["strategy_template"] not in TEMPLATES:
            raise ValueError("Template无效。")
        if changes.get("benchmark_symbol"):
            changes["benchmark_symbol"] = self.normalize_symbol(changes["benchmark_symbol"])
        for key, value in changes.items():
            setattr(item, key, value)
        item.classification_source = "MANUAL"
        self.db.commit()
        return item

    def disable_symbol(self, symbol: str) -> WatchlistItem:
        return self.update_symbol(symbol, enabled=False)

    def enable_symbol(self, symbol: str) -> WatchlistItem:
        return self.update_symbol(symbol, enabled=True)

    def remove_symbol(self, symbol: str) -> WatchlistItem:
        return self.disable_symbol(symbol)

    def reclassify_symbol(self, symbol: str, confirm: bool = False) -> Dict[str, object]:
        item = self.get_symbol(symbol)
        if not item:
            raise KeyError("Ticker不存在于观察池中。")
        instrument = self.db.scalar(select(Instrument).where(
            Instrument.symbol == item.market + "." + item.symbol,
        ))
        classified = self.classifier.classify(item.symbol, instrument)
        if not confirm:
            return {"preview": True, **classified}
        for key, value in classified.items():
            setattr(item, key, value)
        item.classification_source = "AUTO"
        self._ensure_timeframes(item)
        self._ensure_parameters(item, replace_template=True)
        self.db.commit()
        return self.serialize(item, "reclassified")

    def update_parameters(self, symbol: str, updates: Dict[str, object]) -> Dict[str, object]:
        item = self.get_symbol(symbol)
        if not item:
            raise KeyError("Ticker不存在于观察池中。")
        row = self.db.scalar(select(StrategyParameterSet).where(
            StrategyParameterSet.watchlist_item_id == item.id,
            StrategyParameterSet.strategy_name == STRATEGY_NAME,
            StrategyParameterSet.strategy_version == STRATEGY_VERSION,
            StrategyParameterSet.enabled.is_(True),
        ))
        before = dict(row.parameters_json)
        after = validate_parameter_update(before, updates)
        row.parameters_json = after
        row.parameters_hash = parameters_hash(after)
        self.db.commit()
        return {"before": before, "after": after, "parameters_hash": row.parameters_hash}

    def _ensure_timeframes(self, item: WatchlistItem) -> None:
        for timeframe in ROLE_TIMEFRAMES[item.role]:
            statement = sqlite_insert(WatchlistTimeframe).values(
                watchlist_item_id=item.id, timeframe=timeframe, enabled=True,
            ).on_conflict_do_update(
                index_elements=["watchlist_item_id", "timeframe"],
                set_={"enabled": True},
            )
            self.db.execute(statement)

    def _ensure_parameters(self, item: WatchlistItem, replace_template: bool = False) -> None:
        values = parameters_for_template(item.strategy_template)
        statement = sqlite_insert(StrategyParameterSet).values(
            watchlist_item_id=item.id, strategy_name=STRATEGY_NAME,
            strategy_version=STRATEGY_VERSION, parameters_json=values,
            parameters_hash=parameters_hash(values), enabled=True,
        )
        if replace_template:
            statement = statement.on_conflict_do_update(
                index_elements=["watchlist_item_id", "strategy_name", "strategy_version"],
                set_={"parameters_json": values, "parameters_hash": parameters_hash(values), "enabled": True},
            )
        else:
            statement = statement.on_conflict_do_nothing(
                index_elements=["watchlist_item_id", "strategy_name", "strategy_version"],
            )
        self.db.execute(statement)

    @staticmethod
    def serialize(item: WatchlistItem, result: Optional[str] = None) -> Dict[str, object]:
        output = {
            "symbol": item.symbol, "market": item.market, "display_name": item.display_name,
            "asset_type": item.asset_type, "sector": item.sector, "role": item.role,
            "benchmark_symbol": item.benchmark_symbol,
            "strategy_template": item.strategy_template, "enabled": item.enabled,
            "validation_status": item.validation_status,
            "validation_message": item.validation_message,
            "classification_source": item.classification_source, "notes": item.notes,
        }
        if result:
            output["result"] = result
        return output
