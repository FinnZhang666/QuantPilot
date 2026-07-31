import re
from decimal import Decimal


MAX_LENGTH = 4000


def _safe(value) -> str:
    text = "未记录" if value is None or value == "" else str(value)
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)


def _number(value) -> str:
    return "未记录" if value is None else format(Decimal(str(value)).normalize(), "f")


def _limit(value: str) -> str:
    return value if len(value) <= MAX_LENGTH else value[:MAX_LENGTH - 1] + "…"


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
