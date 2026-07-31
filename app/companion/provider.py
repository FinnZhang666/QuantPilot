from typing import Protocol

from app.companion.schemas import CompanionContext, ProviderResult
from app.companion.templates import CompanionPromptTemplate


class CompanionProvider(Protocol):
    name: str
    model: str

    def generate(
        self, context: CompanionContext, template: CompanionPromptTemplate,
    ) -> ProviderResult:
        ...


class ExternalCompanionProvider:
    name = "external"

    def __init__(self, model: str):
        self.model = model

    def generate(self, context, template):
        raise RuntimeError("External AI Companion Adapter尚未在macOS环境启用或联调。")


class GeminiCompanionProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float,
                 max_output_tokens: int, transport=None):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.transport = transport

    def generate(self, context, template):
        if not self.api_key:
            raise RuntimeError("Gemini API Key未配置，Provider已安全禁用。")
        if self.transport is None:
            raise RuntimeError("Gemini网络Transport未启用；本Sprint不执行真实网络调用。")
        try:
            value = self.transport(
                context=context.model_dump(), template=template,
                api_key=self.api_key, model=self.model, timeout=self.timeout,
                max_output_tokens=self.max_output_tokens,
            )
        except TimeoutError:
            raise RuntimeError("Gemini请求超时。")
        except Exception as exc:
            if getattr(exc, "status_code", None) == 429:
                raise RuntimeError("Gemini请求受到限流。")
            raise RuntimeError("Gemini Provider请求失败。")
        if value in (None, "", {}):
            raise ValueError("Gemini返回空响应。")
        if isinstance(value, dict) and "response" in value:
            response = value["response"]
            request_id = value.get("request_id")
            token_input = value.get("token_input")
            token_output = value.get("token_output")
        else:
            response, request_id, token_input, token_output = value, None, None, None
        return ProviderResult(
            response=response, provider=self.name, model=self.model,
            request_id=request_id, token_input=token_input, token_output=token_output,
        )
