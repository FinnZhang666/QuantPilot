from app.telegram_product.base import decimal_text, escape_markdown, limit_message


def _safe(value) -> str:
    return escape_markdown(value)


def _decimal(value) -> str:
    return decimal_text(value)


def _limit(text: str) -> str:
    return limit_message(text)


def format_portfolio_summary(portfolio, statistics) -> str:
    return _limit(
        "💼 我的投资\n组合：%s\n币种：%s\n状态：%s\n当前持仓：%s\n已关闭：%s\n关注标的：%s\n\n"
        "以上为 Trade Companion 内部记录，不是券商实时仓位。" % (
            _safe(portfolio.name), _safe(portfolio.currency), _safe(portfolio.status),
            statistics.get("open_holdings", 0), statistics.get("closed_holdings", 0),
            statistics.get("watchlist_count", 0),
        )
    )


def format_portfolio_holdings(holdings) -> str:
    lines = ["持仓"]
    for row in holdings:
        lines.append("%s · %s · 成本 %s" % (_safe(row.symbol), _decimal(row.quantity), _decimal(row.average_cost)))
    if len(lines) == 1: lines.append("暂无持仓")
    return _limit("\n".join(lines))


def format_portfolio_watchlist(items) -> str:
    lines = ["关注"] + ["%s · %s" % (_safe(row.symbol), _safe(row.market)) for row in items]
    if len(lines) == 1: lines.append("暂无关注标的")
    return _limit("\n".join(lines))


def format_portfolio_statistics(statistics) -> str:
    return _limit("统计\n总持仓：%s\n当前持仓：%s\n已关闭：%s\n关注标的：%s" % (
        statistics.get("total_holdings", 0), statistics.get("open_holdings", 0),
        statistics.get("closed_holdings", 0), statistics.get("watchlist_count", 0),
    ))


def format_holding_summary(holding, portfolio_name=None) -> str:
    return _limit("%s\n%s 股\n平均成本\n%s\n状态\n%s\nPortfolio\n%s" % (
        _safe(holding.symbol), _decimal(holding.quantity), _decimal(holding.average_cost),
        _safe(holding.status), _safe(portfolio_name),
    ))


def format_holding_detail(holding, portfolio_name=None) -> str:
    return _limit(format_holding_summary(holding, portfolio_name) +
                  "\n方向\n%s\n市场\n%s\nTrade Plan\n%s\nUser Position\n%s\n备注\n%s" % (
                      _safe(holding.direction), _safe(holding.market),
                      _safe(holding.trade_plan_id), _safe(holding.user_position_id), _safe(holding.notes),
                  ))
