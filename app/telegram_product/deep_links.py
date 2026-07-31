from urllib.parse import quote


def deep_link(kind, target_id):
    allowed = {"symbol", "trade_plan", "holding", "review", "ai", "portfolio"}
    if kind not in allowed:
        raise ValueError("不支持的Telegram Deep Link类型。")
    return "trade-companion://%s/%s" % (kind, quote(str(target_id), safe=""))
