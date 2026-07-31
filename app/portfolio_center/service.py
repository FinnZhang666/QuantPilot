from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import TradePlan, UserPosition
from app.portfolio_center.errors import (
    DuplicateDefaultPortfolio,
    DuplicatePortfolioName,
    DuplicateSymbol,
    HoldingNotFound,
    PermissionDenied,
    PortfolioNotFound,
    ValidationError,
    WatchlistNotFound,
)
from app.portfolio_center.repository import HoldingRepository, PortfolioRepository, WatchlistRepository
from app.portfolio_center.validation import (
    clean_currency,
    clean_direction,
    clean_market,
    clean_name,
    clean_symbol,
    clean_user_id,
    decimal_value,
    normalized_name,
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class PortfolioService:
    def __init__(self, db: Session):
        self.db, self.repository = db, PortfolioRepository(db)

    def create_portfolio(self, user_id, name, description=None, currency="USD", is_default=False):
        user_id, name = clean_user_id(user_id), clean_name(name)
        normalized = normalized_name(name)
        if self.repository.find_name(user_id, normalized):
            raise DuplicatePortfolioName("同一用户已存在同名Portfolio。")
        currency = clean_currency(currency)
        try:
            make_default = bool(is_default or self.repository.count(user_id=user_id) == 0)
            if make_default: self.repository.clear_default(user_id)
            row = self.repository.create(
                user_id=user_id, name=name, normalized_name=normalized,
                description=description, currency=currency, status="ACTIVE",
                is_default=make_default,
            )
            self.db.commit(); return row
        except Exception:
            self.db.rollback(); raise

    def get(self, portfolio_id: int, owner_id: Optional[str] = None):
        row = self.repository.get(portfolio_id)
        if row is None: raise PortfolioNotFound("Portfolio不存在。")
        self._owner(row, owner_id); return row

    def list_portfolios(self, user_id=None, status=None, default=None, page=1, page_size=100):
        if status and status not in {"ACTIVE", "INACTIVE"}: raise ValidationError("Portfolio状态无效。")
        return self.repository.list(user_id, status, default, page, page_size)

    def count(self, user_id=None, status=None, default=None):
        return self.repository.count(user_id, status, default)

    def rename_portfolio(self, portfolio_id: int, name: str):
        row, name = self.get(portfolio_id), clean_name(name)
        normalized = normalized_name(name)
        duplicate = self.repository.find_name(row.user_id, normalized)
        if duplicate and duplicate.id != row.id: raise DuplicatePortfolioName("同一用户已存在同名Portfolio。")
        row.name, row.normalized_name = name, normalized
        self.db.commit(); return row

    def update(self, portfolio_id: int, name=None, description=None, currency=None, status=None):
        row = self.get(portfolio_id)
        try:
            if name is not None:
                clean = clean_name(name); normalized = normalized_name(clean)
                duplicate = self.repository.find_name(row.user_id, normalized)
                if duplicate and duplicate.id != row.id:
                    raise DuplicatePortfolioName("同一用户已存在同名Portfolio。")
                row.name, row.normalized_name = clean, normalized
            if description is not None: row.description = description
            if currency is not None: row.currency = clean_currency(currency)
            if status is not None:
                status = status.upper()
                if status not in {"ACTIVE", "INACTIVE"}: raise ValidationError("Portfolio状态无效。")
                if status == "INACTIVE" and row.is_default:
                    raise DuplicateDefaultPortfolio("默认Portfolio不能停用，请先设置另一个默认Portfolio。")
                row.status = status
            self.db.commit(); return row
        except Exception:
            self.db.rollback(); raise

    def set_default(self, portfolio_id: int):
        row = self.get(portfolio_id)
        if row.status != "ACTIVE": raise ValidationError("只有ACTIVE Portfolio可以设为默认。")
        try:
            self.repository.clear_default(row.user_id, row.id)
            row.is_default = True
            self.db.commit(); return row
        except Exception:
            self.db.rollback(); raise

    def get_default(self, user_id: str): return self.repository.get_default(clean_user_id(user_id))

    @staticmethod
    def _owner(row, owner_id):
        if owner_id is not None and row.user_id != owner_id:
            raise PermissionDenied("无权访问其他用户的Portfolio。")


class HoldingService:
    def __init__(self, db: Session):
        self.db, self.repository = db, HoldingRepository(db)
        self.portfolios = PortfolioService(db)

    def open_holding(self, portfolio_id, symbol, market, direction, quantity, average_cost,
                     opened_at=None, trade_plan_id=None, user_position_id=None, notes=None,
                     owner_id=None):
        portfolio = self.portfolios.get(portfolio_id, owner_id)
        if portfolio.status != "ACTIVE": raise ValidationError("不能向INACTIVE Portfolio添加Holding。")
        values = {
            "portfolio_id": portfolio.id, "symbol": clean_symbol(symbol),
            "market": clean_market(market), "direction": clean_direction(direction),
            "quantity": decimal_value(quantity, "quantity", False),
            "average_cost": decimal_value(average_cost, "average_cost", True),
            "opened_at": _aware(opened_at or datetime.now(timezone.utc)),
            "trade_plan_id": trade_plan_id, "user_position_id": user_position_id,
            "notes": notes, "status": "OPEN",
        }
        if trade_plan_id is not None and self.db.get(TradePlan, trade_plan_id) is None:
            raise ValidationError("关联Trade Plan不存在。")
        if user_position_id is not None and self.db.get(UserPosition, user_position_id) is None:
            raise ValidationError("关联User Position不存在。")
        try:
            row = self.repository.create(**values); self.db.commit(); return row
        except Exception:
            self.db.rollback(); raise

    def get_holding(self, holding_id: int, owner_id=None):
        row = self.repository.get(holding_id)
        if row is None: raise HoldingNotFound("Holding不存在。")
        self.portfolios.get(row.portfolio_id, owner_id); return row

    def close_holding(self, holding_id: int, closed_at=None, notes=None, owner_id=None):
        row = self.get_holding(holding_id, owner_id)
        if row.status != "OPEN": raise ValidationError("CLOSED Holding不能再次关闭。")
        closed = _aware(closed_at or datetime.now(timezone.utc))
        opened = _aware(row.opened_at)
        if closed < opened: raise ValidationError("closed_at不能早于opened_at。")
        try:
            row.status, row.closed_at = "CLOSED", closed
            if notes is not None: row.notes = notes
            self.db.commit(); return row
        except Exception:
            self.db.rollback(); raise

    def update_notes(self, holding_id: int, notes: Optional[str], owner_id=None):
        row = self.get_holding(holding_id, owner_id); row.notes = notes; self.db.commit(); return row

    def list_all(self, **filters): return self.repository.list(**self._filters(filters))
    def count(self, **filters): return self.repository.count(**self._filters(filters))
    def list_open(self, portfolio_id, **kwargs): return self.repository.list(portfolio_id=portfolio_id, status="OPEN", **kwargs)
    def list_closed(self, portfolio_id, **kwargs): return self.repository.list(portfolio_id=portfolio_id, status="CLOSED", **kwargs)
    def search_holdings(self, **filters): return self.list_all(**filters)

    @staticmethod
    def _filters(filters):
        values = dict(filters)
        if values.get("symbol"): values["symbol"] = clean_symbol(values["symbol"])
        if values.get("market"): values["market"] = clean_market(values["market"])
        if values.get("direction"): values["direction"] = clean_direction(values["direction"])
        if values.get("status"):
            values["status"] = values["status"].upper()
            if values["status"] not in {"OPEN", "CLOSED"}: raise ValidationError("Holding状态无效。")
        for start, end in (("opened_from", "opened_to"), ("closed_from", "closed_to")):
            if values.get(start) and values.get(end) and values[start] > values[end]:
                raise ValidationError("时间范围无效。")
        return values


class WatchlistService:
    def __init__(self, db: Session):
        self.db, self.repository = db, WatchlistRepository(db)
        self.portfolios = PortfolioService(db)

    def add_symbol(self, portfolio_id, symbol, market="US", notes=None, display_order=None, owner_id=None):
        portfolio = self.portfolios.get(portfolio_id, owner_id)
        if portfolio.status != "ACTIVE": raise ValidationError("不能修改INACTIVE Portfolio的Watchlist。")
        symbol, market = clean_symbol(symbol), clean_market(market)
        if self.repository.exists(portfolio_id, market, symbol): raise DuplicateSymbol("Already Exists")
        order = self.repository.max_order(portfolio_id) + 10 if display_order is None else int(display_order)
        try:
            row = self.repository.create(portfolio_id=portfolio_id, symbol=symbol, market=market,
                                         notes=notes, display_order=order)
            self.db.commit(); return row
        except Exception:
            self.db.rollback(); raise

    def get(self, watchlist_id, portfolio_id=None, owner_id=None):
        row = self.repository.get(watchlist_id)
        if row is None or (portfolio_id is not None and row.portfolio_id != portfolio_id):
            raise WatchlistNotFound("Watchlist记录不存在。")
        self.portfolios.get(row.portfolio_id, owner_id); return row

    def remove_symbol(self, watchlist_id, portfolio_id=None, owner_id=None):
        row = self.get(watchlist_id, portfolio_id, owner_id)
        self.repository.delete(row); self.db.commit(); return row

    def list_symbols(self, portfolio_id, symbol=None, market=None, page=1, page_size=100, owner_id=None):
        self.portfolios.get(portfolio_id, owner_id)
        symbol = clean_symbol(symbol) if symbol else None
        market = clean_market(market) if market else None
        return self.repository.list(portfolio_id, symbol, market, page, page_size)

    def count(self, portfolio_id, symbol=None, market=None): return self.repository.count(portfolio_id, symbol, market)
    def exists(self, portfolio_id, symbol, market="US"):
        return self.repository.exists(portfolio_id, clean_market(market), clean_symbol(symbol)) is not None

    def move_order(self, watchlist_id, display_order, portfolio_id=None, owner_id=None):
        row = self.get(watchlist_id, portfolio_id, owner_id)
        row.display_order = int(display_order); self.db.commit(); return row

    def update_notes(self, watchlist_id, notes, portfolio_id=None, owner_id=None):
        row = self.get(watchlist_id, portfolio_id, owner_id)
        row.notes = notes; self.db.commit(); return row


class PortfolioStatisticsService:
    def __init__(self, db: Session):
        self.db, self.holdings, self.watchlist = db, HoldingRepository(db), WatchlistRepository(db)
        self.portfolios = PortfolioService(db)

    def calculate(self, portfolio_id: int, owner_id=None):
        self.portfolios.get(portfolio_id, owner_id)
        rows = self.holdings.list(portfolio_id=portfolio_id, page=1, page_size=100000)
        opened = [_aware(row.opened_at) for row in rows if row.opened_at]
        return {
            "portfolio_id": portfolio_id,
            "total_holdings": len(rows),
            "open_holdings": sum(row.status == "OPEN" for row in rows),
            "closed_holdings": sum(row.status == "CLOSED" for row in rows),
            "watchlist_count": self.watchlist.count(portfolio_id),
            "long_count": sum(row.direction == "LONG" for row in rows),
            "short_count": sum(row.direction == "SHORT" for row in rows),
            "earliest_holding_opened_at": min(opened) if opened else None,
            "latest_holding_opened_at": max(opened) if opened else None,
        }
