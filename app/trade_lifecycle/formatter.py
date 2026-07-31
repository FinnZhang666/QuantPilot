from typing import Iterable


def format_trade_plan(plan) -> str:
    return (
        "【Trade Plan】\n"
        "Symbol: %s\nStage: %s\nDirection: %s\nTimeframe: %s\n"
        "Reference Price: %s\nBuy Zone: %s\nAdd-on Zone: %s\nBreakout Zone: %s\n"
        "Stop Loss: %s\nTargets: %s\nConfidence: %s\nGenerated Time: %s\n"
        "Invalidation: %s\nStrategy: %s %s\n\n"
        "Trade Plan用于结构化研究与生命周期跟踪，不是订单或即时交易指令。"
    ) % (
        plan.symbol, plan.lifecycle_stage, plan.direction, plan.timeframe,
        _value(plan.reference_price), _zone(plan.buy_zone_lower, plan.buy_zone_upper),
        _zone(plan.trend_add_on_zone_lower, plan.trend_add_on_zone_upper),
        _zone(plan.breakout_zone_lower, plan.breakout_zone_upper),
        _value(plan.stop_loss_price), _targets(plan.target_prices_json),
        _value(plan.confidence), _time(plan.created_at),
        plan.invalidation_condition or _missing(), plan.strategy_name, plan.strategy_version,
    )


def _missing() -> str:
    return "暂无（策略未提供）"


def _value(value) -> str:
    return str(value) if value is not None else _missing()


def _zone(lower, upper) -> str:
    if lower is None and upper is None:
        return _missing()
    return "%s - %s" % (_value(lower), _value(upper))


def _targets(values: Iterable[object]) -> str:
    values = list(values or [])
    return ", ".join(str(value) for value in values) if values else _missing()


def _time(value) -> str:
    return value.isoformat() if value is not None else _missing()
