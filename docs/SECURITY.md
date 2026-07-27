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
