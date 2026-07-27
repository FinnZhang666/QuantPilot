# 历史行情数据仓库

## 运行基线

项目固定使用 macOS、Python 3.9.6、pip、venv 和 SQLite。Docker 与 uv 都不是运行前提。

## 支持周期与默认范围

支持 `1m`、`5m`、`15m`、`30m`、`60m`、`1d`。默认同步范围：

- 1d：最近5年
- 60m：最近2年
- 15m：最近365天
- 5m：最近180天
- 1m：最近60天

范围可通过 `.env` 覆盖，但不会默认请求无限历史。请求串行执行，支持分页Token、重复Token保护、最大500页、有限重试与请求间隔。

## 复权

支持 `NONE`、`FORWARD`、`BACKWARD`，分别映射Moomoo不复权、前复权和后复权。默认使用 `FORWARD`。复权方式属于唯一键，不同复权数据不会互相覆盖。前复权会以较新的价格尺度调整历史价格，适合长期收益研究；不得与其他复权方式混用。

## 时区与交易时段

主时间保存UTC，同时保存 `America/New_York` 市场时间和交易日期；API还提供 `Asia/Shanghai` 展示时间。转换使用IANA时区数据库并处理夏令时，不使用固定UTC偏移。

初步识别 `OVERNIGHT`、`PRE_MARKET`、`REGULAR`、`AFTER_HOURS`、`CLOSED`、`UNKNOWN`。当前仅按美东基础时间窗口分类，节假日与提前收盘日仍可能需要人工确认。历史K线是否覆盖完整夜盘以Moomoo实际返回为准，系统不会伪造缺失时段。

## 数据库

- `instruments`：规范代码、别名与支持状态
- `market_bars`：Decimal价格、UTC时间、复权方式和数据源
- `history_sync_jobs`：范围、分页、行数、耗时和错误
- `history_data_issues`：OHLC、成交量、时间顺序和明显缺口问题

唯一键为 `symbol + interval + timestamp_utc + adjustment_type + data_source`。写入使用单任务事务和500行批次upsert。

## 增量与修复

增量同步从本地最后一根K线附近重新请求：日线重叠最近约5个交易日（实现保守使用8个自然日），分钟线重叠20根。供应商修正会upsert更新而不是重复插入。`--repair`允许指定范围重拉。

## CLI

```bash
python scripts/init_instruments.py
python scripts/sync_history.py --symbols US.QQQ US.SOXL --intervals 1d 60m 15m 5m 1m
python scripts/sync_history.py --symbols US.QQQ --intervals 1d --incremental
python scripts/sync_history.py --symbols US.QQQ --intervals 5m --start 2026-07-01 --end 2026-07-10 --repair
python scripts/check_history_data.py --symbols US.QQQ US.SOXL
python scripts/show_history_summary.py
```

## API

- `GET /instruments`
- `GET /history/bars`：默认1000条，绝对最大5000条
- `GET /history/summary`
- `GET /history/jobs`
- `GET /history/issues`
- `POST /history/sync`：必须显式指定标的、周期和有限日期范围

## 权限与限制

只使用Moomoo行情接口。不查询真实账户资金或持仓，不调用解锁、下单、改单或撤单。无效代码、权限不足和不支持证券会分别记录；单标的失败不会回滚其他标的。Moomoo可能限制指数或特定品种历史行情，当前不接第三方数据源。
