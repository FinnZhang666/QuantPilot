from typing import Dict, Iterable, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database.models import (
    CandidateSignal,
    FeatureValueRecord,
    Instrument,
    InvestmentPortfolio,
    MarketBar,
    PortfolioHolding,
    PortfolioWatchlist,
    TradePlan,
)


def bare_symbol(value: str) -> str:
    return (value or "").strip().upper().split(".", 1)[-1]


class MarketSnapshotRepository:
    """Read-only source aggregator. It never flushes or commits a Session."""

    def __init__(self, db: Session):
        self.db = db

    def get_snapshot(self, symbol: str, market: str = "US", portfolio_id: Optional[int] = None) -> Dict[str, object]:
        symbol, market = bare_symbol(symbol), market.upper()
        variants = (symbol, "%s.%s" % (market, symbol))
        instrument = self.db.scalar(select(Instrument).where(or_(
            Instrument.symbol.in_(variants),
            (Instrument.market == market) & (Instrument.code == symbol),
        )).order_by(Instrument.updated_at.desc()).limit(1))
        bar = self.db.scalar(select(MarketBar).where(MarketBar.symbol.in_(variants))
                             .order_by(MarketBar.timestamp_utc.desc(), MarketBar.id.desc()).limit(1))
        feature = self.db.scalar(select(FeatureValueRecord).where(
            FeatureValueRecord.symbol.in_(variants), FeatureValueRecord.quality_status == "VALID",
        ).order_by(FeatureValueRecord.timestamp_utc.desc(), FeatureValueRecord.id.desc()).limit(1))
        candidate = self.db.scalar(select(CandidateSignal).where(
            CandidateSignal.symbol.in_(variants), CandidateSignal.status == "VALID",
        ).order_by(CandidateSignal.bar_timestamp.desc(), CandidateSignal.id.desc()).limit(1))
        plan = self.db.scalar(select(TradePlan).where(TradePlan.symbol.in_(variants))
                              .order_by(TradePlan.updated_at.desc(), TradePlan.id.desc()).limit(1))
        holding_query = select(PortfolioHolding).where(
            PortfolioHolding.symbol == symbol, PortfolioHolding.market == market,
            PortfolioHolding.status == "OPEN",
        )
        watch_query = select(PortfolioWatchlist).where(
            PortfolioWatchlist.symbol == symbol, PortfolioWatchlist.market == market,
        )
        if portfolio_id is not None:
            holding_query = holding_query.where(PortfolioHolding.portfolio_id == portfolio_id)
            watch_query = watch_query.where(PortfolioWatchlist.portfolio_id == portfolio_id)
        holdings = list(self.db.scalars(holding_query.order_by(PortfolioHolding.opened_at.desc())))
        watch = self.db.scalar(watch_query.order_by(PortfolioWatchlist.display_order, PortfolioWatchlist.id).limit(1))
        return {
            "symbol": symbol, "market": market, "instrument": instrument, "bar": bar,
            "feature": feature, "candidate": candidate, "plan": plan,
            "holdings": holdings, "watch": watch,
        }

    def list_snapshots(self, symbol: Optional[str] = None, market: Optional[str] = None,
                       page: Optional[int] = None, page_size: Optional[int] = None) -> Iterable[Dict[str, object]]:
        market = market.upper() if market else None
        keys = self._universe(market)
        if symbol:
            target = bare_symbol(symbol)
            keys = {key for key in keys if key[1] == target}
        rows = [self.get_snapshot(code, item_market) for item_market, code in sorted(keys, key=lambda x: x[1])]
        return self._page(rows, page, page_size)

    def list_watchlist_snapshots(self, portfolio_id: int, page=None, page_size=None) -> Iterable[Dict[str, object]]:
        rows = self.db.scalars(select(PortfolioWatchlist).where(
            PortfolioWatchlist.portfolio_id == portfolio_id,
        ).order_by(PortfolioWatchlist.display_order, PortfolioWatchlist.id))
        return self._page([self.get_snapshot(row.symbol, row.market, portfolio_id) for row in rows], page, page_size)

    def list_portfolio_snapshots(self, portfolio_id: int, page=None, page_size=None) -> Iterable[Dict[str, object]]:
        portfolio = self.db.get(InvestmentPortfolio, portfolio_id)
        if portfolio is None:
            return []
        keys = {(row.market, row.symbol) for row in self.db.scalars(select(PortfolioWatchlist).where(
            PortfolioWatchlist.portfolio_id == portfolio_id,
        ))}
        keys.update((row.market, row.symbol) for row in self.db.scalars(select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id, PortfolioHolding.status == "OPEN",
        )))
        return self._page([self.get_snapshot(code, market, portfolio_id) for market, code in sorted(keys, key=lambda x: x[1])], page, page_size)

    @staticmethod
    def _page(rows, page, page_size):
        if page is None or page_size is None:
            return rows
        return rows[(page - 1) * page_size:page * page_size]

    def _universe(self, market: Optional[str]):
        keys = set()
        instruments = self.db.scalars(select(Instrument))
        keys.update((row.market, bare_symbol(row.code or row.symbol)) for row in instruments)
        for model in (PortfolioWatchlist, PortfolioHolding):
            query = select(model)
            if model is PortfolioHolding:
                query = query.where(PortfolioHolding.status == "OPEN")
            keys.update((row.market, bare_symbol(row.symbol)) for row in self.db.scalars(query))
        for model in (CandidateSignal, TradePlan):
            keys.update((row.market, bare_symbol(row.symbol)) for row in self.db.scalars(select(model)))
        return {key for key in keys if key[1] and (market is None or key[0] == market)}
