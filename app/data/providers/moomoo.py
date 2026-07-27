import socket
from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class ConnectionReport:
    opend_reachable: bool = False
    quote_api_available: bool = False
    us_market_permission: bool = False
    paper_trading_account_found: bool = False
    live_account_found: bool = False
    live_trading_enabled: bool = False
    detail: str = ""

    def safe_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MoomooConnectionChecker:
    """Read-only OpenD connectivity and permission inspection."""

    def __init__(self, host: str, port: int, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def is_reachable(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout):
                return True
        except OSError:
            return False

    def check_quote_connection(self) -> bool:
        return self.is_reachable()

    def check_trade_connection(self) -> bool:
        return self.is_reachable()

    def list_accounts(self) -> Dict[str, bool]:
        # Account enumeration requires the optional moomoo package and an authenticated OpenD.
        return {"paper_found": False, "live_found": False}

    def inspect_permissions(self) -> Dict[str, bool]:
        return {"us_market": False}

    def check_all(self) -> ConnectionReport:
        reachable = self.is_reachable()
        report = ConnectionReport(opend_reachable=reachable)
        if not reachable:
            report.detail = "OpenD is not reachable; no API login or account data was accessed."
            return report
        try:
            from moomoo import OpenQuoteContext, OpenSecTradeContext, TrdEnv, TrdMarket
        except ImportError:
            report.detail = "OpenD is reachable; install the optional 'moomoo' dependency for API inspection."
            return report

        quote_ctx = None
        trade_ctx = None
        try:
            quote_ctx = OpenQuoteContext(host=self.host, port=self.port)
            report.quote_api_available = True
            ret, data = quote_ctx.get_global_state()
            report.us_market_permission = ret == 0 and data is not None
        except Exception as exc:
            report.detail = "Quote inspection failed: " + type(exc).__name__
        finally:
            if quote_ctx:
                quote_ctx.close()
        try:
            trade_ctx = OpenSecTradeContext(
                filter_trdmarket=TrdMarket.US, host=self.host, port=self.port
            )
            ret, accounts = trade_ctx.get_acc_list()
            if ret == 0:
                environments = {str(value) for value in accounts.get("trd_env", [])}
                report.paper_trading_account_found = any("SIMULATE" in value for value in environments)
                report.live_account_found = any("REAL" in value for value in environments)
        except Exception as exc:
            if not report.detail:
                report.detail = "Trade inspection failed: " + type(exc).__name__
        finally:
            if trade_ctx:
                trade_ctx.close()
        report.live_trading_enabled = False
        return report
