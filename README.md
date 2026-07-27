# Moomoo Quant

美股量化研究与安全模拟交易底座。Sprint 00 仅覆盖行情适配接口、数据库、内部虚拟成交、Moomoo OpenD 只读连接检查、单向 Telegram 通知和 FastAPI 基础接口。

## V1 安全边界

- 不支持真实账户下单，`LIVE` 在配置、Broker 与数据库层永久阻止。
- 不采集、不保存 Moomoo 密码或交易解锁密码。
- Telegram 仅允许单向通知，不包含 Webhook、监听、命令或交易控制。
- `.env` 永不提交；日志和 API 不输出 Secret。
- Moomoo 网页登录与 OpenD API 登录相互独立，OpenD 必须由用户本人安装并登录。

## 环境与安装

目标环境为 Python 3.12。代码也可在 Python 3.9+ 开发环境运行。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

如需执行完整 OpenD API 权限检查，再安装可选依赖：

```bash
python -m pip install -e ".[moomoo]"
```

也可使用 `uv sync --extra dev`。

## 配置、数据库与启动

复制 `.env.example` 后只在本机填写配置。默认数据库为 `data/moomoo_quant.db`，默认模式为 `INTERNAL_PAPER`。

```bash
python scripts/check_environment.py
alembic upgrade head
python scripts/init_database.py
python scripts/smoke_test.py
uvicorn app.main:app --reload
```

接口：`/health`、`/system/config`、`/portfolios`、`/signals`、`/orders`、`/events`。

## 测试

```bash
pytest
```

## Moomoo OpenD

Moomoo 网页已登录不代表 OpenD 可用。请自行安装、启动并登录 OpenD，然后运行：

```bash
python scripts/check_moomoo_connection.py
```

脚本只检查连通性、行情权限及账户类型；发现真实账户时仍显示 `Live trading enabled: NO`，不会执行任何交易。Sprint 00 不自动订阅行情，也不发送模拟订单。

## Telegram

在 `.env` 中手工设置 `TELEGRAM_ENABLED=true`、`TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`。开启但缺少配置时应用拒绝启动。真实发送测试必须由用户主动运行：

```bash
python scripts/test_telegram.py
```

## Docker

```bash
docker compose up --build
```

OpenD 不在容器中运行；容器通过 `MOOMOO_OPEND_HOST` 与 `MOOMOO_OPEND_PORT` 连接宿主机。

## 已知限制

本 Sprint 不含完整策略、特征计算、历史回测、实时订阅、Moomoo 模拟下单、前端、新闻/LLM 或任何实盘能力。SQLite 适合第一阶段单进程研究，后续可迁移 PostgreSQL。
