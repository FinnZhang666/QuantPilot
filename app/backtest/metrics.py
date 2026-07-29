from decimal import Decimal
from typing import Dict, List

from app.backtest.models import EquityPoint, TradeResult


def calculate_metrics(
    initial_cash: Decimal, ending_equity: Decimal,
    trades: List[TradeResult], equity: List[EquityPoint],
) -> Dict[str, object]:
    closed = [trade for trade in trades if trade.status in {"CLOSED", "FORCED_CLOSED"}]
    wins = [trade for trade in closed if (trade.net_pnl or Decimal("0")) > 0]
    losses = [trade for trade in closed if (trade.net_pnl or Decimal("0")) < 0]
    gross_profit = sum((trade.net_pnl or Decimal("0")) for trade in wins)
    gross_loss = sum((trade.net_pnl or Decimal("0")) for trade in losses)
    returns = [trade.return_pct or Decimal("0") for trade in closed]
    annualized = None
    if equity and equity[-1].timestamp > equity[0].timestamp:
        years = (equity[-1].timestamp - equity[0].timestamp).total_seconds() / (365.25 * 86400)
        if years > 0 and ending_equity > 0:
            annualized = Decimal(str(float(ending_equity / initial_cash) ** (1 / years) - 1))
    return {
        "closed_trades_count": len(closed),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pnl": ending_equity - initial_cash,
        "total_return_pct": ending_equity / initial_cash - 1,
        "annualized_return_pct": annualized,
        "max_drawdown_pct": min((point.drawdown_pct for point in equity), default=Decimal("0")),
        "win_rate": Decimal(len(wins)) / len(closed) if closed else None,
        "profit_factor": gross_profit / abs(gross_loss) if gross_loss else None,
        "average_trade_return_pct": sum(returns) / len(returns) if returns else None,
        "average_holding_bars": (
            Decimal(sum(trade.holding_bars or 0 for trade in closed)) / len(closed) if closed else None
        ),
    }
