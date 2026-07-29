# Sprint 07 — Realtime Opportunity Runtime + Telegram

## 实现说明

Runtime复用Sprint 03的OpenD连接、落库及有限重连，轮询Watchlist已启用周期的闭合实时K线。每个标的独立运行Sprint 04特征补算和Sprint 05策略，随后将合格的`CANDIDATE_BUY`转换为独立Opportunity。未闭合K线不生成正式Opportunity，单标的异常只记录错误，不终止其他标的。

Opportunity以`symbol + timeframe + strategy + version + direction + bar_time`去重。快照保存Feature引用、参数Hash、策略原因、风险和分项评分。Runtime重启后即使重新看到相同Signal，数据库去重也会阻止重复创建和推送。

当前策略只产生LONG机会；数据模型支持SHORT，但不会人为制造SHORT。

## 配置

```env
REALTIME_RUNTIME_ENABLED=false
REALTIME_TIMEFRAMES=1m
OPPORTUNITY_MIN_SCORE=70
OPPORTUNITY_DEFAULT_EXPIRY_BARS=3
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_IDS=
TELEGRAM_ADMIN_IDS=
```

`TELEGRAM_CHAT_IDS`是推送接收者，多个ID用逗号分隔。`TELEGRAM_ADMIN_IDS`是允许执行查询命令的管理员白名单。Token不会出现在API和日志中。旧的单值`TELEGRAM_CHAT_ID`仍兼容。

管理员命令：`/status`、`/opportunities`、`/symbol SOXL`、`/why SOXL`、`/help`。命令仅查询本地状态，不管理Watchlist、不确认持仓、不触发交易。

## 启动

```bash
alembic upgrade head
python -m app.cli runtime start
python -m app.cli runtime status
python -m app.cli runtime stop
```

也可通过FastAPI的`/api/runtime/start`和`/api/runtime/stop`幂等控制。OpenD断开时Runtime进入`DEGRADED`并复用现有实时管理器的重连能力，不会崩溃或下单。

## Telegram消息边界

只推送新Opportunity、失效、OpenD断开/恢复、Runtime启动和严重异常等重要变化，不逐根K线发送。消息使用“交易机会”“建议关注”“等待确认”等研究表述，不包含即时交易指令或收益承诺。

## Windows后续部署

- 安装Python 3.9.x并使用独立venv。
- OpenD必须在同一台Windows工作站由用户本人登录。
- SQLite数据库路径建议使用固定绝对路径，并确保Runtime进程具有读写权限。
- 使用任务计划程序或受控服务包装CLI；不要通过杀死所有Python进程停止Runtime。
- `.env`、数据库、日志和Telegram Token不得提交Git。
- Docker不是运行前提。

## 当前限制

Runtime启用Telegram后使用官方`getUpdates`轻量轮询接收受权限保护的只读命令，不开放Webhook。没有自由聊天、自选股管理、用户反馈、AI Analyst、Broker、模拟成交或自动下单。每日摘要可通过`/status`和Opportunity查询手动获得，暂未定时发送。
