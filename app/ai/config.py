from app.ai.providers.mock_provider import MockAIProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider


def build_provider(settings):
    if settings.ai_review_provider == "mock":
        return MockAIProvider()
    return OpenAICompatibleProvider(
        base_url=settings.ai_review_base_url,
        api_key=settings.ai_review_api_key,
        model=settings.ai_review_model,
        timeout=settings.ai_review_timeout_seconds,
        prompt_version=settings.ai_review_prompt_version,
        name=settings.ai_review_provider,
    )
