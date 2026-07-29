# QuantPilot

![QuantPilot Logo](app/dashboard/static/quantpilot-logo.png)

美股量化研究、实时机会监控与本地公司工作台。Sprint 09 增加确定性 Market Regime 与 LONG/SHORT Candidate Pool。

## V1 安全边界

- 不支持真实账户下单，`LIVE` 在配置、Broker 与数据库层永久阻止。
- 不采集、不保存 Moomoo 密码或交易解锁密码。
- Telegram支持机会与运行状态通知；查询命令仅允许管理员白名单，且不包含任何交易控制。
- `.env` 永不提交；日志和 API 不输出 Secret。
- Moomoo 网页登录与 OpenD API 登录相互独立，OpenD 必须由用户本人安装并登录。

## 当前运行基线

- macOS 本机运行
- Python 3.9.6（项目要求 `>=3.9,<3.10`）
- pip + venv
- Docker 可选；当前开发机未安装、未验证，不是 V1 运行前提
- 不要求 uv

## 默认安装方法

```bash
git clone https://github.com/FinnZhang666/QuantPilot.git
cd QuantPilot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

`requirements.txt` 包含 Python 3.9 兼容的运行依赖和 `moomoo-api`；不得混用系统 Python 与项目虚拟环境。

## Market Regime 与候选池

```bash
python -m app.cli regime evaluate
python -m app.cli candidates build
python -m app.cli candidates list --limit 20
```

Dashboard 新增 `/dashboard/market-regime` 和 `/dashboard/candidates`。Market
Regime 只是环境加权，Candidate Pool 只是进一步研究入口，均不构成交易指令。
当前 SHORT 候选不会强迫 LONG-only 策略生成 SHORT Opportunity。详细说明见
`docs/SPRINT_09_MARKET_REGIME_CANDIDATE_POOL.md`。

## 配置、数据库与启动

复制 `.env.example` 后只在本机填写配置。默认数据库为 `data/quantpilot.db`，默认模式为 `INTERNAL_PAPER`。

```bash
python scripts/check_environment.py
alembic upgrade head
python scripts/init_database.py
python scripts/smoke_test.py
uvicorn app.main:app --reload
```

接口新增：`GET /moomoo/status`、`POST /moomoo/check`、`GET /moomoo/capabilities`。检查接口只执行一次性只读检查，不订阅、不解锁、不下单。

历史行情接口：`GET /instruments`、`GET /history/bars`、`GET /history/summary`、`GET /history/jobs`、`GET /history/issues`、`POST /history/sync`。详细规则见 `docs/HISTORICAL_DATA.md`。

## Sprint 07：Realtime Opportunity Runtime

Runtime复用现有OpenD实时行情、Feature Engine与Strategy Engine，只在闭合K线后生成独立Opportunity。重要状态变化可通过Telegram通知，但不会创建订单或执行交易。

```bash
alembic upgrade head
python -m app.cli runtime start
python -m app.cli runtime status
python -m app.cli opportunities list
python -m app.cli telegram test
```

API：`GET /api/opportunities`、`GET /api/opportunities/{id}`、`GET /api/opportunities/symbol/{symbol}`、`GET /api/runtime/status`、`POST /api/runtime/start`、`POST /api/runtime/stop`。详细配置与Windows部署注意事项见 `docs/SPRINT_07_RUNTIME.md`。

## Sprint 08：公司工作台

本地Dashboard用于观察运行状态、交易机会、策略、数据质量、历史摘要和开发Issue，不是交易终端。

```bash
alembic upgrade head
# 在.env中设置DASHBOARD_ADMIN_TOKEN
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问：`http://127.0.0.1:8000/dashboard`

默认`DASHBOARD_READONLY_PUBLIC=false`，只读页面也需要管理员Token。Runtime启停、创建Issue和修改Issue状态始终要求管理员鉴权。详细说明见`docs/SPRINT_08_DASHBOARD.md`。

## 测试

```bash
python -m pip check
python -m pytest
```

## Moomoo OpenD

官方连接链路为：Python 程序 → Moomoo Python SDK → 本机 OpenD → Moomoo 服务。Moomoo 网页登录不代表 OpenD 可用。

用户必须亲自完成 OpenD 的登录、验证码、设备确认、用户协议和行情协议确认。Codex 不读取浏览器密码，不保存账号密码，也不自动确认任何实盘授权。

启动并登录 OpenD 后运行：

```bash
python scripts/check_moomoo_connection.py
python scripts/check_moomoo_connection.py --json
python scripts/check_moomoo_connection.py --symbols US.QQQ US.SOXL
```

默认地址为 `127.0.0.1:11111`，可通过 `.env` 修改。脚本检查 Socket、SDK/OpenD 版本、登录状态、市场状态、QQQ/SOXL 快照、最近一根 K 线和美股账户类型。账户 ID 仅显示最后四位。权限不足会单独报告，不会误报成系统故障。

当前交易状态：

- 内部虚拟交易：代码存在，但 Sprint 01 不运行策略
- Moomoo 模拟下单：未启用，订单提交配置永久为 false
- Moomoo 实盘下单：V1 永久禁用
- Telegram 交易控制：不存在

## 历史行情

```bash
python scripts/init_instruments.py
python scripts/sync_history.py --symbols US.QQQ US.SOXL --intervals 1d 60m 15m 5m 1m
python scripts/check_history_data.py --symbols US.QQQ US.SOXL
python scripts/show_history_summary.py
```

支持1m、5m、15m、30m、60m和1d，默认前复权。主时间为UTC，并提供美东及北京时间。历史数据不保证包含完整夜盘，具体覆盖以Moomoo权限和接口返回为准。

