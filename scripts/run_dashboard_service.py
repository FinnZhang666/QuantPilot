"""Production-style Dashboard/API entry point with background runtimes disabled."""

import os

import uvicorn

from app.core.config import get_settings


def main():
    os.environ["RUNTIME_MANAGER_ENABLED"] = "false"
    os.environ["PAPER_TRADING_AUTOSTART"] = "false"
    os.environ["TELEGRAM_RUNTIME_AUTOSTART"] = "false"
    settings = get_settings()
    uvicorn.run(
        "app.main:app", host=settings.app_host, port=settings.app_port,
        workers=1, reload=False,
    )


if __name__ == "__main__":
    main()
