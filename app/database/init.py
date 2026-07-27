from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.base import Base
from app.database.models import Portfolio

DEFAULT_PORTFOLIOS = ("AGGRESSIVE", "BALANCED", "CONSERVATIVE")


def create_schema(engine) -> None:
    Base.metadata.create_all(engine)


def seed_default_portfolios(db: Session, settings: Settings) -> None:
    for code in DEFAULT_PORTFOLIOS:
        if db.scalar(select(Portfolio).where(Portfolio.code == code)) is None:
            cash = settings.default_portfolio_cash
            db.add(
                Portfolio(
                    code=code,
                    name=code.title(),
                    initial_cash=cash,
                    cash=cash,
                    equity=cash,
                    currency="USD",
                    strategy_code=None,
                    is_active=True,
                )
            )
    db.commit()
