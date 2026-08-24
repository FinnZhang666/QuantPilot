# Trade Companion

QMR 实盘信号、Telegram 去重通知与持续验证闭环见
[`docs/SPRINT_06_QMR_LIVE_SIGNAL.md`](docs/SPRINT_06_QMR_LIVE_SIGNAL.md)。
QMR 在现有策略中心的正式注册、状态和版本关系见
[`docs/QMR_STRATEGY_CENTER.md`](docs/QMR_STRATEGY_CENTER.md)。

![Trade Companion Logo](app/dashboard/static/branding/trade-companion-logo.png)

**陪你把每一笔交易做完 · Your AI Trade Companion**

Trade Companion 是一个 AI 辅助的美股研究与交易生命周期工作台，将数据、特征、
策略观察、Opportunity、Review 与研究证据连接起来。它的定位是陪伴用户完成
交易前、交易中和交易后的研究流程，而不是只提供一个买卖信号。

项目内部包名、数据库文件名和 GitHub 仓库名在 Beta 期间继续保持 `quantpilot`、
`quantpilot.db` 与 `FinnZhang666/QuantPilot`，以保持部署和导入兼容性。

## 当前发布状态

- Product：Trade Companion
- Release：`v1.0.0-beta.1`
- Stage：Beta
- Database Migration Head：`0031`
- 范围：Paper Trading Only，不连接真实券商下单，不同步真实持仓。
- Beta 仍需观察长期稳定性；当前策略样本有限，Trade Plan 可能为 0，Sharpe 暂无可靠样本。

## V1 安全边界

- 不支持真实账户下单，`LIVE` 在配置、Broker 与数据库层永久阻止。
- 不采集、不保存 Moomoo 密码或交易解锁密码。
- Telegram支持机会与运行状态通知；查询命令仅允许管理员白名单，且不包含任何交易控制。
- `.env` 永不提交；日志和 API 不输出 Secret。
- Moomoo 网页登录与 OpenD API 登录相互独立，OpenD 必须由用户本人安装并登录。

## 当前运行基线

- Windows 主要运行环境，保持 macOS / Linux 跨平台兼容
- Python 3.9.x（项目要求 `>=3.9,<3.10`）
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
完整发布文档：[`INSTALLATION.md`](docs/INSTALLATION.md)、[`DEPLOYMENT.md`](docs/DEPLOYMENT.md)、
[`RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md)、[`BACKUP_AND_RECOVERY.md`](docs/BACKUP_AND_RECOVERY.md)
和 [`KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)。

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

### Release Dashboard 2.0

Release UI Review 使用统一的紧凑深色工作台、分组及可折叠导航、中文/English 语言切换、
响应式表格和可追溯版本页。界面只聚合现有服务数据，不修改策略、交易计划、持仓、复盘或
AI 业务结果。设计规范和按钮审计见
[`SPRINT_41_DASHBOARD_UX_REFRESH.md`](docs/SPRINT_41_DASHBOARD_UX_REFRESH.md)。
产品后台最终按工作台、市场、策略、AI、产品运营、Strategy Lab 和更多七个一级模块组织；
Feedback Center 与 Telegram 反馈按钮目前仅完成信息架构和展示模型，不启动 Bot 或写入新业务数据。
详见 [`SPRINT_41_PRODUCT_ARCHITECTURE_FINAL.md`](docs/SPRINT_41_PRODUCT_ARCHITECTURE_FINAL.md)。

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

