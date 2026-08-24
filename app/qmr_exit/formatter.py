import html

from app.telegram_runtime.renderer import TelegramMessage


STATE_ZH = {"HOLD": "持有", "WATCH": "观察", "PROTECT": "利润保护", "REDUCE": "减仓", "EXIT": "退出"}
FLOW_ZH = {"ACCUMULATION": "疑似吸筹", "DISTRIBUTION": "疑似派发",
           "BROAD_BUYING": "全面买入", "BROAD_SELLING": "全面卖出",
           "POSSIBLE_ABSORPTION": "疑似承接", "NEUTRAL": "无明显结构"}


def qmr_exit_message(evaluation, language="zh-CN"):
    zh = language == "zh-CN"
    state = STATE_ZH.get(evaluation.state, evaluation.state) if zh else evaluation.state.title()
    action = "减仓 %s%%" % round(float(evaluation.reduce_ratio) * 100) if evaluation.reduce_ratio else state
    components = (("Capital Flow", evaluation.capital_flow_risk, 25),
                  ("Trend", evaluation.trend_risk, 20),
                  ("Relative Strength", evaluation.relative_strength_risk, 15),
                  ("Sector Rotation", evaluation.sector_rotation_risk, 15),
                  ("Profit Protection", evaluation.profit_protection_risk, 15),
                  ("Exhaustion", evaluation.exhaustion_risk, 10))
    lines = ["【QMR EXIT ALERT】", "", "<b>%s</b>" % html.escape(evaluation.symbol),
             ("状态：%s" if zh else "Status: %s") % state,
             "Exit Risk: %.1f/100" % float(evaluation.exit_risk_score), "",
             "Current: $%s" % evaluation.current_price, "Entry: $%s" % evaluation.entry_price,
             "Highest Since Entry: $%s" % evaluation.highest_price,
             "Current P/L: %+.2f%%" % float(evaluation.current_return),
             "Max P/L: %+.2f%%" % float(evaluation.max_return),
             "Giveback: %.2f%%" % float(evaluation.profit_giveback), ""]
    lines.extend("%s Risk: %s/%s" % (name, "数据不足" if value is None and zh else
                 ("Unavailable" if value is None else "%.1f" % float(value)), maximum)
                 for name, value, maximum in components)
    regime = FLOW_ZH.get(evaluation.money_flow_regime, evaluation.money_flow_regime) if zh else evaluation.money_flow_regime
    lines += ["", ("💰 资金结构：%s" if zh else "💰 Money flow structure: %s") % regime]
    if evaluation.reasons_json:
        lines += ["", "关键原因：" if zh else "Key reasons:"] + ["- " + html.escape(str(x)) for x in evaluation.reasons_json[:8]]
    lines += ["", ("建议：%s" if zh else "Suggested state: %s") % action,
              "仅为QMR策略风险提示，不会执行真实交易。" if zh else
              "QMR risk guidance only; no real trade is executed."]
    return TelegramMessage("\n".join(lines))
