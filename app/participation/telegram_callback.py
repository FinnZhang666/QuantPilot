from typing import Dict


def participation_callback_data(action: str, trade_plan_id: str) -> str:
    normalized = action.strip().lower()
    if normalized not in ("open", "ignore", "watch"):
        raise ValueError("不支持的Participation Callback动作。")
    value = "participation:%s:%s" % (normalized, trade_plan_id.strip())
    if not trade_plan_id.strip() or len(value.encode("utf-8")) > 64:
        raise ValueError("Participation Callback数据无效或超过Telegram限制。")
    return value


def trade_plan_participation_callbacks(trade_plan_id: str) -> Dict[str, str]:
    return {
        "我买入": participation_callback_data("open", trade_plan_id),
        "忽略": participation_callback_data("ignore", trade_plan_id),
        "加入关注": participation_callback_data("watch", trade_plan_id),
    }
