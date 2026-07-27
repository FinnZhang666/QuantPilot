from app.strategy.constants import FEATURE_ALIASES, REQUIRED_ALIASES
from app.strategy.models import SignalEvaluation, StrategyInput
from app.strategy.scoring import score_components
from app.strategy.strategies.base import CandidateStrategy


class PullbackRestrengthStrategy(CandidateStrategy):
    name = "pullback_restrength"
    display_name = "趋势回撤后重新转强"
    version = "1.0.0"

    def evaluate(self, value: StrategyInput) -> SignalEvaluation:
        if not value.enabled:
            return SignalEvaluation(
                "SKIPPED", 0, 100, "DISABLED",
                "%s当前已停用，本策略跳过。" % value.symbol,
                risks=["已停用Ticker不会生成正式候选信号。"],
                feature_refs=value.feature_refs, components=self._empty_components(),
            )
        if value.role != "TRADING":
            return SignalEvaluation(
                "SKIPPED", 0, 100, "VALID",
                "%s不是TRADING角色，本策略跳过。" % value.symbol,
                risks=["非交易观察角色不会产生Candidate Buy。"],
                feature_refs=value.feature_refs,
                components=self._empty_components(),
            )
        required = [FEATURE_ALIASES[name] for name in REQUIRED_ALIASES]
        warmup = [name for name in required if value.feature_statuses.get(name) == "WARMUP"]
        missing = [
            name for name in required
            if value.feature_statuses.get(name) != "VALID" or value.features.get(name) is None
        ]
        if missing:
            status = "WARMUP" if warmup else "MISSING_FEATURE"
            return SignalEvaluation(
                "INSUFFICIENT_DATA", 0, max(0, 100 - len(missing) * 15), status,
                "%s核心Feature不足，无法生成候选信号。" % value.symbol,
                risks=["缺失核心Feature：" + "、".join(missing)],
                feature_refs=value.feature_refs, components=self._empty_components(),
            )
        relative_name = (
            "relative_return_soxx_20" if value.benchmark_symbol == "SOXX"
            else "relative_return_qqq_20"
        )
        components, reasons, risks, states = score_components(
            value.features, value.parameters, relative_name,
        )
        score = max(0, min(100, sum(components.values())))
        optional_missing = [
            name for name, status in value.feature_statuses.items()
            if name not in required and not name.startswith("_") and status != "VALID"
        ]
        confidence = 100 - min(60, len(optional_missing) * 8)
        if value.validation_status != "VALID":
            confidence -= 10
            risks.append("证券在线验证尚未完成")
        if value.features.get(relative_name) is None:
            confidence -= 15
        confidence = max(0, min(100, confidence))

        if not states["trend_valid"] or states["pullback_too_deep"]:
            signal_type = "CANDIDATE_EXIT"
            summary = "%s趋势结构或回撤幅度已超出模板，生成Candidate Exit风险提示。" % value.symbol
        elif states["high_risk"] and (states["relative_weak"] or components["trend_score"] < 30):
            signal_type = "CANDIDATE_REDUCE"
            summary = "%s波动风险扩大且相对强弱下降，生成Candidate Reduce风险提示。" % value.symbol
        elif (
            states["pullback_valid"] and states["recovered"] and
            states["volume_confirmed"] and states["relative_confirmed"] and
            score >= int(value.parameters["candidate_buy_threshold"])
        ):
            signal_type = "CANDIDATE_BUY"
            summary = "%s处于上升趋势正常回撤，最新闭合K线重新转强，生成Candidate Buy。" % value.symbol
        else:
            signal_type = "WATCH"
            summary = "%s尚未同时满足趋势、正常回撤和重新转强条件，继续观察。" % value.symbol
        risks.append("默认参数尚未经过历史回测优化")
        return SignalEvaluation(
            signal_type, score, confidence, "VALID", summary,
            reasons=reasons, risks=risks, feature_refs=value.feature_refs,
            components=components,
        )

    @staticmethod
    def _empty_components():
        return {
            "trend_score": 0, "pullback_score": 0, "recovery_score": 0,
            "volume_score": 0, "relative_strength_score": 0, "risk_score": 0,
        }
