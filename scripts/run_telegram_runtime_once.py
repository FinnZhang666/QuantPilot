"""Run one controlled Telegram polling cycle and print only safe status fields."""

from app.core.config import get_settings
from app.telegram_runtime.runtime import get_telegram_runtime


def main():
    result = get_telegram_runtime(get_settings()).run_once(poll_timeout=0)
    print(result)


if __name__ == "__main__":
    main()
