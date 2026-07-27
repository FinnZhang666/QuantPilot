# Sprint 05：轻量策略候选信号

## 概述与边界

Sprint 05在既有Feature Engine之上增加Watchlist和一套`pullback_restrength`策略，只服务少量观察标的，不扫描全市场。输出仅为Candidate Signal：`CANDIDATE_BUY`、`CANDIDATE_REDUCE`、`CANDIDATE_EXIT`、`WATCH`、`INSUFFICIENT_DATA`或`SKIPPED`。

Candidate Signal不是订单。系统不会自动下单、模拟成交、确认用户真实持仓或管理仓位。Candidate Reduce和Candidate Exit只代表策略风险提示。Sprint 05没有Backtest、Portfolio、Position Manager、Risk Engine、Broker或前端。

## Watchlist

用户新增Ticker只需输入证券代码。系统根据本地证券主数据和分类配置自动给出资产类型、行业、Role、Benchmark、Template及Timeframe。OpenD离线时仍允许保存，本地无法确认的Ticker标记为`PENDING_VALIDATION`，不会伪装成验证成功。

Role含义：

- `MARKET_BENCHMARK`：宽基市场参考，例如QQQ。
- `SECTOR_BENCHMARK`：行业参考，例如SOXX。
- `TRADING`：允许执行候选信号评估。
- `RISK_INDICATOR`：风险观察，默认不产生Candidate Buy。
- `PENDING_VALIDATION`：分类或证券状态仍待确认。

人工修改Role、Benchmark、Template或行业后，`classification_source`变为`MANUAL`，普通后台操作不会覆盖。显式重新分类并确认后才恢复`AUTO`。

## 主策略

“趋势回撤后重新转强”版本`1.0.0`只读取Sprint 04已保存的Feature，不在策略层重算技术指标：

1. 趋势：EMA20高于EMA60、EMA20斜率为正、价格位于EMA60上方。
2. 正常回撤：距20周期高点的回撤位于Template区间。
3. 重新转强：闭合K线重新站上EMA20、单周期收益为正、收盘位置和实体比例合理。
4. 成交量：Volume Ratio达到Template标准。
5. 相对强弱：按完全相同UTC时间读取QQQ或SOXX相对收益。
6. 风险：ATR百分比、RSI和VWAP偏离不能过高。

Score表示策略条件满足程度，Confidence表示数据完整性和可信程度，两者不是同一个指标。核心Feature缺失会输出`INSUFFICIENT_DATA`；可选Feature缺失会降低Confidence并写入Risks。不存在前向填充、后向填充、最近值或未来值替代。

当前所有模板参数状态均为`UNBACKTESTED_DEFAULT`，即“默认参数，尚未经过历史回测优化”。Sprint 06才允许验证收益率、最大回撤、胜率、盈亏比和参数敏感性；本Sprint不得把这些参数描述为最优或稳定盈利参数。

## 默认模板

- `BROAD_MARKET`
- `SECTOR_ETF`
- `LEVERAGED_ETF`
- `INVERSE_LEVERAGED_ETF`
- `HIGH_GROWTH`
- `DEFAULT`

参数保存在`strategy_parameter_sets`，使用排序JSON和SHA-256 Hash。参数变化不会修改已有Signal引用的旧Hash。

## 运行与保护

支持FULL、INCREMENTAL、RANGE及REALTIME。FULL和RANGE必须指定时间范围；INCREMENTAL没有历史Signal时只处理合理最小起点；REALTIME只处理最新闭合K线。

超过5个Ticker、3个Timeframe、90天或配置K线阈值属于大任务，必须显式确认。磁盘低于15GB警告；低于10GB禁止大范围Feature补算，但仍允许只读、小范围增量及单根实时计算。程序不会自动删除K线、Feature、Signal、日志或数据库。

## CLI

```bash
python scripts/init_watchlist.py
python scripts/add_watchlist_symbol.py PLTR --notes "AI长期观察"
python scripts/show_watchlist.py --enabled-only
python scripts/update_watchlist_symbol.py SOXS --role TRADING
python scripts/reclassify_watchlist_symbol.py SOXS --confirm
python scripts/update_strategy_parameters.py SOXL --set pullback_min_pct=3.0
python scripts/calculate_strategy_signals.py --symbols SOXL --timeframes 1d --mode incremental
python scripts/calculate_strategy_signals.py --symbols SOXL --timeframes 15m --mode range --start 2026-07-01T00:00:00Z --end 2026-07-20T00:00:00Z --dry-run
python scripts/show_latest_signals.py --symbol SOXL --min-confidence 70
python scripts/show_signal_detail.py --symbol SOXL --timeframe 1d --timestamp 2026-07-24T04:00:00Z
python scripts/check_strategy_quality.py
python scripts/smoke_test_strategy.py
```

## API

Watchlist：

- `GET /watchlist`
- `GET /watchlist/{symbol}`
- `POST /watchlist`
- `PATCH /watchlist/{symbol}`
- `DELETE /watchlist/{symbol}`
- `POST /watchlist/{symbol}/enable`
- `POST /watchlist/{symbol}/disable`
- `POST /watchlist/{symbol}/reclassify`
- `GET /watchlist/{symbol}/parameters`
- `PATCH /watchlist/{symbol}/parameters`

Strategy：

- `GET /strategy/signals/latest`
- `GET /strategy/signals`
- `GET /strategy/signals/summary`
- `GET /strategy/runs`
- `GET /strategy/runs/{run_id}`
- `POST /strategy/calculate`

列表默认100条、最多1000条并支持offset。可预期业务错误返回中文说明，不返回密钥、堆栈或账户信息。

## 已知限制

- 只实现一套策略，参数尚未回测。
- 不支持全市场扫描。
- 分类依赖本地规则和可用证券主数据。
- OpenD不可用时部分Ticker为`PENDING_VALIDATION`。
- 没有Backtest、参数优化、Portfolio、Position、订单、模拟成交或Web前端。
