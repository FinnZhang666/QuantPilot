from typing import Dict, List

from app.core.enums import FeatureValueType
from app.features.models import FeatureDefinition

ALL_INTERVALS = ("1m", "5m", "15m", "30m", "60m", "1d")
MINUTE_INTERVALS = ("1m", "5m", "15m", "30m", "60m")


def _definition(name: str, zh: str, category: str, bars: int, params=None, value_type=FeatureValueType.DECIMAL, intervals=ALL_INTERVALS, reference=None) -> FeatureDefinition:
    return FeatureDefinition(
        name, zh, category, zh, value_type, params or {}, bars, intervals,
        reference is not None, reference, "1.0.0"
    )


def default_feature_definitions() -> List[FeatureDefinition]:
    rows: List[FeatureDefinition] = []
    for period in (1, 5, 10, 20):
        rows.append(_definition("return_%s" % period, "%s周期收益率" % period, "RETURN", period + 1, {"period": period}))
    rows.append(_definition("log_return_1", "单周期对数收益率", "RETURN", 2))
    for period in (5, 10, 20, 50, 200):
        rows.append(_definition("sma_%s" % period, "SMA%s" % period, "TREND", period, {"period": period}))
    for period in (5, 10, 20, 50, 60, 200):
        rows.append(_definition("ema_%s" % period, "EMA%s" % period, "TREND", period, {"period": period, "adjust": False}))
    for name, zh, bars in (
        ("close_vs_ema20_pct", "收盘价距离EMA20百分比", 20),
        ("close_vs_ema60_pct", "收盘价距离EMA60百分比", 60),
        ("ema20_vs_ema60_pct", "EMA20距离EMA60百分比", 60),
        ("close_vs_sma20_pct", "收盘价距离SMA20百分比", 20),
        ("ema20_slope_5", "EMA20五周期斜率", 25),
        ("ema60_slope_5", "EMA60五周期斜率", 65),
    ):
        rows.append(_definition(name, zh, "TREND", bars))
    rows.append(_definition("trend_alignment", "趋势排列", "TREND", 200, value_type=FeatureValueType.TEXT))
    rows.append(_definition("rsi_14", "RSI14", "MOMENTUM", 15, {"period": 14}))
    for name, zh, bars in (
        ("macd_line_12_26", "MACD线", 26), ("macd_signal_9", "MACD信号线", 34),
        ("macd_histogram", "MACD柱", 34), ("roc_10", "ROC10", 11), ("roc_20", "ROC20", 21),
        ("true_range", "真实波幅", 2), ("atr_14", "ATR14", 15), ("atr_pct_14", "ATR百分比", 15),
        ("realized_volatility_20", "20周期实现波动率", 21),
        ("bollinger_mid_20", "布林中轨", 20), ("bollinger_upper_20_2", "布林上轨", 20),
        ("bollinger_lower_20_2", "布林下轨", 20), ("bollinger_width_pct", "布林带宽", 20),
        ("bollinger_position", "布林位置", 20),
    ):
        rows.append(_definition(name, zh, "MOMENTUM" if name.startswith(("macd", "roc")) else "VOLATILITY", bars))
    for period in (5, 20, 50):
        rows.append(_definition("volume_sma_%s" % period, "成交量均值%s" % period, "VOLUME", period))
    rows.extend([
        _definition("volume_ratio_20", "成交量比率20", "VOLUME", 21),
        _definition("turnover_sma_20", "成交额均值20", "VOLUME", 20),
        _definition("session_vwap_regular", "正常盘日内VWAP", "VWAP", 1, intervals=MINUTE_INTERVALS),
        _definition("close_vs_vwap_pct", "收盘价距离VWAP百分比", "VWAP", 1, intervals=MINUTE_INTERVALS),
        _definition("gap_open_pct", "开盘跳空", "PRICE_ACTION", 2),
        _definition("body_range_ratio", "K线实体比例", "PRICE_ACTION", 1),
        _definition("upper_wick_ratio", "上影线比例", "PRICE_ACTION", 1),
        _definition("lower_wick_ratio", "下影线比例", "PRICE_ACTION", 1),
        _definition("close_location_value", "收盘位置", "PRICE_ACTION", 1),
    ])
    for period in (20, 60, 252):
        rows.append(_definition("distance_from_high_%s_pct" % period, "距离%s周期高点" % period, "BREAKOUT", period))
        rows.append(_definition("drawdown_from_%s_high_pct" % period, "%s周期高点回撤" % period, "BREAKOUT", period))
        if period in (20, 60):
            rows.append(_definition("breakout_high_%s_pct" % period, "突破%s周期高点距离" % period, "BREAKOUT", period + 1))
    for period in (20, 60):
        rows.append(_definition("distance_from_low_%s_pct" % period, "距离%s周期低点" % period, "BREAKOUT", period))
    for period in (5, 20, 60):
        rows.append(_definition("relative_return_qqq_%s" % period, "相对QQQ收益%s" % period, "RELATIVE", period + 1, reference="US.QQQ"))
    rows.extend([
        _definition("relative_ratio_qqq", "相对QQQ价格比率", "RELATIVE", 1, reference="US.QQQ"),
        _definition("relative_ratio_qqq_ema20", "相对QQQ比率EMA20", "RELATIVE", 20, reference="US.QQQ"),
        _definition("relative_ratio_vs_ema20_pct", "相对比率距离EMA20", "RELATIVE", 20, reference="US.QQQ"),
        _definition("relative_return_soxx_20", "相对SOXX收益20", "RELATIVE", 21, reference="US.SOXX"),
    ])
    for name, zh, ref, bars in (
        ("market_qqq_return_1", "QQQ市场收益1", "US.QQQ", 2),
        ("market_qqq_return_5", "QQQ市场收益5", "US.QQQ", 6),
        ("market_qqq_close_vs_ema20_pct", "QQQ距离EMA20", "US.QQQ", 20),
        ("market_qqq_atr_pct_14", "QQQ ATR百分比", "US.QQQ", 15),
        ("market_soxx_return_5", "SOXX市场收益5", "US.SOXX", 6),
        ("market_soxx_close_vs_ema20_pct", "SOXX距离EMA20", "US.SOXX", 20),
    ):
        rows.append(_definition(name, zh, "MARKET", bars, reference=ref))
    return rows


DEFAULT_DEFINITIONS: Dict[str, FeatureDefinition] = {
    item.feature_name: item for item in default_feature_definitions()
}
