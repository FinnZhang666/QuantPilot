def format_companion_analysis(analysis, symbol: str, lifecycle: str) -> str:
    if analysis.status != "COMPLETED" or not analysis.structured_response_json:
        raise ValueError("只能格式化已完成并通过校验的AI Companion结果。")
    value = analysis.structured_response_json
    text = (
        "【AI Companion】\n标的：%s\n当前阶段：%s\n系统计划摘要：%s\n"
        "AI解读：%s\n风险提示：%s\n积极因素：%s\n谨慎因素：%s\n"
        "缺失数据：%s\n说明：%s\n\n"
        "以上内容仅解释系统已有计划，不构成新的交易信号。"
    ) % (
        symbol, lifecycle, value["summary"], value["plan_interpretation"],
        "；".join(value["risk_notes"]) or "暂无",
        "；".join(value["positive_factors"]) or "暂无",
        "；".join(value["caution_factors"]) or "暂无",
        "；".join(value["missing_data_notes"]) or "无",
        value["disclaimer"],
    )
    if len(text) <= 4000:
        return text
    ending = "\n\n以上内容仅解释系统已有计划，不构成新的交易信号。"
    return text[:4000 - len(ending)] + ending
