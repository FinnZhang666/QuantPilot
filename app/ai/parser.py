import json
from typing import Any

from app.ai.schemas import AIReviewResponse


def parse_ai_response(value: Any) -> AIReviewResponse:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("AI返回内容不是合法JSON。") from exc
    if not isinstance(value, dict):
        raise ValueError("AI返回内容必须是JSON对象。")
    return AIReviewResponse.model_validate(value)
