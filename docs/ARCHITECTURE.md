# Architecture

系统保持单向五层边界：

1. **Data**：行情与历史数据输入；Moomoo 适配器只暴露数据/只读检查。
2. **Feature**：把市场数据转换成可复用特征。
3. **Strategy**：基于特征产生带版本的 Signal。
4. **Decision**：结合组合、风险与市场状态决定是否允许执行。
5. **Execution**：只接受 Decision 输出；V1 仅支持内部虚拟成交及预留的 Moomoo 模拟接口。

数据库与日志贯穿各层，但不得跨层绕过 Decision 直接调用 Execution。`LiveTradingBlockedBroker` 是永久失败的安全哨兵，不是待实现的实盘接口。FastAPI 只提供查询接口，Sprint 00 没有下单 HTTP 端点。

## Sprint 01 OpenD接入

连接链路为 Python 3.9 应用 → `moomoo-api` → 本机 OpenD → Moomoo 服务。`MoomooConnectionManager` 仅在脚本或手工 API 请求时建立 Quote/US Trade Context，所有 Context 在一次检查结束后关闭。FastAPI 启动默认不连接 OpenD。

能力报告只保存安全布尔状态、版本、错误/警告和一次性行情能力；数据库不保存完整账户 ID、余额、持仓或凭据。Sprint 01 没有订单提交接口。
