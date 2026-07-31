from app.telegram_product.base import decimal_text, escape_markdown, limit_message


def _safe(value) -> str:
    return escape_markdown(value)


def _number(value) -> str:
    return decimal_text(value)


def _limit(value: str) -> str:
    return limit_message(value)


def format_market_snapshot(snapshot) -> str:
    return _limit("📈 Market Snapshot\n%s\nPrice\n%s\nCandidate\n%s\nTrade Plan\n%s\n"
                  "Holding\n%s\nWatchlist\n%s\nFeature\n%s" % (
                      _safe(snapshot.symbol), _number(snapshot.latest_price),
                      _safe(snapshot.candidate_signal), _safe(snapshot.trade_plan_status),
                      "YES" if snapshot.holding == "HOLDING" else "NO",
                      "YES" if snapshot.watching == "WATCHING" else "NO",
                      _safe(snapshot.feature_status),
                  ))


def format_watchlist_snapshot(snapshot) -> str:
    return _limit("👀 Watchlist Snapshot\n" + format_market_snapshot(snapshot))


def format_snapshot_list(snapshots) -> str:
    rows = list(snapshots)
    if not rows: return "📈 Market Snapshot\n暂无数据"
    return _limit("📈 Market Snapshot\n" + "\n".join(
        "%s · %s · %s · %s" % (
            _safe(row.symbol), _number(row.latest_price),
            _safe(row.candidate_signal), _safe(row.strategy_status),
        ) for row in rows
    ))


def format_market_snapshot_summary(summary) -> str:
    return _limit("Today's Snapshot\nWatchlist\n%s\nHolding\n%s\nCandidate\n%s BUY / %s SELL\n"
                  "Trade Plans\n%s ACTIVE" % (
                      summary.get("watchlist", 0), summary.get("holding", 0),
                      summary.get("candidate_buy", 0), summary.get("candidate_sell", 0),
                      summary.get("active_trade_plans", 0),
                  ))
