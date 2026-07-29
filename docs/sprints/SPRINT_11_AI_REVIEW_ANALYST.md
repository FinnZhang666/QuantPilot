# Sprint 11：AI Review Analyst

## 定位

AI Review Analyst 位于 Opportunity Outcome 之后：

```text
Opportunity → Opportunity Review → AI Review Analyst
            → AI Analysis Record → Human Review → Development Board
```

它只分析系统已保存的 Opportunity、Outcome、Feature、Strategy、Market Regime、
Candidate Pool 和历史统计。它不扫描全市场，不引入新闻，不预测价格，不修改策略参数
或代码，不调用 Codex，也不会生成订单。

所有结果必须区分事实、推断、不确定性和建议调查项。AI 分析仅供研究与复盘，
不构成投资建议。

## Provider

- `Disabled`：默认状态，不调用外部服务，不生成虚假分析。
- `mock`：仅供自动化测试，界面明确显示 `TEST / MOCK OUTPUT`，不计入真实统计。
- `openai_compatible`：兼容标准 `/v1/chat/completions` API。
- `local`：使用相同协议连接本机模型，例如 `http://127.0.0.1:11434/v1`。

真实 Key 只能写入项目根目录 `.env`。`.env` 已被 Git 忽略，API、Dashboard、
CLI 和日志不会返回 Key。

## 配置

```text
AI_REVIEW_ENABLED=false
AI_REVIEW_PROVIDER=mock
AI_REVIEW_BASE_URL=
AI_REVIEW_API_KEY=
AI_REVIEW_MODEL=
AI_REVIEW_TIMEOUT_SECONDS=60
AI_REVIEW_MAX_RETRIES=2
AI_REVIEW_BATCH_SIZE=20
AI_REVIEW_MIN_WINDOW=1D
AI_REVIEW_PROMPT_VERSION=v1
AI_REVIEW_STORE_RAW_RESPONSE=true
AI_REVIEW_AUTO_RUN=false
AI_REVIEW_ADMIN_ONLY=true
```

启用真实 Provider 前必须同时配置 Base URL 和模型。`local` 模式允许空 API Key。

## 输入与审计

输入由严格 Pydantic Schema 组成，不会直接序列化 ORM 对象。每次分析保存：

- 实际结构化输入快照和稳定 SHA-256 Hash
- Prompt 版本和 Prompt Hash
- Provider、模型和分析版本
- 状态、延迟、Token 数、重试数和安全错误摘要
- 结构化输出与可选原始响应

相同 Review、输入、Provider 和模型不会重复生成分析。

## CLI

```bash
python -m app.cli ai-review pending
python -m app.cli ai-review run --limit 20
python -m app.cli ai-review run --review-id 1
python -m app.cli ai-review run --symbol SOXL
python -m app.cli ai-review show --id 1
python -m app.cli ai-review retry --id 1
python -m app.cli ai-review statistics
```

## API

所有接口均受 Dashboard 管理员 Token 保护：

```text
POST /api/ai-review/run
GET  /api/ai-review/pending
GET  /api/ai-review
GET  /api/ai-review/{id}
POST /api/ai-review/{id}/retry
GET  /api/ai-review/statistics
```

## Dashboard 与 Telegram

- `/dashboard/ai-reviews`
- `/dashboard/ai-reviews/{analysis_id}`

Telegram 管理员命令：

```text
/ai_review
/ai_review SOXL
/ai_review pending
/ai_review failed
/ai_review 123
```

Telegram 不展示 Mock 分析，也不会发送完整原始 JSON。

## Runtime

只有 `AI_REVIEW_ENABLED=true` 且 `AI_REVIEW_AUTO_RUN=true` 时才启用后台分析。
调度器使用独立后台线程，不阻塞行情、Review Engine 或 Opportunity Pipeline。
默认不会自动扫描并分析全部历史记录。

## 测试

普通测试完全使用 Mock 或注入 Provider，不访问真实外部 API：

```bash
python -m pytest
python -m pytest tests/unit/test_ai_review.py tests/integration/test_ai_review_api.py
```

## 当前限制

- 不提供自动参数优化。
- 不自动建立 Development Board Issue，只提供纯转换接口。
- 不实现新闻、外部事实检索或自由聊天。
- 不自动修改代码、策略或系统配置。
- 不调用 Codex。
- 不执行模拟或真实订单。
