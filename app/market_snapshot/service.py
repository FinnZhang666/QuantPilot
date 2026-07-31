from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, Optional

from sqlalchemy.orm import Session

from app.market_snapshot.models import MarketSnapshot
from app.market_snapshot.repository import MarketSnapshotRepository, bare_symbol
from app.portfolio_center.errors import PortfolioNotFound, ValidationError
from app.portfolio_center.service import PortfolioService
from app.portfolio_center.validation import clean_market, clean_symbol


class SnapshotNotFound(ValueError):
    pass


class MarketSnapshotService:
    def __init__(self, db: Session):
        self.repository = MarketSnapshotRepository(db)
        self.portfolios = PortfolioService(db)
        self._cache: Dict[str, MarketSnapshot] = {}

    def get_snapshot(self, symbol: str, market: str = "US", portfolio_id: Optional[int] = None) -> MarketSnapshot:
        symbol, market = clean_symbol(bare_symbol(symbol)), clean_market(market)
        if portfolio_id is not None:
            self.portfolios.get(portfolio_id)
        key = "%s:%s:%s" % (portfolio_id, market, symbol)
        if key not in self._cache:
            raw = self.repository.get_snapshot(symbol, market, portfolio_id)
            if not any((raw["instrument"], raw["bar"], raw["feature"], raw["candidate"],
                        raw["plan"], raw["holdings"], raw["watch"])):
                raise SnapshotNotFound("Market Snapshot不存在。")
            self._cache[key] = self._build(raw)
        return self._cache[key]

    def list_snapshots(self, symbol=None, market=None, holding=None, watching=None,
                       candidate_signal=None, trade_plan=None, strategy_status=None,
                       page=1, page_size=100):
        if page < 1 or page_size < 1 or page_size > 200:
            raise ValidationError("分页参数无效。")
        market = clean_market(market) if market else None
        rows = [self._build(raw) for raw in self.repository.list_snapshots(symbol, market)]
        rows = self._filter(rows, holding, watching, candidate_signal, trade_plan, strategy_status)
        total = len(rows)
        return rows[(page - 1) * page_size:page * page_size], total

    def list_watchlist_snapshots(self, portfolio_id: int, page=1, page_size=100):
        self.portfolios.get(portfolio_id)
        if page < 1 or page_size < 1 or page_size > 200: raise ValidationError("分页参数无效。")
        rows = [self._build(raw) for raw in self.repository.list_watchlist_snapshots(portfolio_id)]
        return rows[(page - 1) * page_size:page * page_size], len(rows)

    def list_portfolio_snapshots(self, portfolio_id: int, page=1, page_size=100):
        self.portfolios.get(portfolio_id)
        if page < 1 or page_size < 1 or page_size > 200: raise ValidationError("分页参数无效。")
        rows = [self._build(raw) for raw in self.repository.list_portfolio_snapshots(portfolio_id)]
        return rows[(page - 1) * page_size:page * page_size], len(rows)

    @staticmethod
    def summary(snapshots: Iterable[MarketSnapshot]):
        rows = list(snapshots)
        return {
            "total": len(rows), "watchlist": sum(row.watching == "WATCHING" for row in rows),
            "holding": sum(row.holding == "HOLDING" for row in rows),
            "candidate_buy": sum(row.candidate_signal == "BUY" for row in rows),
            "candidate_sell": sum(row.candidate_signal == "SELL" for row in rows),
            "active_trade_plans": sum(row.strategy_status == "ACTIVE" for row in rows),
        }

    @staticmethod
    def _filter(rows, holding, watching, candidate, trade_plan, strategy):
        if holding is not None: rows = [row for row in rows if (row.holding == "HOLDING") is holding]
        if watching is not None: rows = [row for row in rows if (row.watching == "WATCHING") is watching]
        if candidate:
            candidate = candidate.upper()
            if candidate not in {"NONE", "BUY", "SELL", "WATCH"}: raise ValidationError("Candidate过滤值无效。")
            rows = [row for row in rows if row.candidate_signal == candidate]
        if trade_plan:
            trade_plan = trade_plan.upper()
            allowed = {"NONE", "DISCOVER", "PLAN", "COMPANION", "REVIEW", "CANCELLED", "EXPIRED"}
            if trade_plan not in allowed: raise ValidationError("Trade Plan过滤值无效。")
            rows = [row for row in rows if row.trade_plan_status == trade_plan]
        if strategy:
            strategy = strategy.upper()
            if strategy not in {"UNKNOWN", "NO_DATA", "WATCH", "READY", "ACTIVE"}:
                raise ValidationError("Strategy状态过滤值无效。")
            rows = [row for row in rows if row.strategy_status == strategy]
        return rows

    @staticmethod
    def _build(raw) -> MarketSnapshot:
        holdings = raw["holdings"]
        quantity = sum((Decimal(str(row.quantity)) for row in holdings), Decimal("0"))
        total_cost = sum((Decimal(str(row.quantity)) * Decimal(str(row.average_cost)) for row in holdings), Decimal("0"))
        average = total_cost / quantity if quantity else None
        candidate = raw["candidate"]
        candidate_status = "NONE"
        if candidate:
            candidate_status = {
                "CANDIDATE_BUY": "BUY", "CANDIDATE_EXIT": "SELL",
                "CANDIDATE_REDUCE": "SELL", "WATCH": "WATCH",
            }.get(candidate.signal_type, "NONE")
        plan, bar, feature, watch = raw["plan"], raw["bar"], raw["feature"], raw["watch"]
        watching = "WATCHING" if watch else "NOT_WATCHING"
        if plan: strategy_status = "ACTIVE"
        elif candidate_status != "NONE": strategy_status = "READY"
        elif watching == "WATCHING": strategy_status = "WATCH"
        elif not bar and not feature: strategy_status = "NO_DATA"
        else: strategy_status = "UNKNOWN"
        timestamps = [getattr(value, "updated_at", None) for value in (raw["instrument"], bar, feature, candidate, plan, watch)]
        timestamps.extend(getattr(row, "updated_at", None) for row in holdings)
        timestamps = [value.replace(tzinfo=None) for value in timestamps if isinstance(value, datetime)]
        return MarketSnapshot(
            symbol=raw["symbol"], market=raw["market"],
            display_name=(raw["instrument"].display_name if raw["instrument"] else raw["symbol"]),
            latest_price=(Decimal(str(bar.close)) if bar else None),
            latest_bar_time=(bar.timestamp_utc if bar else None), strategy_status=strategy_status,
            candidate_signal=candidate_status,
            trade_plan_status=(plan.lifecycle_stage if plan else "NONE"),
            holding="HOLDING" if holdings else "NOT_HOLDING",
            holding_quantity=quantity if holdings else None, average_cost=average,
            watching=watching, feature_status="FEATURE_READY" if feature else "FEATURE_MISSING",
            updated_at=max(timestamps) if timestamps else None,
            trade_plan_id=plan.plan_id if plan else None,
            holding_id=holdings[0].id if holdings else None,
            portfolio_id=(watch.portfolio_id if watch else holdings[0].portfolio_id if holdings else None),
        )
