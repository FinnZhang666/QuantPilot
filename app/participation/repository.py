from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database.models import TradePlan, UserPosition


class UserPositionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_plan(self, plan_id: str) -> Optional[TradePlan]:
        return self.db.scalar(select(TradePlan).where(TradePlan.plan_id == plan_id))

    def get_plan_by_id(self, plan_id: int) -> Optional[TradePlan]:
        return self.db.get(TradePlan, plan_id)

    def create(self, row: UserPosition) -> UserPosition:
        self.db.add(row)
        self.db.flush()
        return row

    def update(self, row: UserPosition) -> UserPosition:
        self.db.add(row)
        return row

    def get(self, position_id: int) -> Optional[UserPosition]:
        return self.db.get(UserPosition, position_id)

    def exists_open(self, user_id: str, trade_plan_id: int) -> bool:
        return self.db.scalar(select(UserPosition.id).where(
            UserPosition.user_id == user_id,
            UserPosition.trade_plan_id == trade_plan_id,
            UserPosition.status == "OPEN",
        ).limit(1)) is not None

    def list(
        self, user_id: Optional[str] = None, symbol: Optional[str] = None,
        status: Optional[str] = None, limit: int = 100, offset: int = 0,
    ) -> List[UserPosition]:
        query = self._filtered(user_id, symbol, status)
        return list(self.db.scalars(query.order_by(
            desc(UserPosition.opened_at), desc(UserPosition.id),
        ).offset(offset).limit(limit)))

    def count(
        self, user_id: Optional[str] = None, symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        query = self._filtered(user_id, symbol, status).subquery()
        return int(self.db.scalar(select(func.count()).select_from(query)) or 0)

    def statistics(self, user_id: Optional[str] = None):
        filters = [UserPosition.user_id == user_id] if user_id else []
        rows = list(self.db.scalars(select(UserPosition).where(*filters)))
        closed = [row for row in rows if row.status == "CLOSED"]
        wins = sum(1 for row in closed if self._won(row))
        losses = sum(1 for row in closed if self._lost(row))
        return {
            "open_positions": sum(row.status == "OPEN" for row in rows),
            "closed_positions": len(closed), "total_trades": len(rows),
            "win_count": wins, "loss_count": losses,
        }

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    @staticmethod
    def _filtered(user_id=None, symbol=None, status=None):
        query = select(UserPosition)
        if user_id:
            query = query.where(UserPosition.user_id == user_id)
        if symbol:
            query = query.where(UserPosition.symbol == symbol.upper().replace("US.", ""))
        if status:
            query = query.where(UserPosition.status == status.upper())
        return query

    @staticmethod
    def _won(row: UserPosition) -> bool:
        if row.exit_price is None:
            return False
        return row.exit_price > row.entry_price if row.direction == "LONG" else row.exit_price < row.entry_price

    @staticmethod
    def _lost(row: UserPosition) -> bool:
        if row.exit_price is None:
            return False
        return row.exit_price < row.entry_price if row.direction == "LONG" else row.exit_price > row.entry_price
