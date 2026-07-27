# Feature Engine

## 边界

Sprint 04只把`market_bars`和已闭合的`realtime_bars`转换为可复用特征、质量状态及计算任务记录。它不修改原始行情，不计算买卖评分，不生成信号、持仓或订单，也不连接任何交易接口。运行基线固定为Python 3.9.6、pip、venv和SQLite；Docker不是前提。

## 数据模型

- `feature_definitions`：英文稳定名称、中文名称、参数、预热条数、周期、参考标的和版本。
- `feature_values`：UTC时间、版本、稳定参数Hash、一个类型化值字段、源K线时间、数据源和质量状态。
- `feature_calculation_jobs`：FULL、INCREMENTAL、REPAIR或REALTIME任务及吞吐统计。
- `feature_quality_issues`：输入缺口、非法输出、错位、参考数据缺失、版本冲突及潜在未来泄漏。

唯一键由标的、周期、UTC时间、特征名、版本、参数Hash及数据源组成。关键数值以`Numeric`/`Decimal`保存。首版公式版本为`1.0.0`。

## 数据来源与周期

支持`1m`、`5m`、`15m`、`30m`、`60m`和`1d`。历史计算读取前复权、`MOOMOO`来源的`market_bars`；实时计算仅读取`is_closed=true`、`MOOMOO`来源的1分钟`realtime_bars`，输出数据源标记为`MOOMOO_REALTIME`。两类结果不互相覆盖。

默认`--all`输出范围为：日线现有全部数据、60分钟最近2年、15分钟最近1年、5分钟最近180天、1分钟最近60天。FastAPI启动不会自动计算。

## 计算和质量规则

所有滚动窗口均向后看且不居中；禁止`bfill`。突破阈值和成交量比率明确排除当前K线。跨标的只按完全相同的`timestamp_utc`对齐，不使用未来值或无限最近邻填充。增量和修复会读取足够的历史上下文再只保存目标范围，因此递归EMA、Wilder RSI和ATR可重算。

不足`required_bars`的结果保存为`WARMUP`且值为空；源字段缺失或参考标的不存在保存为`MISSING`；NaN和Infinity不写入数值字段并标记`INVALID`。不得用0替代缺失值。单个特征或标的失败会被隔离并记录，原始K线不受影响。

## CLI

```bash
python scripts/init_feature_definitions.py
python scripts/calculate_features.py --symbols US.QQQ US.SOXL --intervals 1d 60m
python scripts/calculate_features.py --symbols US.SOXL --intervals 1m --incremental
python scripts/calculate_features.py --symbols US.SOXL --intervals 5m --features ema_20 atr_14 --start 2026-07-01 --end 2026-07-27 --repair
python scripts/check_feature_quality.py --symbols US.QQQ US.SOXL
python scripts/show_feature_summary.py
python scripts/compare_feature_calculation.py --symbol US.QQQ --interval 1d
```

初始化使用Upsert，重复执行不会产生重复定义。`--all`遵守配置范围，不能表示无限历史。

## API

- `GET /features/definitions`
- `GET /features/latest`
- `GET /features/values`
- `GET /features/summary`
- `GET /features/jobs`
- `GET /features/issues`
- `POST /features/calculate`

values默认最多1000条，绝对上限5000条。计算请求必须明确提供标的、周期、特征、带时区的开始和结束时间。用户可见状态及参数错误使用中文。

## 配置和性能

`FEATURE_READ_CHUNK_SIZE=10000`、`FEATURE_WRITE_BATCH_SIZE=1000`、`FEATURE_MAX_WORKERS=1`。SQLite保持单写入者并批量Upsert，不逐条提交。现阶段读取按标的和周期隔离；长历史递归指标需要保留前置上下文，因此峰值内存与单标的单周期数据量相关。