当前已包含 Strategy、Backtest、Dashboard、Trade Lifecycle、Review、AI Companion Mock 和 Telegram
产品预览层，但仍不包含 Broker 实盘执行。Telegram 产品按钮/Deep Link 尚未与 Windows 部署端真实
Bot Runtime 联调；外部 AI Provider 和 Windows 生产环境也尚未完成发布验证。实时与历史行情覆盖仍
取决于用户本机 OpenD 登录状态和市场权限。完整清单见
[`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)。
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

Trade Companion 现在提供统一配置、环境校验、Secret Mask、结构化滚动日志、Health、
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

## Sprint 13：Research Center

Research Center 为每个 Opportunity 建立唯一研究档案，统一聚合 Candidate、
Opportunity、Review、AI Review、Evidence、Timeline、Manual Notes、
Attachments、Investigation 和相似历史案例。

```bash
python -m app.cli research show
python -m app.cli research timeline --id 1
python -m app.cli research note --id 1 --content "观察成交量"
python -m app.cli research similarity --id 1
```

Dashboard：`/dashboard/research`。完整说明见
[`docs/SPRINT_13_RESEARCH_CENTER.md`](docs/SPRINT_13_RESEARCH_CENTER.md)。
Research Center 不会自动修改策略或代码，不会调用Codex、创建Git Issue或交易。

## Sprint 30：Trade Lifecycle Foundation

Trade Lifecycle 将既有 Strategy Engine 输出结构化为可追踪的 Trade Plan，
支持 `DISCOVER → PLAN → COMPANION → REVIEW` 及取消、过期终态。
本层不计算新信号，不推导Strategy Engine未提供的价格区间，也不生成订单。

Dashboard：`/dashboard/trade-plans`

Read-only API：`GET /api/trade-plans`、`GET /api/trade-plans/{plan_id}` 和
`GET /api/trade-plans/{plan_id}/history`。详见
[`docs/SPRINT_30_TRADE_LIFECYCLE_FOUNDATION.md`](docs/SPRINT_30_TRADE_LIFECYCLE_FOUNDATION.md)。

## Sprint 31：Trade Plan Runtime

Trade Companion 会把既有 `CANDIDATE_BUY + VALID` Strategy Signal 幂等转换为真实
Trade Plan，并通过生命周期审计从 `DISCOVER` 推进到 `PLAN`。现有 Runtime 会触发轻量
Generator；Dashboard 提供真实列表与详情，内部管理员接口可进行有限批次生成。

本功能不改变 Strategy Engine，不进入用户参与阶段，不下单，也不会在 macOS 启动或发送
Telegram。架构、去重规则与部署边界见
[`docs/SPRINT_31_TRADE_PLAN_RUNTIME.md`](docs/SPRINT_31_TRADE_PLAN_RUNTIME.md)。

## Sprint 32：User Participation Engine

User Position 独立记录每位用户是否参与 Trade Plan、自己的进入价格、可选数量及平仓状态。
系统 Trade Plan 保持不可被用户修改；同一个 Plan 可以关联多个用户，彼此完全隔离。

Dashboard：`/dashboard/positions`。只读 API：`GET /api/user-positions`、
`GET /api/user-positions/{id}` 和 `GET /api/user-positions/statistics`。管理员内部 open/close
接口不会出现在 OpenAPI，也不会触发真实交易。详见
[`docs/SPRINT_32_USER_PARTICIPATION_ENGINE.md`](docs/SPRINT_32_USER_PARTICIPATION_ENGINE.md)。

## Sprint 33：Review Engine Foundation

Trade Review 只针对终态 Trade Plan（`REVIEW/CANCELLED/EXPIRED`）和 `CLOSED` User Position，
使用现有 Historical Bars 计算基础 MFE/MAE、持有时间及 Target/Stop 命中。重复回填更新同一
Review，不会产生重复记录，也不会修改来源对象。

Dashboard：`/dashboard/trade-reviews`。只读 API：`GET /api/reviews`、
`GET /api/reviews/{id}`、`GET /api/reviews/statistics`。手工 Runtime 的管理员内部接口默认
dry-run，本 Sprint 不接 Scheduler。完整公式和边界见
[`docs/SPRINT_33_REVIEW_ENGINE_FOUNDATION.md`](docs/SPRINT_33_REVIEW_ENGINE_FOUNDATION.md)。

## Sprint 34：AI Companion Foundation

AI Companion 只解释既有 Trade Plan、User Position、Trade Review 和现有 Statistics，Strategy
Engine 仍是唯一决策来源。默认使用确定性离线 Mock Provider；Context、Prompt、结构化输出、
Validator、持久化、审计、只读 API、Dashboard 和 Formatter 已形成安全闭环。

Dashboard：`/dashboard/ai-companion`。只读 API：`GET /api/ai-companion/outputs` 和
`GET /api/ai-companion/outputs/{id}`（保留旧路径兼容）。管理员内部生成接口默认 dry-run，
不调用 Provider、不写库。
本 Sprint 没有真实 Gemini、外部 AI 或 Telegram 调用。详见
[`docs/SPRINT_34_AI_COMPANION_FOUNDATION.md`](docs/SPRINT_34_AI_COMPANION_FOUNDATION.md)。

## Sprint 35：Portfolio Center Foundation

Portfolio Center 保存用户手工录入的 Portfolio、Holding 与 Portfolio Watchlist，并提供统一的
事实统计、只读 API、管理员管理接口、Dashboard 和纯 Formatter。这里的 Holding 不是 Broker
Position：系统不读取券商、OpenD 或实时行情，不计算市值、盈亏或收益率，也不触发 Review、AI、
策略、通知或交易。

Dashboard：`/dashboard/portfolios`。公开文档中的读取 API 使用现有管理员身份；当前没有可靠普通
用户身份上下文，因此普通用户访问采用 Fail Closed。完整说明见
[`docs/SPRINT_35_PORTFOLIO_CENTER.md`](docs/SPRINT_35_PORTFOLIO_CENTER.md)。

## Sprint 36：Market Snapshot Foundation

Market Snapshot 是不持久化的只读聚合模型，将已有 Market Bar、Feature、Candidate Signal、Trade
Plan、Portfolio Holding 和 Investment Watchlist 统一为每个 Symbol 一份 Snapshot。它不重新计算
Feature 或 Signal，不调用 AI、Broker、OpenD 或 Telegram，也不写入数据库。

Dashboard：`/dashboard/market-snapshots`。只读 API：`GET /api/market-snapshots`、
`GET /api/market-snapshots/{symbol}` 和 `GET /api/watchlists/{portfolio_id}/snapshots`。完整说明见
[`docs/SPRINT_36_MARKET_SNAPSHOT.md`](docs/SPRINT_36_MARKET_SNAPSHOT.md)。

## Sprint 37：Experience Integration

`GET /api/symbols/{symbol}/overview` 与 `/dashboard/symbols/{symbol}` 以 Symbol 为入口，将只读
Snapshot、Trade Plan、Portfolio Holding、Trade Review 和已缓存 AI Companion Analysis 汇总为
统一工作流。各详情页共享 Related Objects 导航；缺失对象明确显示 `Not Available`。AI 入口统一
委托现有 `CompanionService`，不改变 Prompt、Provider 或策略决策。详见
[`docs/SPRINT_37_EXPERIENCE_INTEGRATION.md`](docs/SPRINT_37_EXPERIENCE_INTEGRATION.md)。

## Sprint 38：Telegram Product Integration

Telegram 产品层把 Symbol Overview 转换为版本化 ViewModel、Markdown-safe 消息、Action Button 与
Deep Link。`GET /api/telegram-preview/{symbol}` 和 `/dashboard/telegram-preview` 仅提供预览，返回
`sent=false`；该层不读取 Repository、不访问网络、不接 Bot Token，也不启动 Polling、Webhook 或
消息发送。详见 [`docs/SPRINT_38_TELEGRAM_PRODUCT_LAYER.md`](docs/SPRINT_38_TELEGRAM_PRODUCT_LAYER.md)。

## Sprint 39：Production Hardening

Trade Companion 1.0.0-rc1 完成聚合、Repository、Service、API、Dashboard、Formatter、异常、安全和
性能一致性审计。Strategy Status 仅在 PLAN/COMPANION 映射 ACTIVE；Candidate 统一限制为当前市场、
当前策略版本的最新 VALID 记录；Symbol Overview 复用 Snapshot 已加载来源，Dashboard 在单页内合并
重复 GET。该 Sprint 不增加业务模块、数据库或 Migration。详见
[`docs/SPRINT_39_PRODUCTION_HARDENING.md`](docs/SPRINT_39_PRODUCTION_HARDENING.md)。

## Sprint 40：Release Candidate Finalization

Trade Companion 1.0.0-rc2 冻结 Public API、Dashboard、数据库和业务逻辑，只补全配置说明、安装、部署、
备份恢复、已知问题和发布检查清单。RC2 离线基线不包含 Windows、OpenD Runtime、Telegram Runtime、
Broker 或外部 AI Provider 的生产联调。

## Windows Phase 4: System Paper Runtime

Phase 4 adds an isolated system paper ledger, deterministic LONG/SHORT
`paper-fill-v1`, bounded position sizing, partial/full exits, stale-data aware
valuation and equity curve, immutable objective review, complete strategy
scoreboard, non-overlapping Scheduler, audit trace, Dashboard views, and
Telegram Preview. All runtime flags default to disabled. Broker trading, OpenD
realtime, Telegram transport and external AI transport remain off. See
[`docs/WINDOWS_PHASE4_RUNTIME_PAPER_TRADING.md`](docs/WINDOWS_PHASE4_RUNTIME_PAPER_TRADING.md).

## Sprint 41 Part D：Dashboard Route Repair 与 Mac 交接

最终 Dashboard 信息架构的所有 Sidebar 页面均有真实、受登录保护的 HTML Route。市场监控、策略成绩、
系统监控和安全日志视图读取现有服务；尚无可靠数据源的模拟持仓、参数实验和产品运营指标使用明确空状态，
不伪造数据。Sidebar 分组可折叠，工作台采用紧凑运营布局。

同时准备了 5 个 Telegram Bot 的脱敏 Profile、定稿中英文 `/start` 文案、Commands、菜单、512×512 头像与
默认 dry-run 同步工具。Mac 不执行真实同步、不发送消息、不启动 Telegram Runtime；详见
[`docs/SPRINT_41_PART_D_DASHBOARD_ROUTE_REPAIR.md`](docs/SPRINT_41_PART_D_DASHBOARD_ROUTE_REPAIR.md)。
# Trade Companion Telegram Runtime (Windows Phase 5)

The unified, configuration-backed multi-Bot runtime is documented in
[`docs/WINDOWS_PHASE5_TELEGRAM_RUNTIME.md`](docs/WINDOWS_PHASE5_TELEGRAM_RUNTIME.md).
Bot tokens remain local in `.env`; `config/telegram_bots.json` contains public profile
copy only. Preview and real delivery share one renderer, and Bot avatars remain a
manual BotFather step.

## Universe Engine

策略选股现已受持久化白名单约束。首批来源为可配置的 QQQ 与 SPY 官方成分文件，支持跨 ETF 去重、
成员删除软停用、本地缓存、每日更新、只读 API 和 Dashboard。新增 ETF 只需扩展配置与相应解析器，
无需改变数据库结构。详见 [`docs/UNIVERSE_ENGINE.md`](docs/UNIVERSE_ENGINE.md)。

## Quality & Mispricing Engine

QMR Engine 仅分析评估时点有效的 QQQ/SPY Universe 成分股，分别计算可解释、版本化的公司质量分和
错杀分，并保留历史评分。符合阈值且无重大基本面风险时只输出 `WATCH`，不输出 BUY/SELL、价格或仓位。
缺少新闻时明确标记 `UNKNOWN`，不会伪装为低风险。API 为 `GET /qmr/candidates`、
`GET /qmr/{symbol}`，Dashboard 为 `/dashboard/qmr`。详见
[`docs/QMR_ENGINE.md`](docs/QMR_ENGINE.md)。

## Recovery Engine

Recovery Engine 仅处理当前 QMR `WATCH` 候选，使用已闭合 5m/15m/30m/60m K 线计算止跌、资金回流、
技术确认、板块同步和大盘环境，并保存完整阶段变化历史。RVOL 按交易时段及同一时刻比较；主动买卖、
大单或全球联动缺失时保持 `PARTIAL/UNKNOWN` 并重新归一化可用因子。输出 Entry 候选状态但不下单、
不管理仓位。API 为 `GET /qmr/recovery`、`GET /qmr/recovery/{symbol}`，Dashboard 复用
`/dashboard/qmr`。详见 [`docs/RECOVERY_ENGINE.md`](docs/RECOVERY_ENGINE.md)。

## Buy Score Engine

Buy Score Engine 只聚合当前 QMR WATCH 与其对应 Recovery 结果，按配置化权重计算 Raw Buy Score，加入
基本面、大盘、板块、失败修复、波动、数据可信度与追涨风险扣分，再通过状态矩阵、迟滞和冷却输出候选
状态及 Top 10/20 排名。它保存排名变化、首次发现价格和观察价格区间；杠杆产品映射仅展示，不改变底层
正股评分或创建订单。API 为 `GET /qmr/buy-scores`、`GET /qmr/ranking`、
`GET /qmr/{symbol}/buy-score`。详见 [`docs/BUY_SCORE_ENGINE.md`](docs/BUY_SCORE_ENGINE.md)。

## QMR 历史回测

Sprint 5 提供 Point-in-Time QMR 事件回放、1/3/5/10/20日收益、MFE/MAE、局部底部捕获、止盈止损与追踪止损矩阵、Walk-Forward、Out-of-Sample、失败案例和分层统计。它只读取已保存的历史信号及 `market_bars`，不会为了改善结果修改 Sprint 1–4 数据。

当前缺少完整历史 QQQ/SPY 成分有效期，因此真实结果必须标记为 `RESEARCH` 和幸存者偏差警告。详见 [`docs/QMR_BACKTEST_ENGINE.md`](docs/QMR_BACKTEST_ENGINE.md)。
