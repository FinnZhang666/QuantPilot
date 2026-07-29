from app.review.config import parse_window


def validate_review_for_ai(review, minimum_window: str):
    if review.review_status != "REVIEWED":
        return "SKIPPED", "Opportunity Review尚未完成。"
    if review.return_percent is None or review.mfe_percent is None or review.mae_percent is None:
        return "INSUFFICIENT_DATA", "Review缺少有效收益、MFE或MAE。"
    try:
        if parse_window(review.review_window) < parse_window(minimum_window):
            return "SKIPPED", "Review Window小于AI分析最低窗口。"
    except (TypeError, ValueError):
        return "INSUFFICIENT_DATA", "Review Window格式无效。"
    if not review.price_path_json:
        return "INSUFFICIENT_DATA", "Review缺少价格路径。"
    return None, None
