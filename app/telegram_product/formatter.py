from app.companion.formatter import format_companion_analysis
from app.market_snapshot.formatter import format_market_snapshot
from app.portfolio_center.formatter import format_holding_detail, format_portfolio_summary
from app.telegram_product.presenter import TelegramPresenter
from app.trade_lifecycle.formatter import format_trade_plan
from app.trade_review.formatter import format_trade_review


class TelegramFormatter:
    """One product formatter facade that reuses the established object formatters."""

    def __init__(self):
        self.presenter = TelegramPresenter()

    def overview(self, overview, language="zh-CN"):
        return self.presenter.preview(overview, language)

    @staticmethod
    def snapshot(snapshot):
        return format_market_snapshot(snapshot)

    @staticmethod
    def trade_plan(plan):
        return format_trade_plan(plan)

    @staticmethod
    def holding(holding, portfolio_name=None):
        return format_holding_detail(holding, portfolio_name)

    @staticmethod
    def portfolio(portfolio, statistics):
        return format_portfolio_summary(portfolio, statistics)

    @staticmethod
    def review(review, symbol):
        return format_trade_review(review, symbol)

    @staticmethod
    def companion(analysis, symbol, lifecycle):
        return format_companion_analysis(analysis, symbol, lifecycle)
