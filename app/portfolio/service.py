from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Portfolio


class PortfolioService:
    def __init__(self, db: Session):
        self.db = db

    def list_active(self):
        return list(self.db.scalars(select(Portfolio).where(Portfolio.is_active.is_(True))))
