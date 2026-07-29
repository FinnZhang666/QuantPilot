from app.ai.config import build_provider


class AIReviewAnalyst:
    """Provider-only analyst facade. It never accesses the database."""

    def __init__(self, settings):
        self.provider = build_provider(settings)

    def analyze(self, request):
        return self.provider.analyze_review(request)
