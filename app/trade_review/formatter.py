def format_trade_review(review, symbol: str) -> str:
    return (
        "【Trade Review】\nSymbol: %s\nType: %s\nResult: %s\n"
        "MFE: %s%%\nMAE: %s%%\nHolding: %s minutes\n"
        "Target Hit: %s\nStop Hit: %s\n\n"
        "Review仅为历史客观复盘，不构成交易建议。"
    ) % (
        symbol, review.review_type, review.result, review.mfe, review.mae,
        review.holding_minutes, review.target_hit, review.stop_hit,
    )
