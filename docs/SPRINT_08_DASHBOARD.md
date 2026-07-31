# Sprint 08 — Dashboard / 公司工作台

## 定位

Dashboard是本机公司内部工作台，用于观察Trade Companion运行、Opportunity、策略状态、数据质量和历史记录。它不提供买卖、订单、持仓操作，也不调用券商交易接口。

## 启动

```bash
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问：

```text
http://127.0.0.1:8000/dashboard
```

不需要Node、Docker或uv。

## 管理员鉴权

```env
DASHBOARD_ADMIN_TOKEN=请设置足够长的随机Token
DASHBOARD_READONLY_PUBLIC=false
```

默认只读页面不公开。浏览器在登录页输入Token后写入HttpOnly、SameSite=Strict的本地Cookie。JSON API也支持`X-Dashboard-Token`请求头。

以下操作始终要求管理员Token：

- 启动和停止Runtime
- 创建Development Issue
- 修改Issue状态

API和HTML不会返回Dashboard Token或Telegram Token。

## 页面

- 工作台：服务状态、心跳、数据库规模、今日统计、最新机会和最近异常。
- 交易机会：按标的、周期、方向、状态、策略、评分和日期查询；详情展示完整快照。
- 运行状态：服务状态、Runtime PID、OpenD连接、最近行情和策略时间；支持幂等启停。
- 策略观察：版本、周期、模板、Signal分布、评分分布、失败Gate和Opportunity数量。
- 数据质量：Watchlist各标的K线覆盖、问题数、Feature与Strategy数据状态。
- 历史报告：日报使用当前聚合数据；周报和月报为占位。
- 开发看板：管理员创建Issue、过滤、查看详情和更新状态。Codex Prompt仅预留，不自动执行。

## API

- `GET /api/dashboard/summary`
- `GET /api/dashboard/data-quality`
- `GET /api/dashboard/strategy-summary`
- `GET /api/development/issues`
- `GET /api/development/issues/{id}`
- `POST /api/development/issues`
- `PATCH /api/development/issues/{id}`

Opportunity查询和Runtime API继续复用Sprint 07接口，并纳入Dashboard鉴权。

## Windows后续部署

- 使用Python 3.9.x和独立venv。
- OpenD由用户本人在同一台Windows工作站登录。
- 建议仅监听`127.0.0.1`；如需局域网访问，应额外配置系统防火墙和反向代理TLS。
- `.env`、SQLite数据库、日志和管理员Token不得提交Git。
- 可使用任务计划程序启动FastAPI和Runtime；不要粗暴终止所有Python进程。
- Dashboard不依赖Docker或Node构建工具。

## 当前限制

- 没有复杂用户系统和权限角色。
- 没有AI Analyst、Candidate Pool、用户自选股或用户反馈入口。
- 日报为简单数据聚合；周报和月报仅占位。
- Development Issue不会自动调用Codex。
- 数据质量缺口使用已有质量Issue统计，不主动下载或修复数据。
- Dashboard不包含任何订单功能。
