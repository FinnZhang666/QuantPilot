from datetime import datetime, timezone
from typing import Dict

from app.market_regime.models import MarketRegimeResult


def clamp(value: float) -> int:
    return max(0, min(100, int(round(value))))


class MarketRegimeScorer:
    """Pure deterministic scorer. Positive scores describe risk-on conditions."""

    REQUIRED = (
        "close_vs_ema20_pct", "ema20_vs_ema60_pct", "ema20_slope_5",
        "return_5", "rsi_14", "atr_pct_14",
    )

    def __init__(self, config: Dict[str, object]):
        self.config = config

    def score(self, snapshots: Dict[str, Dict[str, object]], bar_time=None) -> MarketRegimeResult:
        qqq = snapshots.get("QQQ") or snapshots.get("US.QQQ") or {}
        missing = [name for name in self.REQUIRED if qqq.get(name) is None]
        when = bar_time or qqq.get("_timestamp") or datetime.now(timezone.utc)
        if missing:
            return MarketRegimeResult(
                "UNKNOWN", 50, None, 50, 50, 50, 50, 50,
                max(0, 50 - len(missing) * 8), when, snapshots,
                [], ["缺少必要特征：" + "、".join(missing)], False,
                str(self.config.get("version", "1.0.0")),
            )
        trend = 50
        trend += 15 if float(qqq["close_vs_ema20_pct"]) > 0 else -15
        trend += 20 if float(qqq["ema20_vs_ema60_pct"]) > 0 else -20
        trend += 15 if float(qqq["ema20_slope_5"]) > 0 else -15
        momentum = 50
        momentum += 20 if float(qqq["return_5"]) > 0 else -20
        rsi = float(qqq["rsi_14"])
        momentum += 10 if 50 <= rsi <= 70 else (-10 if rsi < 45 else 0)
        atr = float(qqq["atr_pct_14"])
        high_atr = float(self.config["thresholds"]["high_atr_pct"])
        volatility = 70 if atr <= high_atr else max(10, 70 - (atr - high_atr) * 10)
        soxx = snapshots.get("SOXX") or snapshots.get("US.SOXX") or {}
        soxs = snapshots.get("SOXS") or snapshots.get("US.SOXS") or {}
        risk = 60
        reasons = []
        risks = []
        if soxx.get("return_5") is not None:
            aligned = (float(soxx["return_5"]) >= 0) == (float(qqq["return_5"]) >= 0)
            risk += 10 if aligned else -15
            (reasons if aligned else risks).append("QQQ与SOXX方向%s" % ("同步" if aligned else "不同步"))
        else:
            risks.append("SOXX参考特征缺失")
        if soxs.get("return_5") is not None and float(soxs["return_5"]) > 0:
            risk -= 15
            risks.append("SOXS风险参考正在转强")
        else:
            reasons.append("SOXS未显示明显风险转强")
        trend, momentum, volatility, risk = map(clamp, (trend, momentum, volatility, risk))
        weights = self.config["weights"]
        composite = (
            trend * float(weights["trend"]) + momentum * float(weights["momentum"]) +
            volatility * float(weights["volatility"]) + risk * float(weights["risk"])
        )
        thresholds = self.config["thresholds"]
        if composite >= float(thresholds["strong_bull"]):
            regime = "STRONG_BULL"
        elif composite >= float(thresholds["bull"]):
            regime = "BULL"
        elif composite <= float(thresholds["strong_bear"]):
            regime = "STRONG_BEAR"
        elif composite <= float(thresholds["bear"]):
            regime = "BEAR"
        else:
            regime = "NEUTRAL"
        long_bias = clamp(30 + composite * 0.6)
        short_bias = clamp(90 - composite * 0.6)
        reasons.extend([
            "趋势评分 %s" % trend, "动量评分 %s" % momentum,
            "市场状态由多指标确定性评分生成",
        ])
        if atr > high_atr:
            risks.append("ATR百分比较高")
        return MarketRegimeResult(
            regime, trend, None, momentum, volatility, risk,
            long_bias, short_bias, clamp(80 - len(risks) * 8),
            when, snapshots, reasons, risks, True,
            str(self.config.get("version", "1.0.0")),
        )
