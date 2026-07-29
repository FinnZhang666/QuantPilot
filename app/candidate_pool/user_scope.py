import re
from typing import List

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database.models import TelegramUserSymbol


class TelegramUserScopeService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def normalize(symbol: str) -> str:
        value = symbol.strip().upper().replace("US.", "")
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", value):
            raise ValueError("Ticker格式无效。")
        return value

    def add(self, user_id: str, symbol: str, notes=None):
        value = self.normalize(symbol)
        statement = sqlite_insert(TelegramUserSymbol).values(
            telegram_user_id=str(user_id), symbol=value, market="US",
            enabled=True, source="TELEGRAM", notes=notes,
        ).on_conflict_do_update(
            index_elements=["telegram_user_id", "symbol", "market"],
            set_={"enabled": True, "notes": notes},
        )
        self.db.execute(statement)
        self.db.commit()
        return value

    def remove(self, user_id: str, symbol: str) -> bool:
        value = self.normalize(symbol)
        row = self.db.scalar(select(TelegramUserSymbol).where(
            TelegramUserSymbol.telegram_user_id == str(user_id),
            TelegramUserSymbol.symbol == value,
        ))
        if row is None:
            return False
        row.enabled = False
        self.db.commit()
        return True

    def symbols(self, user_id: str) -> List[str]:
        return list(self.db.scalars(select(TelegramUserSymbol.symbol).where(
            TelegramUserSymbol.telegram_user_id == str(user_id),
            TelegramUserSymbol.enabled.is_(True),
        ).order_by(TelegramUserSymbol.symbol)))
