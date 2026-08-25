from sqlalchemy import desc, select

from app.database.models import SystemPaperOrder, SystemPaperPosition


class PaperRuntimeQueryService:
    """Read-only projection for Agent, Dashboard, and Telegram consumers."""

    def __init__(self, db):
        self.db = db

    def positions(self, symbol=None, status="OPEN", limit=20):
        query = select(SystemPaperPosition)
        if symbol:
            query = query.where(SystemPaperPosition.symbol == symbol.upper())
        if status:
            query = query.where(SystemPaperPosition.status == status)
        rows = self.db.scalars(query.order_by(desc(SystemPaperPosition.updated_at)).limit(limit))
        return [self._serialize(row) for row in rows]

    def orders(self, symbol=None, order_id=None, limit=20):
        query = select(SystemPaperOrder)
        if symbol:
            query = query.where(SystemPaperOrder.symbol == symbol.upper())
        if order_id is not None:
            query = query.where(SystemPaperOrder.id == int(order_id))
        rows = self.db.scalars(query.order_by(desc(SystemPaperOrder.updated_at)).limit(limit))
        return [self._serialize(row) for row in rows]

    @staticmethod
    def _serialize(row):
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}
