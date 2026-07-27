import json
import socket

from app.data.providers.moomoo import (
    MoomooCapabilityReport,
    MoomooConnectionManager,
    mask_account_id,
)


class FakeSocket:
    def close(self):
        pass


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orientation):
        assert orientation == "records"
        return self.rows

    def get(self, key, default=None):
        if self.rows and isinstance(self.rows[0], dict):
            return self.rows[0].get(key, default)
        return default


class FakeQuoteContext:
    def __init__(self, permission=True):
        self.closed = False
        self.permission = permission

    def close(self):
        self.closed = True

    def get_global_state(self):
        return 0, {"server_ver": "9.6.1"}

    def get_market_state(self, symbols):
        return 0, FakeFrame([])

    def get_market_snapshot(self, symbols):
        if self.permission:
            return 0, FakeFrame([{"code": symbols[0]}])
        return -1, "No quote permission"

    def request_history_kline(self, symbol, max_count=1):
        if self.permission:
            return 0, FakeFrame([{"code": symbol}]), None
        return -1, "No quote permission", None


class FakeTradeContext:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def get_acc_list(self):
        return 0, FakeFrame(
            [
                {"acc_id": "1234564821", "trd_env": "SIMULATE", "trd_market": "US"},
                {"acc_id": "9876541000", "trd_env": "REAL", "trd_market": "US"},
            ]
        )


class FakeSdk:
    RET_OK = 0

    class TrdMarket:
        US = "US"

    def __init__(self, permission=True):
        self.quote = FakeQuoteContext(permission)
        self.trade = FakeTradeContext()

    def OpenQuoteContext(self, **kwargs):
        return self.quote

    def OpenSecTradeContext(self, **kwargs):
        return self.trade


class FakeSdkLogger:
    console_level = 20


def reachable(*args, **kwargs):
    return FakeSocket()


def test_unreachable_returns_structured_result():
    def refused(*args, **kwargs):
        raise ConnectionRefusedError()

    manager = MoomooConnectionManager(socket_connector=refused)
    result = manager.check_opend_socket()
    assert result.success is False
    assert result.status_code == "unreachable"
    assert result.message_zh == "OpenD不可达"


def test_sdk_missing_returns_clear_status(monkeypatch):
    manager = MoomooConnectionManager(socket_connector=reachable)
    monkeypatch.setattr(manager, "sdk_version", lambda: "")
    report = manager.inspect()
    assert report.status_code == "sdk_missing"
    assert report.status_message_zh == "Moomoo SDK未安装"


def test_contexts_are_always_closed():
    sdk = FakeSdk()
    manager = MoomooConnectionManager(sdk_loader=lambda: sdk, socket_connector=reachable)
    report = manager.inspect()
    assert report.status_code == "connected"
    assert sdk.quote.closed is True
    assert sdk.trade.closed is True


def test_sdk_console_info_logs_are_suppressed():
    sdk = FakeSdk()
    sdk.logger = FakeSdkLogger()
    manager = MoomooConnectionManager(sdk_loader=lambda: sdk, socket_connector=reachable)
    manager.inspect(["US.QQQ"])
    assert sdk.logger.console_level == 30


def test_permission_denied_is_not_connection_failure():
    sdk = FakeSdk(permission=False)
    manager = MoomooConnectionManager(sdk_loader=lambda: sdk, socket_connector=reachable)
    report = manager.inspect(["US.QQQ"])
    assert report.opend_reachable is True
    assert report.quote_context_available is True
    assert report.symbol_results["US.QQQ"]["状态"] == "权限不足"


def test_paper_account_is_identified():
    sdk = FakeSdk()
    report = MoomooConnectionManager(
        sdk_loader=lambda: sdk, socket_connector=reachable
    ).inspect()
    assert report.paper_account_found is True


def test_live_account_detected_but_trading_stays_off():
    sdk = FakeSdk()
    report = MoomooConnectionManager(
        sdk_loader=lambda: sdk, socket_connector=reachable
    ).inspect()
    assert report.live_account_found is True
    assert report.live_trading_enabled is False
    assert report.order_submission_enabled is False


def test_account_id_masking():
    assert mask_account_id("1234564821") == "****4821"
    assert "123456" not in mask_account_id("1234564821")


def test_capability_report_json_serialization():
    report = MoomooCapabilityReport(status_message_zh="检查完成")
    payload = json.dumps(report.safe_dict(), ensure_ascii=False)
    assert "检查完成" in payload
    assert '"live_trading_enabled": false' in payload


def test_user_status_is_chinese():
    manager = MoomooConnectionManager(socket_connector=lambda *a, **k: (_ for _ in ()).throw(OSError()))
    report = manager.inspect()
    assert report.status_message_zh == "OpenD不可达"
