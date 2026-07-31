from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import InvestmentPortfolio, PortfolioHolding, PortfolioWatchlist


class PortfolioRepository:
    def __init__(self, db: Session): self.db = db

    def create(self, **values):
        row = InvestmentPortfolio(**values); self.db.add(row); self.db.flush(); return row

    def get(self, portfolio_id: int): return self.db.get(InvestmentPortfolio, portfolio_id)

    def find_name(self, user_id: str, name: str):
        return self.db.scalar(select(InvestmentPortfolio).where(
            InvestmentPortfolio.user_id == user_id, InvestmentPortfolio.normalized_name == name,
        ))

    def get_default(self, user_id: str):
        return self.db.scalar(select(InvestmentPortfolio).where(
            InvestmentPortfolio.user_id == user_id, InvestmentPortfolio.is_default.is_(True),
        ))

    def list(self, user_id=None, status=None, default=None, page=1, page_size=100):
        query = select(InvestmentPortfolio)
        if user_id: query = query.where(InvestmentPortfolio.user_id == user_id)
        if status: query = query.where(InvestmentPortfolio.status == status)
        if default is not None: query = query.where(InvestmentPortfolio.is_default.is_(default))
        query = query.order_by(InvestmentPortfolio.is_default.desc(), InvestmentPortfolio.updated_at.desc())
        return list(self.db.scalars(query.offset((page - 1) * page_size).limit(page_size)))

    def count(self, user_id=None, status=None, default=None):
        query = select(func.count()).select_from(InvestmentPortfolio)
        if user_id: query = query.where(InvestmentPortfolio.user_id == user_id)
        if status: query = query.where(InvestmentPortfolio.status == status)
        if default is not None: query = query.where(InvestmentPortfolio.is_default.is_(default))
        return int(self.db.scalar(query) or 0)

    def clear_default(self, user_id: str, except_id: Optional[int] = None):
        rows = list(self.db.scalars(select(InvestmentPortfolio).where(
            InvestmentPortfolio.user_id == user_id, InvestmentPortfolio.is_default.is_(True),
        )))
        for row in rows:
            if row.id != except_id: row.is_default = False


class HoldingRepository:
    def __init__(self, db: Session): self.db = db
    def create(self, **values):
        row = PortfolioHolding(**values); self.db.add(row); self.db.flush(); return row
    def get(self, holding_id: int): return self.db.get(PortfolioHolding, holding_id)
    def list(self, portfolio_id=None, symbol=None, market=None, status=None, direction=None,
             opened_from=None, opened_to=None, closed_from=None, closed_to=None,
             page=1, page_size=100):
        query = self._filtered(portfolio_id, symbol, market, status, direction,
                               opened_from, opened_to, closed_from, closed_to)
        return list(self.db.scalars(query.order_by(PortfolioHolding.opened_at.desc(), PortfolioHolding.id.desc())
                                    .offset((page - 1) * page_size).limit(page_size)))
    def count(self, portfolio_id=None, symbol=None, market=None, status=None, direction=None,
              opened_from=None, opened_to=None, closed_from=None, closed_to=None):
        query = self._filtered(portfolio_id, symbol, market, status, direction,
                               opened_from, opened_to, closed_from, closed_to)
        return len(list(self.db.scalars(query)))
    @staticmethod
    def _filtered(portfolio_id, symbol, market, status, direction,
                  opened_from, opened_to, closed_from, closed_to):
        query = select(PortfolioHolding)
        values = ((PortfolioHolding.portfolio_id, portfolio_id), (PortfolioHolding.symbol, symbol),
                  (PortfolioHolding.market, market), (PortfolioHolding.status, status),
                  (PortfolioHolding.direction, direction))
        for field, value in values:
            if value is not None: query = query.where(field == value)
        if opened_from: query = query.where(PortfolioHolding.opened_at >= opened_from)
        if opened_to: query = query.where(PortfolioHolding.opened_at <= opened_to)
        if closed_from: query = query.where(PortfolioHolding.closed_at >= closed_from)
        if closed_to: query = query.where(PortfolioHolding.closed_at <= closed_to)
        return query


class WatchlistRepository:
    def __init__(self, db: Session): self.db = db
    def create(self, **values):
        row = PortfolioWatchlist(**values); self.db.add(row); self.db.flush(); return row
    def get(self, watchlist_id: int): return self.db.get(PortfolioWatchlist, watchlist_id)
    def exists(self, portfolio_id: int, market: str, symbol: str):
        return self.db.scalar(select(PortfolioWatchlist).where(
            PortfolioWatchlist.portfolio_id == portfolio_id,
            PortfolioWatchlist.market == market, PortfolioWatchlist.symbol == symbol,
        ))
    def list(self, portfolio_id: int, symbol=None, market=None, page=1, page_size=100):
        query = select(PortfolioWatchlist).where(PortfolioWatchlist.portfolio_id == portfolio_id)
        if symbol: query = query.where(PortfolioWatchlist.symbol == symbol)
        if market: query = query.where(PortfolioWatchlist.market == market)
        query = query.order_by(PortfolioWatchlist.display_order, PortfolioWatchlist.id)
        return list(self.db.scalars(query.offset((page - 1) * page_size).limit(page_size)))
    def count(self, portfolio_id: int, symbol=None, market=None):
        query = select(func.count()).select_from(PortfolioWatchlist).where(
            PortfolioWatchlist.portfolio_id == portfolio_id,
        )
        if symbol: query = query.where(PortfolioWatchlist.symbol == symbol)
        if market: query = query.where(PortfolioWatchlist.market == market)
        return int(self.db.scalar(query) or 0)
    def max_order(self, portfolio_id: int):
        return int(self.db.scalar(select(func.max(PortfolioWatchlist.display_order)).where(
            PortfolioWatchlist.portfolio_id == portfolio_id,
        )) or 0)
    def delete(self, row): self.db.delete(row)
