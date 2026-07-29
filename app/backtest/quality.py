from datetime import timezone
from typing import Iterable, List

from app.backtest.models import BacktestBar, BacktestConfig, BacktestSignal


def validate_inputs(config: BacktestConfig, bars: Iterable[BacktestBar], signals: Iterable[BacktestSignal]) -> List[str]:
    errors = []
    if config.start_time >= config.end_time:
        errors.append("时间范围无效：开始时间必须早于结束时间。")
    if config.initial_cash <= 0:
        errors.append("初始资金必须大于0。")
    previous = None
    seen = set()
    for bar in bars:
        if bar.timestamp.tzinfo is None or bar.timestamp.utcoffset() is None:
            errors.append("K线时间戳必须包含UTC时区。")
        elif bar.timestamp.utcoffset() != timezone.utc.utcoffset(bar.timestamp):
            errors.append("K线主时间必须为UTC。")
        if bar.timestamp in seen:
            errors.append("K线时间戳重复。")
        seen.add(bar.timestamp)
        if previous is not None and bar.timestamp <= previous:
            errors.append("K线时间不是严格递增。")
        previous = bar.timestamp
        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            errors.append("K线价格必须大于0。")
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close) or bar.high < bar.low:
            errors.append("K线OHLC关系无效。")
        if bar.volume < 0:
            errors.append("成交量不能为负。")
    hashes = {signal.parameters_hash for signal in signals}
    if hashes and hashes != {config.parameters_hash}:
        errors.append("Signal参数Hash不一致。")
    keys = [(signal.timestamp, signal.parameters_hash) for signal in signals]
    if len(keys) != len(set(keys)):
        errors.append("CONFLICTING_SIGNALS")
    return list(dict.fromkeys(errors))
