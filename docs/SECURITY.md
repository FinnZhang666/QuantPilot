# Security

- V1 不支持实盘，`TRADING_MODE=LIVE` 会在配置加载时立即抛出异常。
- `paper_orders` 与 `trades` 使用数据库 `CHECK` 约束拒绝 `LIVE`。
- 不保存账号密码、交易解锁密码、完整 Token、Webhook 或其他 Secret。
- 所有敏感配置只从 `.env`/环境变量读取，`.env` 已加入 `.gitignore`。
- Telegram 只有主动发送接口；禁止 Webhook、消息监听、命令解析和交易控制。
- OpenD 必须由用户本人安装、登录和处理验证；应用不得自动填充凭据。
- 连接检查发现真实账户时仅报告存在性，绝不输出完整账户信息或启用交易。
- 内部成交必须标为 `INTERNAL_PAPER`，Moomoo 模拟成交必须标为 `MOOMOO_PAPER`。
- 安全配置 API 使用白名单，不依赖通用序列化或事后删除字段。
- `MOOMOO_LIVE_TRADING_ENABLED=true` 或 `MOOMOO_ALLOW_ORDER_SUBMISSION=true` 会导致配置启动失败。
- Sprint 01 只调用全局状态、行情快照、市场状态、少量历史 K 线和账户列表接口。
- 禁止调用 `unlock_trade`、`place_order`、`modify_order` 或 `cancel_order`。
- 用户必须亲自处理 OpenD 登录、验证码、设备确认及协议确认；不得索取、读取或保存密码。
- 真实账户只报告“发现”，账户标识最多显示最后四位，实盘交易仍永久禁用。

当前交易状态：内部虚拟成交代码保留但不运行策略；Moomoo 模拟下单未启用；实盘永久禁用；Telegram 交易控制不存在。

Sprint 02仅使用行情快照、证券基本信息和历史K线接口。历史同步不得查询账户余额、持仓或任何交易状态；数据库只保存公开市场行情和脱敏的支持状态，不保存登录配置。历史同步API要求显式有限范围，并对单次返回数量设置上限。
