import json

import httpx

from app.ai.parser import parse_ai_response
from app.ai.prompts import prompt_for
from app.ai.schemas import AIReviewRequest, ProviderResult


class OpenAICompatibleProvider:
    def __init__(
        self, base_url: str, api_key: str, model: str, timeout: float,
        prompt_version: str = "v1", name: str = "openai_compatible",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.prompt_version = prompt_version
        self.name = name

    def analyze_review(self, request: AIReviewRequest) -> ProviderResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt_for(self.prompt_version)},
                {"role": "user", "content": request.model_dump_json()},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        response = httpx.post(
            self.base_url + "/chat/completions", headers=headers, json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        raw = response.json()
        content = raw["choices"][0]["message"]["content"]
        parsed = parse_ai_response(content)
        usage = raw.get("usage") or {}
        return ProviderResult(
            response=parsed, raw_response=raw,
            token_input=usage.get("prompt_tokens"),
            token_output=usage.get("completion_tokens"),
        )

    def request_preview(self, request: AIReviewRequest):
        """Safe request preview for tests; never contains the API key."""
        return {
            "url": self.base_url + "/chat/completions", "model": self.model,
            "prompt_version": self.prompt_version,
            "input": json.loads(request.model_dump_json()),
        }
