import math
from typing import Dict, Optional

import numpy as np
import pandas as pd


ANNUALIZATION_FACTORS = {
    "1d": 252.0,
    "60m": 252.0 * 6.5,
    "30m": 252.0 * 13.0,
    "15m": 252.0 * 26.0,
    "5m": 252.0 * 78.0,
    "1m": 252.0 * 390.0,
}


def _pct(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a / b.replace(0, np.nan) - 1.0) * 100.0


def _wilder(values: pd.Series, period: int) -> pd.Series:
    return values.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


class FeatureCalculator:
    """纯函数式特征计算；所有rolling均为右对齐且不使用未来值。"""

    def calculate(
        self,
        bars: pd.DataFrame,
        interval: str,
        references: Optional[Dict[str, pd.DataFrame]] = None,
    ) -> Dict[str, pd.Series]:
        references = references or {}
        frame = bars.sort_index().copy()
        o, h, l, c = (frame[name].astype(float) for name in ("open", "high", "low", "close"))
        volume = frame["volume"].astype(float)
        result: Dict[str, pd.Series] = {}

        for period in (1, 5, 10, 20):
            result["return_%s" % period] = c.pct_change(period, fill_method=None)
        result["log_return_1"] = np.log(c.where(c > 0) / c.shift(1).where(c.shift(1) > 0))
        for period in (5, 10, 20, 50, 200):
            result["sma_%s" % period] = c.rolling(period, min_periods=period).mean()
        for period in (5, 10, 20, 50, 60, 200):
            result["ema_%s" % period] = c.ewm(span=period, adjust=False, min_periods=period).mean()
        result["close_vs_ema20_pct"] = _pct(c, result["ema_20"])
        result["close_vs_ema60_pct"] = _pct(c, result["ema_60"])
        result["ema20_vs_ema60_pct"] = _pct(result["ema_20"], result["ema_60"])
        result["close_vs_sma20_pct"] = _pct(c, result["sma_20"])
        result["ema20_slope_5"] = result["ema_20"] / result["ema_20"].shift(5) - 1.0
        result["ema60_slope_5"] = result["ema_60"] / result["ema_60"].shift(5) - 1.0
        alignment = pd.Series("UNKNOWN", index=frame.index, dtype=object)
        valid = result["ema_200"].notna()
        alignment[valid & (c > result["ema_20"]) & (result["ema_20"] > result["ema_60"]) & (result["ema_60"] > result["ema_200"])] = "STRONG_BULL"
        alignment[valid & (result["ema_20"] > result["ema_60"]) & ~(c > result["ema_20"])] = "BULL"
        alignment[valid & (c < result["ema_20"]) & (result["ema_20"] < result["ema_60"]) & (result["ema_60"] < result["ema_200"])] = "STRONG_BEAR"
        alignment[valid & (result["ema_20"] < result["ema_60"]) & ~(c < result["ema_20"])] = "BEAR"
        alignment[valid & (alignment == "UNKNOWN")] = "MIXED"
        result["trend_alignment"] = alignment

        delta = c.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain, avg_loss = _wilder(gain, 14), _wilder(loss, 14)
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100.0 - 100.0 / (1.0 + rs)
        rsi[(avg_loss == 0) & (avg_gain > 0)] = 100.0
        rsi[(avg_loss == 0) & (avg_gain == 0)] = 50.0
        result["rsi_14"] = rsi
        ema12 = c.ewm(span=12, adjust=False, min_periods=12).mean()
        ema26 = c.ewm(span=26, adjust=False, min_periods=26).mean()
        result["macd_line_12_26"] = ema12 - ema26
        result["macd_signal_9"] = result["macd_line_12_26"].ewm(span=9, adjust=False, min_periods=9).mean()
        result["macd_histogram"] = result["macd_line_12_26"] - result["macd_signal_9"]
        result["roc_10"] = c.pct_change(10, fill_method=None) * 100.0
        result["roc_20"] = c.pct_change(20, fill_method=None) * 100.0

        previous_close = c.shift(1)
        tr = pd.concat([h - l, (h - previous_close).abs(), (l - previous_close).abs()], axis=1).max(axis=1)
        tr.iloc[0] = np.nan
        result["true_range"] = tr
        result["atr_14"] = _wilder(tr, 14)
        result["atr_pct_14"] = _pct(result["atr_14"] + c, c)
        factor = ANNUALIZATION_FACTORS[interval]
        result["realized_volatility_20"] = result["log_return_1"].rolling(20, min_periods=20).std(ddof=1) * math.sqrt(factor)
        mid = c.rolling(20, min_periods=20).mean()
        std = c.rolling(20, min_periods=20).std(ddof=0)
        upper, lower = mid + 2 * std, mid - 2 * std
        result["bollinger_mid_20"] = mid
        result["bollinger_upper_20_2"] = upper
        result["bollinger_lower_20_2"] = lower
        result["bollinger_width_pct"] = (upper - lower) / mid.replace(0, np.nan) * 100
        result["bollinger_position"] = (c - lower) / (upper - lower).replace(0, np.nan)

        for period in (5, 20, 50):
            result["volume_sma_%s" % period] = volume.rolling(period, min_periods=period).mean()
        volume_baseline = volume.shift(1).rolling(20, min_periods=20).mean()
        result["volume_ratio_20"] = volume / volume_baseline.replace(0, np.nan)
        turnover = pd.to_numeric(frame.get("turnover"), errors="coerce")
        result["turnover_sma_20"] = turnover.rolling(20, min_periods=20).mean()

        if interval != "1d":
            regular = frame.get("market_session", pd.Series("", index=frame.index)).eq("REGULAR")
            typical = (h + l + c) / 3.0
            date_key = frame["trading_date"]
            numerator = (typical * volume).where(regular).groupby(date_key).cumsum()
            denominator = volume.where(regular).groupby(date_key).cumsum()
            vwap = numerator / denominator.replace(0, np.nan)
            result["session_vwap_regular"] = vwap.where(regular)
            result["close_vs_vwap_pct"] = _pct(c, result["session_vwap_regular"]).where(regular)
        else:
            result["session_vwap_regular"] = pd.Series(np.nan, index=frame.index)
            result["close_vs_vwap_pct"] = pd.Series(np.nan, index=frame.index)

        if interval == "1d":
            result["gap_open_pct"] = o / c.shift(1).replace(0, np.nan) - 1.0
        else:
            dates = frame["trading_date"]
            daily_close = c.groupby(dates).last()
            previous_daily_close = daily_close.shift(1)
            regular_open = o.where(frame.get("market_session").eq("REGULAR")).groupby(dates).first()
            gap_map = regular_open / previous_daily_close.replace(0, np.nan) - 1.0
            result["gap_open_pct"] = dates.map(gap_map)
        bar_range = (h - l).replace(0, np.nan)
        result["body_range_ratio"] = (c - o).abs() / bar_range
        result["upper_wick_ratio"] = (h - pd.concat([o, c], axis=1).max(axis=1)) / bar_range
        result["lower_wick_ratio"] = (pd.concat([o, c], axis=1).min(axis=1) - l) / bar_range
        result["close_location_value"] = (c - l) / bar_range

        for period in (20, 60, 252):
            rolling_high = h.rolling(period, min_periods=period).max()
            result["distance_from_high_%s_pct" % period] = _pct(c, rolling_high)
            result["drawdown_from_%s_high_pct" % period] = _pct(c, rolling_high)
            if period in (20, 60):
                prior_high = h.shift(1).rolling(period, min_periods=period).max()
                result["breakout_high_%s_pct" % period] = _pct(c, prior_high)
        for period in (20, 60):
            rolling_low = l.rolling(period, min_periods=period).min()
            result["distance_from_low_%s_pct" % period] = _pct(c, rolling_low)

        self._relative_features(result, c, references)
        return result

    def _relative_features(self, result: Dict[str, pd.Series], close: pd.Series, references: Dict[str, pd.DataFrame]) -> None:
        missing = pd.Series(np.nan, index=close.index)
        for period in (5, 20, 60):
            result["relative_return_qqq_%s" % period] = missing.copy()
        for name in (
            "relative_ratio_qqq", "relative_ratio_qqq_ema20",
            "relative_ratio_vs_ema20_pct", "relative_return_soxx_20",
            "market_qqq_return_1", "market_qqq_return_5",
            "market_qqq_close_vs_ema20_pct", "market_qqq_atr_pct_14",
            "market_soxx_return_5", "market_soxx_close_vs_ema20_pct",
        ):
            result[name] = missing.copy()
        qqq = references.get("US.QQQ")
        if qqq is not None:
            ref_close = qqq["close"].astype(float).reindex(close.index)
            for period in (5, 20, 60):
                result["relative_return_qqq_%s" % period] = close.pct_change(period, fill_method=None) - ref_close.pct_change(period, fill_method=None)
            ratio = close / ref_close.replace(0, np.nan)
            ratio_ema = ratio.ewm(span=20, adjust=False, min_periods=20).mean()
            result["relative_ratio_qqq"] = ratio
            result["relative_ratio_qqq_ema20"] = ratio_ema
            result["relative_ratio_vs_ema20_pct"] = _pct(ratio, ratio_ema)
            qcalc = self._market_reference(ref_close, qqq, "US.QQQ")
            result.update(qcalc)
        soxx = references.get("US.SOXX")
        if soxx is not None:
            ref_close = soxx["close"].astype(float).reindex(close.index)
            result["relative_return_soxx_20"] = close.pct_change(20, fill_method=None) - ref_close.pct_change(20, fill_method=None)
            result.update(self._market_reference(ref_close, soxx, "US.SOXX"))

    @staticmethod
    def _market_reference(close: pd.Series, frame: pd.DataFrame, symbol: str) -> Dict[str, pd.Series]:
        prefix = "market_qqq" if symbol == "US.QQQ" else "market_soxx"
        values = {
            prefix + "_return_5": close.pct_change(5, fill_method=None),
            prefix + "_close_vs_ema20_pct": _pct(close, close.ewm(span=20, adjust=False, min_periods=20).mean()),
        }
        if symbol == "US.QQQ":
            values[prefix + "_return_1"] = close.pct_change(1, fill_method=None)
            high = frame["high"].astype(float).reindex(close.index)
            low = frame["low"].astype(float).reindex(close.index)
            tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
            values[prefix + "_atr_pct_14"] = _pct(_wilder(tr, 14) + close, close)
        return values