## 实时行情

```bash
python scripts/start_realtime.py --symbols US.QQQ US.SOXL --duration 60
python scripts/check_realtime_status.py
python scripts/stop_realtime.py
python scripts/cleanup_realtime_data.py --dry-run
```

支持Quote、Ticker、实时1分钟K线和市场状态。数据经有界队列批量写入SQLite，只记录行情，不产生策略信号或订单。详见 `docs/REALTIME_DATA.md`。

## Feature Engine

```bash
python scripts/init_feature_definitions.py
python scripts/calculate_features.py --symbols US.QQQ US.SOXL --intervals 1d 60m
python scripts/check_feature_quality.py --symbols US.QQQ US.SOXL
python scripts/show_feature_summary.py
python scripts/compare_feature_calculation.py --symbol US.QQQ --interval 1d
```

Feature Engine提供带版本、参数Hash和质量状态的批量、增量及修复计算，只读取历史K线或已闭合实时1分钟K线。它不产生策略评分、交易信号或订单。接口为`/features/definitions`、`/features/latest`、`/features/values`、`/features/summary`、`/features/jobs`、`/features/issues`和`POST /features/calculate`。详细规则见`docs/FEATURE_ENGINE.md`和`docs/FEATURE_CATALOG.md`。

## Watchlist与候选信号

```bash
python scripts/init_watchlist.py
python scripts/add_watchlist_symbol.py PLTR
python scripts/calculate_strategy_signals.py --symbols SOXL --timeframes 1d --mode incremental
python scripts/show_latest_signals.py --symbol SOXL
python scripts/check_strategy_quality.py
```

Sprint 05只实现一套“趋势回撤后重新转强”策略。它按需读取Sprint 04 Feature并生成Candidate Signal，不下单、不模拟成交、不确认持仓。Score表示条件满足程度，Confidence表示数据可信度。所有模板均为尚未回测的默认参数。完整说明见`docs/STRATEGY_SIGNALS.md`。

## Telegram

在 `.env` 中手工设置 `TELEGRAM_ENABLED=true`、`TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`。开启但缺少配置时应用拒绝启动。真实发送测试必须由用户主动运行：

```bash
python scripts/test_telegram.py
```

## Docker（可选、未验证）

```bash
docker compose up --build
```

当前开发机未安装 Docker，这不是 V1 前提。Docker 文件仅作为可选部署基础，OpenD 不在容器中运行。

## 已知限制

当前不含Moomoo模拟下单、策略、回测、前端或真实Telegram信号通知。实时行情和历史行情能力取决于OpenD登录状态及市场权限。
# Sprint 06：轻量历史回测

Sprint 06 提供单标的、单策略、单周期的 Candidate Signal 历史回放与策略重算回测。默认在信号 K 线的下一根开盘成交，只做 `FLAT/LONG` 状态模拟，不连接券商、不创建订单。完整说明见 [docs/BACKTEST_ENGINE.md](docs/BACKTEST_ENGINE.md)。
## Sprint 10：Opportunity Outcome 复盘

Opportunity 现在会在配置窗口成熟后形成不可重复的最终 Review。Review 保存实际
价格路径、方向化收益、MFE、MAE、Target/Stop 触达和物化聚合统计，并可通过
Dashboard、管理员 API、CLI 与 Telegram 查询。

```bash
python -m app.cli review pending
python -m app.cli review run --limit 100
python -m app.cli review show --id 1
```

Dashboard 页面：`/dashboard/reviews`。详细设计和安全边界见
[`docs/SPRINT_10_REVIEW_ENGINE.md`](docs/SPRINT_10_REVIEW_ENGINE.md)。

Opportunity、Outcome 与 Review 都是研究对象，不是交易订单；本模块不会调用
Moomoo 下单接口。

## Sprint 11：AI Review Analyst

AI Review Analyst 对已经完成的 Opportunity Review 进行结构化复盘，输入包含
Outcome、Feature Snapshot、Strategy Context、Market Regime、Candidate Pool
以及历史同类统计。默认关闭；Mock Provider 仅用于测试且不计入真实统计。

```bash
python -m app.cli ai-review pending
python -m app.cli ai-review run --limit 20
python -m app.cli ai-review statistics
```

Dashboard：`/dashboard/ai-reviews`。详细配置、安全边界、API 和 Telegram 命令见
[`docs/sprints/SPRINT_11_AI_REVIEW_ANALYST.md`](docs/sprints/SPRINT_11_AI_REVIEW_ANALYST.md)。

AI 输出只供研究与复盘，不构成投资建议；AI 不会修改策略、参数或代码，不会调用
Codex，也不会创建订单。

## Sprint 12：Platform Foundation

QuantPilot 现在提供统一配置、环境校验、Secret Mask、结构化滚动日志、Health、
Version、Runtime Diagnostics、SQLite ZIP Backup 和 System Dashboard。

```bash
python -m app.cli health
python -m app.cli config
python -m app.cli version
python -m app.cli backup create
python -m app.cli backup list
python -m app.cli backup verify
```

平台接口为 `/health`、`/runtime` 与 `/api/platform/*`；System 页面为
`/dashboard/system`。详细说明见
[`docs/SPRINT_12_PLATFORM_FOUNDATION.md`](docs/SPRINT_12_PLATFORM_FOUNDATION.md)。

Telegram 每个管理员 ID 使用独立研究池：

```text
/watch add NVDA
/watch remove NVDA
/watchlist
```

之后候选、Opportunity、策略原因与 Review 查询仅针对该用户的研究股票。此能力
是轻量研究隔离，不是完整多租户账号系统。
