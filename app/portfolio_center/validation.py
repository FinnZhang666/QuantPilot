import re
from decimal import Decimal, InvalidOperation

from app.portfolio_center.errors import ValidationError


MARKETS = {"US", "HK", "CN"}
CURRENCIES = {"USD", "HKD", "CNY"}
DIRECTIONS = {"LONG", "SHORT"}
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,31}$")


def normalized_name(value: str) -> str:
    name = " ".join((value or "").strip().split())
    if not name:
        raise ValidationError("Portfolio名称不能为空。")
    if len(name) > 128:
        raise ValidationError("Portfolio名称过长。")
    return name.casefold()


def clean_name(value: str) -> str:
    normalized_name(value)
    return " ".join(value.strip().split())


def clean_user_id(value: str) -> str:
    user_id = (value or "").strip()
    if not user_id:
        raise ValidationError("用户标识不能为空。")
    return user_id


def clean_symbol(value: str) -> str:
    symbol = (value or "").strip().upper()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValidationError("证券代码格式无效。")
    return symbol


def clean_market(value: str) -> str:
    market = (value or "").strip().upper()
    if market not in MARKETS:
        raise ValidationError("市场仅支持US、HK或CN。")
    return market


def clean_currency(value: str) -> str:
    currency = (value or "").strip().upper()
    if currency not in CURRENCIES:
        raise ValidationError("币种仅支持USD、HKD或CNY。")
    return currency


def clean_direction(value: str) -> str:
    direction = (value or "").strip().upper()
    if direction not in DIRECTIONS:
        raise ValidationError("方向仅支持LONG或SHORT。")
    return direction


def decimal_value(value, field: str, allow_zero: bool) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("%s必须是有效Decimal。" % field)
    if not result.is_finite() or result < 0 or (not allow_zero and result == 0):
        operator = ">= 0" if allow_zero else "> 0"
        raise ValidationError("%s必须%s。" % (field, operator))
    return result
