import re
from pathlib import Path

import yaml
from sqlalchemy import func, select

from app.core.errors import AppError, ControlledServiceError, ErrorCode
from app.database.models import SymbolRegistryRecord, UniverseInstrument


VALID_TYPES = {"STOCK", "ETF", "LEVERAGED_ETF", "INDEX", "CRYPTO",
               "COMMODITY_PROXY", "BOND_ETF", "VOLATILITY_INDEX"}


class SymbolRegistryService:
    def __init__(self, db, config_path="config/symbol_registry_v1.yaml"):
        self.db = db
        self.config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))

    @staticmethod
    def normalize(value):
        symbol = str(value or "").strip().upper()
        symbol = symbol.removeprefix("$").removeprefix("US.").strip()
        if not symbol or len(symbol) > 16 or not re.fullmatch(r"[A-Z0-9.-]+", symbol):
            raise ControlledServiceError(AppError(
                ErrorCode.SYMBOL_NOT_FOUND, "symbol_registry", "Invalid symbol"))
        return symbol

    def resolve(self, value, allow_unknown=True):
        raw = str(value or "").strip()
        try:
            normalized = self.normalize(raw)
        except ControlledServiceError:
            normalized = None
        row = self.db.scalar(select(SymbolRegistryRecord).where(
            SymbolRegistryRecord.symbol == normalized)) if normalized else None
        if row is None and raw:
            matches = list(self.db.scalars(select(SymbolRegistryRecord).where(
                func.lower(SymbolRegistryRecord.display_name) == raw.lower()).limit(3)))
            if len(matches) == 1:
                row = matches[0]
            elif len(matches) > 1:
                return {"status": "AMBIGUOUS", "candidates": [self.serialize(x) for x in matches]}
        if row:
            return {"status": "RESOLVED", "item": self.serialize(row)}
        if allow_unknown and normalized:
            return {"status": "UNREGISTERED", "item": {"symbol": normalized,
                "asset_type": "STOCK", "market": "US", "status": "UNKNOWN",
                "manual_analysis_supported": True, "quote_supported": False,
                "money_flow_supported": False, "paper_trade_supported": False}}
        raise ControlledServiceError(AppError(
            ErrorCode.SYMBOL_NOT_FOUND, "symbol_registry", "Symbol was not found",
            symbol=normalized))

    def sync(self):
        definitions = dict(self.config.get("symbols", {}))
        universe = list(self.db.scalars(select(UniverseInstrument)))
        for item in universe:
            values = definitions.setdefault(item.symbol, {})
            values.setdefault("display_name", item.company_name)
            values.setdefault("asset_type", "STOCK")
            values.setdefault("sector", item.sector)
            values.setdefault("industry", item.industry)
            values["qmr_auto_universe"] = item.status == "ACTIVE"
        created = updated = 0
        defaults = self.config["defaults"]
        for symbol, override in definitions.items():
            values = {**defaults, **(override or {})}
            asset_type = values.get("asset_type", "STOCK")
            if asset_type not in VALID_TYPES:
                raise ValueError("Unsupported asset_type in registry config")
            row = self.db.scalar(select(SymbolRegistryRecord).where(
                SymbolRegistryRecord.market == values.get("market", "US"),
                SymbolRegistryRecord.symbol == symbol))
            if row is None:
                row = SymbolRegistryRecord(symbol=symbol)
                self.db.add(row); created += 1
            else:
                updated += 1
            for field in ("display_name", "asset_type", "market", "exchange", "currency",
                          "is_etf", "is_leveraged", "leverage_ratio", "underlying_symbol",
                          "underlying_type", "sector", "industry", "primary_benchmark",
                          "secondary_benchmark", "qmr_auto_universe",
                          "manual_analysis_supported", "quote_supported",
                          "money_flow_supported", "paper_trade_supported", "status"):
                if field in values:
                    setattr(row, field, values[field])
        self.db.commit()
        return {"created": created, "updated": updated, "total": len(definitions)}

    def search(self, query, limit=10):
        value = str(query or "").strip().lower()
        rows = list(self.db.scalars(select(SymbolRegistryRecord).where(
            (func.lower(SymbolRegistryRecord.symbol).contains(value)) |
            (func.lower(SymbolRegistryRecord.display_name).contains(value))
        ).order_by(SymbolRegistryRecord.symbol).limit(limit)))
        return [self.serialize(row) for row in rows]

    @staticmethod
    def serialize(row):
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}
