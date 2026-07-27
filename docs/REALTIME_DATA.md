# 实时行情

运行基线固定为macOS、Python 3.9.6、pip、venv、SQLite和本机Moomoo OpenD。Docker不是前提，不使用Redis、Kafka或Celery。实时模块仅记录行情，不产生策略信号，不进行模拟或真实下单。

支持 `QUOTE`、`TICKER`、`KLINE_1M` 和 `MARKET_STATE`。默认标的为SOXL、MULL、TQQQ、NVDL、RAM、QQQ、SPY、SMH、SOXX、NVDA、AMD和MU，只订阅 `instruments` 中启用且已支持的记录。VIX保持不支持。`REALTIME_SYMBOLS` 可覆盖白名单。

## 启动和停止

```bash
python scripts/start_realtime.py --symbols US.QQQ US.SOXL
python scripts/start_realtime.py --symbols US.QQQ US.SOXL --duration 60
python scripts/check_realtime_status.py
python scripts/stop_realtime.py
```

持续模式写入 `data/realtime.pid`。停止脚本验证PID确属当前项目，不会终止其他Python进程。有限时模式到期后取消订阅、刷新队列并关闭Context。

## 交易时段

内部时段为夜盘行情、盘前、正常盘、盘后、休市和未知。OpenD市场状态优先；没有可靠状态时按America/New_York推断。夜盘仅表示行情时段，不代表Moomoo模拟交易或FirstTrade允许交易。扩展时段成交可能稀疏。

周末可明确判断。节假日及提前收盘依赖OpenD实际状态；无法确认时不会假装拥有完整交易日历。

## 队列、重连和健康

SDK回调只标准化并写入有界 `queue.Queue`。默认容量10000、批量200、每1秒刷新。队列满时丢弃新事件并累计统计，SQLite锁仅有限重试。

断线或高流动性参考标的数据停滞会使服务降级，并按配置有限重建Context、注册Handler和恢复原订阅。低流动性标的短暂无Ticker不会单独判定全局断线。

## 数据保留和对账

默认保留Ticker 30天、Quote 90天、实时K线365天。清理默认只预览：

```bash
python scripts/cleanup_realtime_data.py --dry-run
python scripts/cleanup_realtime_data.py --apply
```

实时1分钟K线保存在 `realtime_bars`，未完成K线持续Upsert。历史接口数据保存在 `market_bars`，两者来源和复权语义不同，不自动混合。

```bash
python scripts/reconcile_realtime_bars.py --symbol US.QQQ --date 2026-07-27
python scripts/reconcile_realtime_bars.py --symbol US.QQQ --date 2026-07-27 --apply
```

默认仅报告价格、成交量、缺失及时段差异。只有显式 `--apply` 才会把闭合实时K线以 `MOOMOO_REALTIME/NONE` 来源写入历史表。

## API

提供 `/realtime/status`、`/realtime/health`、`/realtime/subscriptions`、`/realtime/quotes/latest`、`/realtime/tickers`、`/realtime/bars` 及启动、停止、订阅、取消订阅接口。Ticker和K线默认最多1000条，绝对上限5000条。
