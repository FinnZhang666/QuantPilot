# Sprint 13：Research Center

Research Center 是 Trade Companion 的统一研究入口。它不新增策略、AI Provider 或交易
能力，而是围绕每个 Opportunity 保存完整、可追溯的研究档案。

## Research Workspace

每个 Opportunity 对应唯一 Workspace，包含 Candidate、Opportunity、Review、
AI Review、Investigation、Evidence、Attachments、Timeline、Manual Notes 和
Similar Reviews。

新 Opportunity 创建后自动建立 Workspace。升级前的历史 Opportunity 会在首次
进入 Research API、Dashboard 或执行 `research show` 时幂等回填。

## Timeline

时间轴汇总 Candidate Created、Opportunity Generated、Opportunity Status、
Telegram Sent、Review Completed、AI Review、Manual Note、Attachment Added
和 Investigation Created / Updated。事件具有来源唯一性，重复同步不会重复写入。

## Evidence Center

Evidence 保存 Feature、Strategy、Decision、Market Regime、Return、MFE、MAE、
Price Path 和 AI Review Conclusion，并可追溯到具体来源记录。

## Notes、Attachments 与 Investigation

Manual Note 支持 `OBSERVATION`、`HYPOTHESIS`、`VALIDATION`、`EXPERIENCE` 和
`NEXT_STEP`。它不由 AI 自动生成。

附件支持 PNG、JPG/JPEG、CSV、JSON 和 Markdown，单文件最大10MB。文件名会清洗，
内容保存 SHA-256，并写入被 Git 忽略的 `data/research_attachments/`。不支持OCR。

AI Review Investigation Item 会进入 Investigation Board，状态为 `NEW`、`OPEN`、
`TESTING`、`VERIFIED`、`REJECTED`、`CLOSED`。状态只能由管理员修改。

## Similarity

相似度使用 Direction、Strategy、Timeframe、Market Regime、Score、Confidence
和已有 Review Return，返回前10个历史案例。它不调用AI，不使用未来数据，也不把
缺失值补成0。

## CLI

```bash
python -m app.cli research show
python -m app.cli research show --symbol SOXL
python -m app.cli research timeline --id 1
python -m app.cli research note --id 1 --type OBSERVATION --content "观察成交量"
python -m app.cli research similarity --id 1
```

## API 与 Dashboard

Dashboard：`/dashboard/research`

- `GET /api/research`
- `GET /api/research/{id}`
- `GET /api/research/{id}/timeline`
- `POST /api/research/{id}/notes`
- `POST /api/research/{id}/attachments`
- `GET /api/research/{id}/similarity`
- `GET /api/research/{id}/investigations`
- `PATCH /api/research/investigations/{id}`

全部要求 Dashboard 管理员 Token。

## 明确不做

不自动修改策略、参数或代码；不调用Codex；不自动创建Git Issue；不自动交易；
不做新闻分析、OCR、云同步或新的多用户权限功能。
