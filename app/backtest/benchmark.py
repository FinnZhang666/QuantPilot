from decimal import Decimal
from typing import Dict, List

from app.backtest.models import BacktestBar


def buy_and_hold(initial_cash: Decimal, bars: List[BacktestBar]) -> Dict[str, object]:
    if not bars or bars[0].open <= 0:
        return {"status": "UNAVAILABLE", "return_pct": None, "max_drawdown_pct": None}
    shares = int(initial_cash // bars[0].open)
    cash = initial_cash - shares * bars[0].open
    values = [cash + shares * bar.close for bar in bars]
    peak = values[0]
    drawdowns = []
    for value in values:
        peak = max(peak, value)
        drawdowns.append(value / peak - 1)
    return {
        "status": "AVAILABLE", "return_pct": values[-1] / initial_cash - 1,
        "max_drawdown_pct": min(drawdowns), "coverage_start": bars[0].timestamp,
        "coverage_end": bars[-1].timestamp,
    }
