# Sprint 12：Platform Foundation

Sprint 12 不改变交易、策略、Feature、回测、Opportunity 或 AI Review 逻辑。它为
QuantPilot 增加统一配置入口、环境校验、Secret 脱敏、结构化滚动日志、Health、
Version、Runtime Diagnostics、Backup 和 System Dashboard。

## 配置中心

统一入口为：

```python
from app.config.settings import settings
```

`app/config/` 按 Database、Runtime、AI、Telegram、Dashboard、Logging 和 Backup
提供只读配置视图。旧的 `app.core.config` 暂时保留为兼容入口。所有配置来自
Pydantic Settings 与 `.env`，业务模块不直接读取 `os.getenv`。

Secret 不进入 `safe_dict()`。API 和 Dashboard 仅显示 `******`，日志 formatter
会清洗敏感键和 Telegram Token 形态。

## Environment 与 Health

```bash
python -m app.cli config
python -m app.cli health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/runtime
```

环境校验分别检查 Python、Database、Telegram、Dashboard、AI Provider、
Runtime 周期和磁盘空间，输出 `PASS / WARNING / FAILED`。可选模块缺少配置时
降级或禁用，不应拖垮其他模块。

## Version Center

```bash
python -m app.cli version
```

版本中心提供 Product、Version、Sprint、Commit、Migration、Build Time、Python、
SQLite Version 和 Git Branch。

## Backup Center

```bash
python -m app.cli backup create
python -m app.cli backup create --type daily
python -m app.cli backup list
python -m app.cli backup verify
```

备份使用 SQLite Online Backup API 创建一致性数据库快照，并连同非敏感配置、
Prompt 和 manifest 压缩为 ZIP。支持 7 份 Daily、4 份 Weekly 保留策略。当前
不上传云端，也不自动删除数据库、K线、Feature 或 Signal。

## Telegram 用户研究范围

每个 Telegram 管理员 ID 有独立的研究股票范围：

```text
/watch add NVDA
/watch remove NVDA
/watchlist
```

`/candidates`、`/candidate`、`/opportunities`、`/symbol`、`/why`、`/review`
和 `/ai_review` 只读取该 Telegram ID 的股票范围。它只是研究数据隔离，不是完整
多租户账号、认证或计费系统。

## Dashboard 与 API

System 页面：`/dashboard/system`

- `GET /api/platform/health`
- `GET /api/platform/runtime`
- `GET /api/platform/version`
- `GET /api/platform/config`
- `GET /api/platform/backups`
- `POST /api/platform/backups`

配置与备份接口需要 Dashboard 管理员 Token。

## Logging

`config/logging.yaml` 描述 Console 与 Rolling File。当前写入 `logs/app.log` 和
`logs/error.log`，默认单文件 5MB、保留 5 份。结构化日志预留 JSON 扩展。

## 已知限制

- 继续使用 SQLite，不支持 PostgreSQL。
- 不包含 Docker、Kubernetes、云部署、Redis、Kafka、Celery。
- Telegram 用户范围不是完整 Multi-user Authentication。
- 不包含 Billing、WebSocket Cluster、Auto Scaling。
- 备份只保存本地 ZIP，不做云端上传。
