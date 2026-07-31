TEXT = {
    "zh-CN": {
        "title": "📈 {symbol}", "snapshot": "市场快照", "price": "最新价格",
        "candidate": "候选信号", "holding": "持仓", "plan": "交易计划",
        "review": "复盘", "ai": "AI 解读", "none": "暂无", "yes": "是",
        "no": "否", "view_snapshot": "查看快照", "view_ai": "查看 AI",
        "view_holding": "查看持仓", "view_plan": "查看计划",
        "view_review": "查看复盘", "portfolio": "投资组合",
        "disclaimer": "以上内容仅展示系统已有数据，不构成新的交易信号。",
        "empty": "暂无可展示的数据。",
        "submit_feedback": "提交建议", "feedback_bug": "🐞 Bug",
        "feedback_feature": "💡 功能建议", "feedback_strategy": "📈 新策略",
        "feedback_market": "🌍 新市场", "feedback_other": "⭐ 其它",
        "helpful": "👍 有帮助", "not_helpful": "👎 没帮助",
    },
    "en-US": {
        "title": "📈 {symbol}", "snapshot": "Market Snapshot", "price": "Latest Price",
        "candidate": "Candidate", "holding": "Holding", "plan": "Trade Plan",
        "review": "Review", "ai": "AI Explanation", "none": "Not Available",
        "yes": "YES", "no": "NO", "view_snapshot": "View Snapshot",
        "view_ai": "View AI", "view_holding": "View Holding",
        "view_plan": "View Trade Plan", "view_review": "View Review",
        "portfolio": "Portfolio",
        "disclaimer": "This only presents existing system data and is not a new trading signal.",
        "empty": "No data available.",
        "submit_feedback": "Submit Feedback", "feedback_bug": "🐞 Bug",
        "feedback_feature": "💡 Feature Idea", "feedback_strategy": "📈 New Strategy",
        "feedback_market": "🌍 New Market", "feedback_other": "⭐ Other",
        "helpful": "👍 Helpful", "not_helpful": "👎 Not Helpful",
    },
}


def translations(language):
    if language not in TEXT:
        raise ValueError("language必须是zh-CN或en-US。")
    return TEXT[language]
