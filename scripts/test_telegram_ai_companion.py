"""Minimal real Gemini smoke test for Telegram AI Companion.

The script skips without a configured key and never prints the key, prompt, or full
model response. It is not part of the default test suite.
"""

import time

from app.core.config import get_settings
from app.telegram_runtime.ai import GeminiAdapter


def main():
    settings = get_settings()
    if not (settings.ai_companion_api_key or settings.gemini_api_key):
        print({"status": "SKIPPED", "reason": "Gemini API key not configured"})
        return 0
    smoke_settings = settings.model_copy(update={"ai_companion_max_output_tokens": 64})
    started = time.perf_counter()
    try:
        result = GeminiAdapter(smoke_settings).generate(
            "Reply with one short sentence confirming the connection. Do not include numbers."
        )
        print({
            "status": "SUCCESS", "provider": "gemini", "model": result["model"],
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
            "text_output": bool(result["text"]),
        })
        return 0
    except Exception as exc:
        print({
            "status": "FAILED", "provider": "gemini",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error_code": type(exc).__name__, "error": "redacted",
        })
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
