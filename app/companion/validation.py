import json
import re

from pydantic import ValidationError

from app.companion.schemas import CompanionResponse, DISCLAIMER_ZH


BANNED_KEYS = {
    "recommended_entry", "recommended_stop", "recommended_target", "new_signal",
    "trade_action", "order_request", "guaranteed_return", "buy_price", "sell_price",
}
BANNED_PHRASES = (
    "一定会上涨", "必然盈利", "应立即买入", "保证达到目标", "无风险", "稳赚", "必须持有",
    "建议入场价", "建议买入价", "建议止损价", "建议目标价",
)
SECRET_PATTERN = re.compile(r"(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|\d{8,12}:[A-Za-z0-9_-]{20,})", re.I)


class CompanionResponseValidator:
    def validate(self, value) -> CompanionResponse:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                raise ValueError("Provider返回了非JSON响应。")
        if not isinstance(value, dict):
            raise ValueError("Provider响应必须是JSON对象。")
        self._scan(value)
        try:
            response = CompanionResponse.model_validate(value)
        except ValidationError as exc:
            raise ValueError("Provider响应不符合Companion Schema：%s" % str(exc)[:300])
        if response.disclaimer != DISCLAIMER_ZH:
            raise ValueError("Provider响应缺少固定风险声明。")
        return response

    def _scan(self, value):
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in BANNED_KEYS:
                    raise ValueError("Provider响应包含禁止字段：%s" % key)
                self._scan(item)
        elif isinstance(value, list):
            if len(value) > 100:
                raise ValueError("Provider响应数组过长。")
            for item in value:
                self._scan(item)
        elif isinstance(value, str):
            if len(value) > 5000:
                raise ValueError("Provider响应文本过长。")
            if SECRET_PATTERN.search(value):
                raise ValueError("Provider响应疑似包含敏感信息。")
            if any(phrase in value for phrase in BANNED_PHRASES):
                raise ValueError("Provider响应包含禁止的确定性交易表述。")


def safe_error(value) -> str:
    return SECRET_PATTERN.sub("******", str(value))[:500]
