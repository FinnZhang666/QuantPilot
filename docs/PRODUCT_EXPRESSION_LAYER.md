# Trade Companion 产品表达层

股票分析页采用“结论优先、事实可追溯、缺失不补写”的表达方式。表达层只翻译已保存的 QMR、Buy Score、Exit、Market Context、资金流、基本面和 Trade Plan 数据，不重新运行策略，也不改变任何交易结论。

## 页面认知顺序

1. 识别交易标的、资产类型、底层资产和行业基准。
2. Decision Summary 同屏展示当前状态、QMR、质量、估值、Global、Sector、Stock、Buy Score、Exit Risk 与最终建议。
3. 分开展示支持因素与风险限制。
4. 显示关键价位；仅在 Trade Plan 保存了可靠入场、失效和目标价时计算风险收益比。
5. 展开公司质量、同业估值、价值陷阱、市场/行业/资金事实。
6. 技术细节、数据源、缺失项和模型版本放在可折叠审计区。

## 单一事实来源

`StockAnalysisService` 生成 `dashboard-stock-analysis-v2` 读模型。Dashboard 和 Telegram Agent 都读取同一份双语 `presentation` 字典，因此不会分别解释状态。所有状态码保留，中文和英文标签只是展示层。

## 估值与价值陷阱

估值沿用 QMR 已保存的比较层级：显式同业、行业、板块、市场、公司历史。页面显示实际使用层级、样本数、置信度和覆盖率；没有可比数据时显示“数据不足”。便宜不是独立买入条件，价值陷阱标记仍来自现有 QMR 规则。

## 风险收益与数据时效

风险收益比不使用 52 周高低点。缺少可靠 Trade Plan 价位时返回 `UNAVAILABLE`。页面同时显示最新数据时间及 `FRESH / DELAYED / STALE` 状态，并列出各引擎模型版本和缺失模块。

## 边界

- 不改变 QMR、Global、Sector、Stock、Money Flow 或 Exit Engine。
- 不调用 AI 生成事实或买卖结论。
- 不伪造同业、价格、指标或目标。
- 主动分析仍允许不在 QMR 自动 Universe 中的标的，并明确标记范围。
