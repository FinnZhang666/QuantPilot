from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from app.strategy.models import SignalEvaluation, StrategyInput
from app.strategy.strategies.base import CandidateStrategy


STRATEGY_CODE = "intraday_pyramid"
STRATEGY_NAME = "超短线顺势金字塔"
STRATEGY_VERSION = "0.1.0"

DEFAULT_PARAMETERS = {
    "supported_timeframes": ["5m", "15m"],
    "entry_score_min": 75,
    "volume_ratio_min": 1.30,
    "rsi_min": 52,
    "rsi_max": 72,
    "atr_pct_max": 3.0,
    "vwap_deviation_max_pct": 2.5,
    "close_position_min": 0.65,
    "common_stock": {
        "tranches": [0.15, 0.15, 0.15, 0.25],
        "add_profit_thresholds_pct": [2.0, 4.0, 6.0],
        "single_stop_pct": 5.0,
        "max_allocation": 0.70,
    },
    "leveraged_etf": {
        "tranches": [0.10, 0.10, 0.10, 0.20],
        "add_profit_thresholds_pct": [3.0, 6.0, 10.0],
        "single_stop_pct": 8.0,
        "max_allocation": 0.50,
    },
}


@dataclass(frozen=True)
class PyramidPositionState:
    stage: int
    current_return_pct: Decimal
    current_allocation: Decimal
    trend_confirmed: bool
    reversal_signal: bool = False
    stop_triggered: bool = False
    leveraged: bool = False


@dataclass(frozen=True)
class PyramidDecision:
    action: str
    next_stage: int
    add_allocation: Decimal
    target_allocation: Decimal
    reason: str


class IntradayPyramidStrategy(CandidateStrategy):
    name = STRATEGY_CODE
    display_name = STRATEGY_NAME
    version = STRATEGY_VERSION

    _required = (
        "ema_20", "ema_60", "ema20_slope_5", "close_vs_ema20_pct",
        "close_vs_vwap_pct", "return_1", "volume_ratio_20",
        "close_location_value", "atr_pct_14", "rsi_14",
    )

    def __init__(self, parameters=None):
        self.parameters = parameters or DEFAULT_PARAMETERS

    def evaluate(self, value: StrategyInput) -> SignalEvaluation:
        if not value.enabled or value.role != "TRADING":
            return self._result("SKIPPED", 0, 100, "DISABLED", "标的未启用超短线评估。")
        if value.timeframe not in self.parameters["supported_timeframes"]:
            return self._result(
                "SKIPPED", 0, 100, "VALID",
                "超短线策略仅评估5分钟和15分钟闭合K线。",
            )
        missing = [
            name for name in self._required
            if value.feature_statuses.get(name) != "VALID" or value.features.get(name) is None
        ]
        if missing:
            return self._result(
                "INSUFFICIENT_DATA", 0, max(0, 100 - len(missing) * 10),
                "MISSING_FEATURE", "超短线核心Feature不足。",
                risks=["缺失核心Feature：" + "、".join(missing)],
            )

        features = value.features
        p = self.parameters
        trend = (
            features["ema_20"] > features["ema_60"] and
            features["ema20_slope_5"] > 0 and
            features["close_vs_ema20_pct"] >= 0
        )
        momentum = (
            features["return_1"] > 0 and
            Decimal(str(p["rsi_min"])) <= features["rsi_14"] <= Decimal(str(p["rsi_max"]))
        )
        volume = features["volume_ratio_20"] >= Decimal(str(p["volume_ratio_min"]))
        vwap = Decimal("0") <= features["close_vs_vwap_pct"] <= Decimal(
            str(p["vwap_deviation_max_pct"])
        )
        candle = features["close_location_value"] >= Decimal(str(p["close_position_min"]))
        risk = features["atr_pct_14"] <= Decimal(str(p["atr_pct_max"]))
        components = {
            "trend_score": 30 if trend else 0,
            "momentum_score": 15 if momentum else 0,
            "volume_score": 20 if volume else 0,
            "vwap_score": 10 if vwap else 0,
            "candle_score": 10 if candle else 0,
            "risk_score": 15 if risk else 0,
        }
        score = sum(components.values())
        entry = trend and momentum and volume and vwap and candle and risk and score >= p["entry_score_min"]
        reasons = [name for name, passed in (
            ("短周期趋势向上", trend), ("动量确认", momentum), ("成交量确认", volume),
            ("价格位于VWAP上方且未过度偏离", vwap), ("收盘位置强", candle),
            ("波动风险可接受", risk),
        ) if passed]
        risks = [name for name, passed in (
            ("短周期趋势未确认", trend), ("动量未确认", momentum), ("成交量不足", volume),
            ("VWAP位置不合格", vwap), ("K线收盘偏弱", candle), ("ATR波动过高", risk),
        ) if not passed]
        risks.extend(["策略仍处于RESEARCH状态", "禁止在亏损中补仓"])
        return SignalEvaluation(
            "CANDIDATE_BUY" if entry else "WATCH", score, 100, "VALID",
            "满足超短线顺势试仓条件。" if entry else "超短线条件尚未全部满足，继续观察。",
            reasons=reasons, risks=risks, feature_refs=value.feature_refs,
            components=components,
        )

    def decide_position(self, state: PyramidPositionState) -> PyramidDecision:
        profile = self.parameters["leveraged_etf" if state.leveraged else "common_stock"]
        tranches: Sequence[float] = profile["tranches"]
        thresholds: Sequence[float] = profile["add_profit_thresholds_pct"]
        cap = Decimal(str(profile["max_allocation"]))
        if state.stop_triggered or state.reversal_signal:
            return PyramidDecision("EXIT", state.stage, Decimal("0"), Decimal("0"),
                                   "止损或反转信号触发，停止加仓并退出。")
        if state.current_return_pct <= 0:
            return PyramidDecision("HOLD", state.stage, Decimal("0"), state.current_allocation,
                                   "当前未盈利，禁止补仓。")
        if not state.trend_confirmed:
            return PyramidDecision("HOLD", state.stage, Decimal("0"), state.current_allocation,
                                   "趋势未确认，禁止加仓。")
        if state.stage >= len(thresholds):
            return PyramidDecision("HOLD", state.stage, Decimal("0"), state.current_allocation,
                                   "已完成全部加仓阶段。")
        threshold = Decimal(str(thresholds[state.stage]))
        if state.current_return_pct < threshold:
            return PyramidDecision("HOLD", state.stage, Decimal("0"), state.current_allocation,
                                   "盈利幅度尚未达到下一阶段门槛。")
        requested = Decimal(str(tranches[state.stage + 1]))
        addition = max(Decimal("0"), min(requested, cap - state.current_allocation))
        if addition == 0:
            return PyramidDecision("HOLD", state.stage, Decimal("0"), state.current_allocation,
                                   "已达到总仓位上限。")
        return PyramidDecision("ADD", state.stage + 1, addition,
                               state.current_allocation + addition, "盈利且趋势确认，允许顺势加仓。")

    @staticmethod
    def _result(signal_type, score, confidence, status, summary, risks=None):
        return SignalEvaluation(signal_type, score, confidence, status, summary,
                                risks=risks or [], components={})
