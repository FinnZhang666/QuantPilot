import re
from decimal import Decimal, InvalidOperation


MAX_MESSAGE_LENGTH = 4000


def escape_markdown(value, missing="未记录"):
    text = missing if value is None or value == "" else str(value)
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)


def decimal_text(value, missing="未记录", markdown_safe=False):
    if value is None or value == "":
        return missing
    try:
        text = format(Decimal(str(value)).normalize(), "f")
        return escape_markdown(text, missing) if markdown_safe else text
    except InvalidOperation:
        return escape_markdown(value, missing) if markdown_safe else str(value)


def limit_message(text, ending=None, maximum=MAX_MESSAGE_LENGTH):
    if len(text) <= maximum:
        return text
    if not ending:
        return text[:maximum - 1] + "…"
    suffix = "\n\n" + ending
    return text[:maximum - len(suffix) - 1] + "…" + suffix
