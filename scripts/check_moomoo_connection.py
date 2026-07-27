#!/usr/bin/env python3
from app.core.config import get_settings
from app.data.providers.moomoo import MoomooConnectionChecker


def yn(value: bool) -> str:
    return "YES" if value else "NO"


def main() -> None:
    settings = get_settings()
    report = MoomooConnectionChecker(
        settings.moomoo_opend_host, settings.moomoo_opend_port
    ).check_all()
    print(f"OpenD reachable: {yn(report.opend_reachable)}")
    print(f"Quote API available: {yn(report.quote_api_available)}")
    print(f"US market permission: {yn(report.us_market_permission)}")
    print(f"Paper trading account found: {yn(report.paper_trading_account_found)}")
    print(f"Live account found: {yn(report.live_account_found)}")
    print("Live trading enabled: NO")
    if report.detail:
        print(f"Detail: {report.detail}")


if __name__ == "__main__":
    main()
