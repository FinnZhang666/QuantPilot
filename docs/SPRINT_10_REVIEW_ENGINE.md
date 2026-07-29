# Sprint 10：Opportunity Review Engine

## 对象关系

系统将实时策略判断拆成三个可追溯对象：

1. `Opportunity`：在闭合K线后发现的研究机会，不等同于订单。
2. `Outcome`：Opportunity 在配置复盘窗口内的实际价格路径和方向化结果。
3. `OpportunityReview`：持久化的最终复盘记录，包含收益、MFE、MAE、目标/止损触达、持有时间和完整价格路径。

Review 失败只会把对应 Opportunity 标记为 `REVIEW_FAILED`，不会中断实时 Runtime。

## 生命周期

```text
DETECTED → NOTIFIED → ACTIVE → EXPIRED → REVIEW_PENDING → REVIEWED
                                                     ↘ REVIEW_FAILED
```

第一版每个 Opportunity 只有一个最终 Review。多个窗口的阶段收益写入同一条
`statistics_json.window_returns`，为以后支持多条 Window Review 保留兼容空间。

## 窗口与指标

窗口读取自 `config/review_windows_v1.yaml`，默认包含 `1h`、`4h`、`1d`、
`3d`、`5d`、`10d` 和 `20d`。最长窗口成熟后计算：

- 最终方向化收益
- MFE / MAE
- 最高价、最低价和最大/最小收盘收益
- 持有 K 线、分钟和天数
- Target / Stop 是否触达
- ATR 倍数（ATR 可用时）
- 风险收益参考
- 各 Review Window 的阶段收益

LONG 和 SHORT 使用同一计算接口。当前真实策略仅产生 LONG 时，系统不会人为制造
SHORT Opportunity。

## 运行方式

```bash
python -m app.cli review pending
python -m app.cli review run --limit 100
python -m app.cli review run --symbol SOXL
python -m app.cli review show --id 1
```

Runtime 会通过独立后台线程、小批量触发 Review，不阻塞实时行情和 Opportunity
Pipeline。重复运行以 `opportunity_id` 唯一约束保证幂等。

管理员 API：

```text
POST /api/review/run
GET  /api/review/pending
GET  /api/review
GET  /api/review/{id}
GET  /api/review/statistics
```

访问 `/dashboard/reviews` 查看列表，访问 `/dashboard/reviews/{id}` 查看价格路径与
Outcome 指标。所有 Review API 都使用 Dashboard 管理员 Token。

Telegram 管理员命令：

```text
/review
/review SOXL
/review pending
```

Review 和统计只用于研究复盘，不构成交易建议，不会触发任何订单。

## 配置

```text
OPPORTUNITY_REVIEW_ENABLED=true
OPPORTUNITY_REVIEW_WINDOWS_FILE=config/review_windows_v1.yaml
OPPORTUNITY_REVIEW_BATCH_SIZE=100
OPPORTUNITY_REVIEW_POLL_SECONDS=300
```

## 当前限制

- 每个 Opportunity 当前保存一个最终 Review，多窗口结果放在 JSON 快照内。
- 只读取本地已有历史 K 线；缺失数据不会自动下载或伪造。
- 节假日和非交易时段可能让自然时间窗口内的 K 线数量较少。
- 不包含 AI Review、新闻分析、参数优化、自动开发或任何下单能力。
