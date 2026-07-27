#!/usr/bin/env python3
import argparse
import json
import platform
import sys

from app.core.config import get_settings
from app.data.providers.moomoo import MoomooConnectionManager


def yn(value: bool) -> str:
    return "是" if value else "否"


def main() -> int:
    parser = argparse.ArgumentParser(description="Moomoo OpenD只读能力检查")
    parser.add_argument("--json", action="store_true", help="输出机器可读JSON")
    parser.add_argument("--symbols", nargs="+", default=["US.QQQ", "US.SOXL"])
    args = parser.parse_args()
    settings = get_settings()
    manager = MoomooConnectionManager(
        settings.moomoo_opend_host,
        settings.moomoo_opend_port,
        settings.moomoo_connection_timeout_seconds,
    )
    report = manager.inspect(args.symbols, enabled=settings.moomoo_enabled)
    if args.json:
        print(json.dumps(report.safe_dict(include_masked_accounts=True), ensure_ascii=False, indent=2))
    else:
        print("Moomoo OpenD连接检查")
        print("Python版本：" + platform.python_version())
        print("Moomoo SDK：" + ("已安装" if report.sdk_available else "未安装"))
        print("SDK版本：" + (report.sdk_version or "未知"))
        print(f"OpenD地址：{settings.moomoo_opend_host}:{settings.moomoo_opend_port}")
        print("Socket可达：" + yn(report.opend_reachable))
        print("OpenD登录：" + yn(report.opend_logged_in))
        print("OpenD版本：" + (report.opend_version or "未知"))
        print("行情连接：" + ("成功" if report.quote_context_available else "失败"))
        print("美国行情权限：" + ("可用" if report.us_quote_available else "不足或未检查"))
        for symbol in args.symbols:
            item = report.symbol_results.get(symbol, {})
            print(symbol + "快照：" + ("成功" if item.get("快照") else item.get("状态", "失败")))
        print("历史K线读取：" + ("成功" if report.historical_kline_available else "失败或未检查"))
        print("市场状态读取：" + ("成功" if report.market_state_available else "失败或未检查"))
        print("模拟账户：" + ("发现" if report.paper_account_found else "未发现"))
        print("真实账户：" + ("发现（真实交易永久禁用）" if report.live_account_found else "未发现"))
        for account in report.masked_accounts:
            print(
                "{类型}：发现，账户标识：{账户标识}，市场：{市场}，状态：{状态}".format(**account)
            )
        print("订单提交：关闭")
        print("模拟下单：本Sprint未启用")
        print("实盘交易：永久禁止")
        print("检查结果：" + report.status_message_zh)
        for error in report.errors:
            print("错误：" + error)
        for warning in report.warnings:
            print("警告：" + warning)
    return 0 if report.opend_reachable and report.opend_logged_in else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("检查已由用户中止。", file=sys.stderr)
        raise SystemExit(130)
