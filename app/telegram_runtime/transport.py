"""Small injectable Telegram Bot API transport.

Production uses httpx; automated tests inject a fake transport and never send a
message to Telegram.
"""

import json
import time
from typing import Callable, Dict, Optional

import httpx


class TelegramTransportError(RuntimeError):
    pass


class TelegramBotTransport:
    def __init__(
        self, timeout_seconds: float = 10.0,
        max_retries: int = 2,
        sender: Optional[Callable[[str, str, Dict[str, object]], Dict[str, object]]] = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sender = sender or self._send_http

    def call(self, token: str, method: str, payload: Optional[Dict[str, object]] = None):
        if not token:
            raise TelegramTransportError("Telegram bot token is not configured.")
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.sender(token, method, payload or {})
                if response.get("ok"):
                    return response
                code = int(response.get("error_code") or 0)
                if code not in {429} and code < 500:
                    raise TelegramTransportError("Telegram request failed with code %s." % (code or "unknown"))
                last_error = TelegramTransportError("Telegram retryable request failure.")
            except TelegramTransportError:
                raise
            except Exception as exc:
                last_error = exc
            if attempt < self.max_retries:
                time.sleep(min(0.25 * (2 ** attempt), 2.0))
        raise TelegramTransportError("Telegram request failed; details are redacted.") from last_error

    def send_message(self, token: str, payload: Dict[str, object]):
        return self.call(token, "sendMessage", payload)

    def get_updates(self, token: str, offset: int, timeout: int):
        return self.call(token, "getUpdates", {
            "offset": offset, "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        })

    def answer_callback(self, token: str, callback_query_id: str):
        return self.call(token, "answerCallbackQuery", {"callback_query_id": callback_query_id})

    def _send_http(self, token: str, method: str, payload: Dict[str, object]):
        url = "https://api.telegram.org/bot%s/%s" % (token, method)
        encoded = {
            key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
            for key, value in payload.items()
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, data=encoded)
        return response.json()
