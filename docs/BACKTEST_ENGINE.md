# Lightweight Backtest Engine（Sprint 06）

Sprint 06 将 Sprint 05 的 Candidate Signal 转换为可复现的历史模拟交易结果。它是研究工具，不连接券商、不提交订单，也不修改 Portfolio、Position、Paper Order 或 Trade 业务表。

## 固定规则

- 单标的、单策略、单周期独立回测；不构建组合。
- 正式区间为闭区间 `[start_time, end_time]`，且必须显式提供。
- 默认 `SIGNAL_REPLAY`；也支持复用 Sprint 05 策略引擎的 `STRATEGY_RECOMPUTE`。
- 信号在 K 线闭合后产生，统一在下一根 K 线开盘执行（`NEXT_BAR_OPEN`）。
- 仅支持 `FLAT` 与 `LONG`，不加仓、不分批、不做空。
- `CANDIDATE_REDUCE` 在持仓状态下按全部退出处理，但交易记录保留原触发类型。
- 默认整数股、`FULL_CASH`；手续费和滑点均可配置。
- 默认期末强制按最后一根正式 K 线收盘价平仓，并明确标记为 `FORCED_END_OF_BACKTEST`。
- 少于 20 根正式 K 线时只返回诊断，不形成有效绩效结论。

## 数据真实性和防未来数据

数据只读取 `market_bars` 的 `FORWARD/MOOMOO` 历史闭合 K 线以及 Sprint 05 Candidate Signal。信号 K 线本身不会作为成交价格；最后一根信号没有下一根 K 线时记录 `UNFILLED_END_OF_DATA`。相同配置重复运行会创建独立 Run，并通过 `configuration_hash` 标记重复配置。

## CLI

```bash
python scripts/run_backtest.py \
  --symbol SOXL --timeframe 60m \
  --start 2025-01-01T00:00:00Z --end 2026-01-01T00:00:00Z

python scripts/show_backtest_result.py 1
```

## API

- `POST /backtest/runs`
- `GET /backtest/runs`
- `GET /backtest/runs/{run_id}`
- `GET /backtest/runs/{run_id}/trades`
- `GET /backtest/runs/{run_id}/equity`

列表接口有分页保护。回测结果同时记录标的 Buy & Hold 和 Watchlist Benchmark；行业 Benchmark 无数据时回退 QQQ 并标记 `FALLBACK`，两者均不可用则标记 `UNAVAILABLE`。

## 当前限制

不支持 Portfolio、做空、部分仓位、Tick/订单簿撮合、参数优化、机器学习、实盘或模拟下单。`NEXT_BAR_CLOSE` 仅保留概念，当前不可启用。
