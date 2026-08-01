from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Instrument

DEFAULT_INSTRUMENTS = [
    ("US.SOXL", "SOXL"),
    ("US.SOXS", "SOXS"),
    ("US.MULL", "MULL"),
    ("US.TQQQ", "TQQQ"),
    ("US.NVDL", "NVDL"),
    ("US.RAM", "RAM"),
    ("US.QQQ", "QQQ"),
    ("US.SPY", "SPY"),
    ("US.SMH", "SMH"),
    ("US.SOXX", "SOXX"),
    ("US.NVDA", "NVDA"),
    ("US.AMD", "AMD"),
    ("US.MU", "MU"),
    ("US.PLTR", "PLTR"),
    ("US.ML", "ML"),
    ("US.VIX", "VIX"),
]


class InstrumentService:
    def __init__(self, db: Session):
        self.db = db

    def initialize_defaults(self) -> List[Instrument]:
        rows: List[Instrument] = []
        for symbol, alias in DEFAULT_INSTRUMENTS:
            row = self.db.scalar(select(Instrument).where(Instrument.symbol == symbol))
            if row is None:
                market, code = symbol.split(".", 1)
                row = Instrument(
                    symbol=symbol,
                    market=market,
                    code=code,
                    display_name=alias,
                    alias=alias,
                    is_supported=False,
                    support_status="PENDING",
                    support_message="待确认",
                )
                self.db.add(row)
            rows.append(row)
        self.db.commit()
        return rows

    def resolve(self, value: str) -> Optional[Instrument]:
        normalized = value.upper()
        return self.db.scalar(
            select(Instrument).where(
                (Instrument.symbol == normalized) | (Instrument.alias == normalized)
            )
        )

    def set_validation(
        self,
        instrument: Instrument,
        supported: bool,
        status: str,
        message: str,
        actual_symbol: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> None:
        if actual_symbol and actual_symbol != instrument.symbol:
            market, code = actual_symbol.split(".", 1)
            instrument.symbol = actual_symbol
            instrument.market = market
            instrument.code = code
        instrument.is_supported = supported
        instrument.support_status = status
        instrument.support_message = message
        if metadata:
            instrument.display_name = str(metadata.get("name", instrument.display_name))
            instrument.security_type = str(metadata.get("stock_type", instrument.security_type))
            instrument.lot_size = int(metadata.get("lot_size", instrument.lot_size) or 1)
        self.db.commit()
