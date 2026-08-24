import html
from zoneinfo import ZoneInfo

from app.telegram_runtime.renderer import TelegramMessage, callback_keyboard


LEVEL_ZH = {"EARLY_ENTRY": "早期介入", "CONFIRMED_ENTRY": "确认介入", "STRONG_ENTRY": "强确认"}
SESSION_ZH = {"OVERNIGHT": "【夜盘】", "PRE_MARKET": "【盘前】", "AFTER_HOURS": "【盘后】"}


def qmr_signal_message(signal, language="zh-CN", failed=False):
    zh = language == "zh-CN"
    if failed:
        title = "【QMR｜修复失败】" if zh else "【QMR | Recovery Failed】"
        reasons = signal.invalidation_reason_json or []
        lines = [title, "", "<b>%s</b>" % html.escape(signal.symbol),
            ("原信号：%s" % LEVEL_ZH.get(signal.signal_level, signal.signal_level)) if zh else
            "Original signal: %s" % signal.signal_level,
            ("原信号价：$%s" % signal.signal_price),
            ("当前：$%s" % (signal.latest_price or "数据不足")),
            ("状态：修复结构失效" if zh else "Status: recovery structure invalidated")]
        lines += [("✗ " + html.escape(reason)) for reason in reasons]
        lines += ["", "Signal", "#" + signal.signal_id]
        return TelegramMessage("\n".join(lines))
    research = signal.signal_mode == "PAPER"
    title = "【研究信号｜QMR】" if research and zh else ("【QMR Research Signal】" if research else "【QMR｜优质错杀修复】")
    session = SESSION_ZH.get((signal.trading_session or "").upper(), "") if zh else (
        "[%s]" % signal.trading_session.replace("_", " ").title() if signal.trading_session and signal.trading_session != "REGULAR" else "")
    level = LEVEL_ZH.get(signal.signal_level, signal.signal_level) if zh else signal.signal_level.replace("_", " ").title()
    lines = [title + session, "", "<b>%s</b>" % html.escape(signal.symbol),
        ("状态：%s" % level) if zh else "Status: %s" % level,
        ("买入评分：%s / 100（%s）" % (signal.buy_score, signal.buy_grade)) if zh else
        ("Buy score: %s / 100 (%s)" % (signal.buy_score, signal.buy_grade)),
        ("当前价：$%s" % signal.signal_price) if zh else ("Reference price: $%s" % signal.signal_price),
        ("风险：%s｜时段置信度：%s" % (signal.chase_risk_level, signal.session_confidence)) if zh else
        ("Risk: %s | Session confidence: %s" % (signal.chase_risk_level, signal.session_confidence)), "",
        "Quality %s｜Mispricing %s｜Recovery %s" % (
            signal.quality_score, signal.mispricing_score, signal.recovery_score)]
    reasons = (signal.signal_snapshot_json or {}).get("reasons", [])
    if reasons:
        lines += ["", "为什么出现信号：" if zh else "Why this signal:"] + ["✓ " + html.escape(str(value)) for value in reasons[:8]]
    stats = signal.similar_statistics_json or {}
    if stats.get("sample_count"):
        lines += ["", "历史相似信号：" if zh else "Similar historical signals:",
            (("样本：%s" if zh else "Samples: %s") % stats["sample_count"]),
            "5D %s｜10D %s" % (_pct(stats.get("average_return_5d"), zh), _pct(stats.get("average_return_10d"), zh)),
            "MAE %s｜MFE %s" % (_pct(stats.get("mae"), zh), _pct(stats.get("mfe"), zh))]
        if stats["sample_count"] < 30: lines.append("⚠ 历史样本较少，统计可信度有限" if zh else "⚠ Small sample; statistics have limited confidence")
        elif stats["sample_count"] < 100: lines.append("历史样本：初步" if zh else "Historical evidence: preliminary")
    else:
        lines += ["", "历史统计暂不可用" if zh else "Historical statistics are currently unavailable"]
    lines += ["", "Signal", "#" + signal.signal_id,
        "以上为策略信号，不代表保证盈利。" if zh else "This strategy signal does not guarantee profit."]
    buttons = callback_keyboard([[
        ("👍 有帮助" if zh else "👍 Helpful", "qmr-feedback:%s:helpful" % signal.signal_id),
        ("👎 没帮助" if zh else "👎 Not Helpful", "qmr-feedback:%s:not-helpful" % signal.signal_id),
    ], [("💰 我买了" if zh else "💰 I Bought", "qmr-bought:%s" % signal.signal_id)]])
    return TelegramMessage("\n".join(lines), buttons)


def qmr_status_message(signal, performances, language="zh-CN"):
    zh = language == "zh-CN"; latest = performances[-1] if performances else None
    at = signal.signal_time.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York")) if signal.signal_time.tzinfo is None else signal.signal_time.astimezone(ZoneInfo("America/New_York"))
    lines = ["<b>%s</b>" % html.escape(signal.symbol), "Signal #%s" % signal.signal_id,
        ("信号时间：%s ET" % at.strftime("%Y-%m-%d %H:%M")), "Signal price: $%s" % signal.signal_price,
        ("当前状态：%s" if zh else "Status: %s") % signal.status]
    if latest:
        lines += ["Return: %s" % _pct(latest.return_pct, zh), "MFE: %s" % _pct(latest.mfe_pct, zh), "MAE: %s" % _pct(latest.mae_pct, zh)]
    return TelegramMessage("\n".join(lines))


def qmr_user_statistics_message(stats, language="zh-CN"):
    zh = language == "zh-CN"
    rate = "—" if stats["win_rate"] is None else "%.1f%%" % (stats["win_rate"] * 100)
    average = "—" if stats["average_return"] is None else "%+.2f%%" % stats["average_return"]
    best = "—" if stats["best"] is None else "%s %+.2f%%" % stats["best"]
    worst = "—" if stats["worst"] is None else "%s %+.2f%%" % stats["worst"]
    if zh:
        text = ("<b>我的 QMR</b>\n\n跟随次数：%s\n已完成：%s\n盈利：%s\n亏损：%s\n"
                "胜率：%s\n平均收益：%s\n最佳：%s\n最差：%s" %
                (stats["follow_count"], stats["completed"], stats["wins"], stats["losses"],
                 rate, average, best, worst))
    else:
        text = ("<b>My QMR</b>\n\nFollowed: %s\nCompleted: %s\nWins: %s\nLosses: %s\n"
                "Win rate: %s\nAverage return: %s\nBest: %s\nWorst: %s" %
                (stats["follow_count"], stats["completed"], stats["wins"], stats["losses"],
                 rate, average, best, worst))
    return TelegramMessage(text)


def _pct(value, zh=True):
    return ("数据不足" if zh else "Unavailable") if value is None else "%+.2f%%" % float(value)
