from app.review.service import OpportunityReviewService


def run_reviews(db, settings=None, limit=None, symbol=None):
    return OpportunityReviewService(db, settings).run(limit=limit, symbol=symbol)
