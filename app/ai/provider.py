from typing import Protocol

from app.ai.schemas import AIReviewRequest, ProviderResult


class AIProvider(Protocol):
    name: str
    model: str

    def analyze_review(self, request: AIReviewRequest) -> ProviderResult:
        ...
