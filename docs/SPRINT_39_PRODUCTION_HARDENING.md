# Sprint 39 — Production Hardening & Architecture Consistency

Trade Companion 1.0.0-rc1 对 Sprint 29–38 产品链路执行生产一致性审计。本 Sprint 不增加业务能力、
数据库表或 Migration。

## Single Source of Truth

`MarketSnapshotService` 是 Market、Feature、Candidate、Trade Plan、Holding 与 Watchlist 状态的事实
聚合来源。`SymbolOverviewService` 复用其 DTO 和已加载 sources；API、Dashboard 与 Telegram
Presenter 只消费 Service 输出，不自行映射状态。

## 状态与 Candidate

- 仅 `PLAN`、`COMPANION` 映射 `strategy_status=ACTIVE`。
- `REVIEW`、`CANCELLED`、`EXPIRED` 保持真实 `trade_plan_status`，不映射 ACTIVE。
- Candidate 必须匹配 Symbol、Market、`VALID`、当前 Strategy Name 与 Version。
- 最新值按 `bar_timestamp DESC, id DESC` 选择；ERROR、EXPIRED、其他市场/标的/版本均排除。

## Repository、Service 与性能

Symbol Overview 不再重复查询 Plan/Holding，而使用 Snapshot 请求级 source bundle。Dashboard API
客户端对单页 GET 使用 Promise Cache，写操作后清空，避免详情与统一导航重复请求。未引入 Redis、
后台预计算或持久化缓存。Route 和 Formatter 不新增业务计算。

## API、异常与安全

近期聚合 API 对不存在资源返回 404、Domain Validation 返回 422；未知异常交给统一框架处理，不被
伪装成业务错误。Internal API 继续隐藏于 OpenAPI，响应不包含 Dashboard Token、Telegram Token、
AI Key 或底层堆栈。

## Dashboard、Formatter 与 Logging

详情页复用 Symbol Header、Related Objects、Loading 与 Empty State。Markdown 转义、Decimal 文本和
4,000 字符限制集中在 `telegram_product.base`，既有 Formatter 公开语义保持兼容。运行模块继续使用
现有 Logging Center；新产品层无 `print()`、外网发送或敏感值日志。

仓库名、包名、数据库文件名中的 QuantPilot 是 Beta 部署兼容标识，不是用户可见产品名，保留到独立
Repository Migration Sprint。

## 保持不变

Strategy、Feature Engine、Candidate Generation、Trade Plan、Portfolio、Review、AI Companion 与
Telegram Product Layer 的业务决策未修改；无 Broker、OpenD Runtime、Telegram Runtime 或 Push。
