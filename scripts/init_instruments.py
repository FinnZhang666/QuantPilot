#!/usr/bin/env python3
import argparse

from app.core.config import get_settings
from app.data.providers.moomoo import MoomooConnectionManager
from app.database.session import get_session_factory
from app.historical.instruments import InstrumentService
from app.historical.validator import MoomooInstrumentValidator


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化并验证历史行情标的")
    parser.add_argument("--skip-validation", action="store_true", help="只写入待确认标的")
    args = parser.parse_args()
    settings = get_settings()
    with get_session_factory()() as db:
        service = InstrumentService(db)
        rows = service.initialize_defaults()
        if not args.skip_validation:
            manager = MoomooConnectionManager(
                settings.moomoo_opend_host,
                settings.moomoo_opend_port,
                settings.moomoo_connection_timeout_seconds,
            )
            MoomooInstrumentValidator(manager).validate(service, rows)
        print("历史行情标的初始化")
        for row in rows:
            label = "成功" if row.is_supported else "待确认"
            print(f"- {row.alias or row.symbol}：{label}，{row.support_message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
