# Sprint 09：Market Regime 与 Candidate Pool

## 定位

Market Regime 是确定性的市场环境描述，不是独立买卖信号。Candidate Pool
是低成本规则筛选后的有限研究入口，不是交易指令，也不等于 Watchlist 或
Opportunity。

- Watchlist：管理员长期关注范围。
- Candidate Pool：当天值得进一步研究的有限标的。
- Opportunity：特定策略在闭合 K 线后形成的可追溯机会对象。

后续 AI 研究原则上只读取 Candidate Pool，避免对全市场逐只进行昂贵深度
分析。本 Sprint 不调用 LLM。

## Market Regime

第一版使用 QQQ、SOXX、SOXS 的 1d 特征，综合趋势、动量、波动率和风险。
市场宽度暂无全市场数据，保存为 `null` 并标记 `UNAVAILABLE`，不伪装为真实
breadth。状态包括：

`STRONG_BULL / BULL / NEUTRAL / BEAR / STRONG_BEAR / UNKNOWN`

`long_bias` 和 `short_bias` 分别表示环境对两个方向的支持度，均为 0～100，
不要求合计为 100。BULL 不删除 SHORT，BEAR 也不删除 LONG。

阈值版本位于 `config/market_regime_v1.yaml`，版本写入快照。

## Candidate Pool

Universe Provider：

1. `WatchlistUniverseProvider`
2. `ConfigUniverseProvider`
3. `PreviousCandidateUniverseProvider`
4. `CombinedUniverseProvider`

当前只使用 Watchlist、少量配置标的和历史候选，不伪造全市场数据。构建按
标的逐个读取 1d 最新特征，不进行 `feature_values` 全表扫描。

LONG 与 SHORT 独立评分，包含趋势、突破/跌破、相对强弱、量能、安全性、
Watchlist 优先级和 Market Regime 调整。最终稳定按“评分降序、symbol
升序”排序。达到双向阈值且差距足够小时为 `BOTH`。

候选按 `symbol + market + pool_date` Upsert。重复构建只刷新评分、排名和
过期时间，不产生重复行。默认 36 小时过期。刷新只重算当前小范围 Universe。

## 使用

```bash
python -m app.cli regime evaluate
python -m app.cli regime current
python -m app.cli candidates build
python -m app.cli candidates list --min-score 60
python -m app.cli candidates show --symbol SOXL
```

Dashboard：

- `/dashboard/market-regime`
- `/dashboard/candidates`

管理员写操作继续使用 `DASHBOARD_ADMIN_TOKEN`。

Telegram 管理员命令：

- `/regime`
- `/candidates`
- `/long`
- `/short`
- `/candidate SOXL`

## 当前限制

- 没有真实全市场 breadth。
- 没有新闻、财报事件或全市场扫描。
- SHORT 候选不代表当前 LONG-only 策略能够生成 SHORT Opportunity。
- 不修改 Sprint 06 回测核心逻辑。
- 不调用 AI，不自动下单。

## Windows 后续运行

克隆仓库后使用 Python 3.9 创建虚拟环境，复制 `.env.example`，执行
`alembic upgrade head`。配置文件使用项目相对路径，不依赖开发者本机的
macOS 用户目录。SQLite、OpenD 和 Dashboard 均可在同一台 Windows 工作站
运行。
