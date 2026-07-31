from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import UserPosition
from app.participation.repository import UserPositionRepository


class UserParticipationService:
    def __init__(self, db: Session, repository: Optional[UserPositionRepository] = None):
        self.repository = repository or UserPositionRepository(db)

    def open(
        self, user_id: str, trade_plan_id: str, entry_price,
        quantity=None, opened_at: Optional[datetime] = None,
        source: str = "ADMIN_API", notes: Optional[str] = None,
    ) -> UserPosition:
        user = self._text(user_id, "user_id")
        plan = self.repository.get_plan(trade_plan_id)
        if plan is None:
            raise KeyError("Trade Plan不存在。")
        if plan.plan_status != "ACTIVE" or plan.lifecycle_stage != "PLAN":
            raise ValueError("只有处于PLAN阶段的有效Trade Plan可以创建参与记录。")
        if self.repository.exists_open(user, plan.id):
            raise ValueError("该用户已参与此Trade Plan，不能重复创建未平仓记录。")
        row = UserPosition(
            user_id=user, trade_plan_id=plan.id, symbol=plan.symbol,
            direction=plan.direction, entry_price=self._positive(entry_price, "entry_price"),
            quantity=self._optional_positive(quantity, "quantity"),
            opened_at=self._aware(opened_at or datetime.now(timezone.utc)),
            status="OPEN", source=self._text(source, "source"), notes=self._notes(notes),
        )
        self.repository.create(row)
        self.repository.commit()
        return row

    def close(
        self, position_id: int, exit_price, closed_at: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> UserPosition:
        row = self._required(position_id)
        if row.status != "OPEN":
            raise ValueError("只有OPEN状态的User Position可以平仓。")
        validated_price = self._positive(exit_price, "exit_price")
        validated_time = self._aware(closed_at or datetime.now(timezone.utc))
        if validated_time < self._aware(row.opened_at):
            raise ValueError("平仓时间不能早于参与时间。")
        row.exit_price = validated_price
        row.closed_at = validated_time
        row.status = "CLOSED"
        if notes is not None:
            row.notes = self._notes(notes)
        self.repository.update(row)
        self.repository.commit()
        return row

    def get(self, position_id: int):
        return self.repository.get(position_id)

    def list(self, user_id=None, symbol=None, status=None, limit=100, offset=0):
        if status and status.upper() not in ("OPEN", "CLOSED", "CANCELLED"):
            raise ValueError("User Position状态无效。")
        return self.repository.list(user_id, symbol, status, limit, offset)

    def count(self, user_id=None, symbol=None, status=None):
        return self.repository.count(user_id, symbol, status)

    def statistics(self, user_id=None):
        return self.repository.statistics(user_id)

    def source_plan(self, row: UserPosition):
        return self.repository.get_plan_by_id(row.trade_plan_id)

    def _required(self, position_id):
        row = self.repository.get(position_id)
        if row is None:
            raise KeyError("User Position不存在。")
        return row

    @staticmethod
    def _positive(value, name):
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("%s必须是有效数字。" % name)
        if not result.is_finite() or result <= 0:
            raise ValueError("%s必须大于0。" % name)
        return result

    @classmethod
    def _optional_positive(cls, value, name):
        return None if value is None else cls._positive(value, name)

    @staticmethod
    def _text(value, name):
        result = str(value or "").strip()
        if not result:
            raise ValueError("%s不能为空。" % name)
        return result

    @staticmethod
    def _notes(value):
        value = value.strip() if value else None
        return value or None

    @staticmethod
    def _aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
