# Profit Lock / 利润锁定与资金再配置

Profit Lock 属于 Portfolio / Capital Management 层，不属于 QMR。它不会改变 QMR 信号、交易结果或 `realized_pnl`，只把达到利润阶梯的部分资金从主动交易账本隔离出来。

## 三个资金桶

- `ACTIVE_TRADING`：现有 `SystemPaperAccount`。QMR 与其他主动策略只能使用这里的可用资金。
- `RESERVE`：模拟提现或现金储备。V1 使用 `CASH`，收益为 0，不会自动回流主动交易。
- `LONG_TERM_CORE`：长期核心配置。V1 使用 SPY 虚拟份额，仍承担市场风险，不计入无风险锁定利润。

`Total Wealth = Active Trading Equity + Reserve Value + Long-Term Core Value`

QMR 绩效只读取策略交易；SPY 涨跌与 Reserve 不会进入 QMR CAGR、胜率或 Profit Factor。

## 触发与 High Water Mark

默认初始资金每新增 10% 的累计已实现利润触发一个阶梯。每个新阶梯锁定该阶梯利润的 30%，其中 70% 进入 Reserve、30% 进入 SPY Core。

以 100,000 USD 为例：累计已实现利润首次达到 10,000 时锁定 3,000，其中 Reserve 2,100、Core 900。High Water Mark 记录已经处理的利润阶梯；利润从 10,000 回撤后再次回到 10,000 不会重复触发。只有到达 20,000 才处理下一个阶梯。

如果 Active Cash 不足，状态保留为 `TRIGGERED`，不产生部分流水，也不扣除任何资金。资金扣减、两条分配流水和状态更新在同一数据库事务中完成。

## Core 与 Reserve 估值

Core 仅使用触发时已经保存的 SPY Market Bar。没有可靠价格时，资金保留为 `core_pending_cash`，不会伪造份额、收益或在后续查询时静默补买。Reserve V1 为现金模拟，`reserve_yield=0`。

只有 `reserve_principal` 计入本金回收率。Core 即使上涨也不会触发 `INITIAL_CAPITAL_RECOVERED`。

## 数据与 API

- `capital_management_states`：每个 System Paper Account 的桶状态、HWM、Core 份额和版本。
- `capital_transfers`：追加式内部资金调拨记录，带唯一幂等键。
- `GET /api/capital-management/summary`
- `GET /api/capital-management/transfers`
- `POST /internal/capital-management/process`（管理员、OpenAPI 隐藏）

Dashboard 首页使用一个紧凑的“财富结构”模块展示总财富、主动交易、锁定储备、SPY Core、累计调拨和本金回收率。

## 通知与回测

Telegram 仅把 `PROFIT_LOCK_ALLOCATED`、`INITIAL_CAPITAL_RECOVERED` 作为低频重大事件发送。SPY 日常涨跌、Reserve 日常变化和未达到阈值不会通知。通知复用现有 Paper Event Dispatcher。

`app.capital_management.backtest.compare_profit_lock` 使用同一实现利润路径比较 No Lock、不同锁定比例与 Reserve/Core 配比。输出主动账户回撤、总财富回撤、锁定利润、Core Value、最终总财富和本金回收时点。策略利润始终单独保留。

## 安全边界与限制

- 不连接真实券商，不执行真实提现或 SPY 订单。
- 不允许 Reserve 自动补充 Active Trading。
- V1 不模拟国债收益；Treasury 数据和 `MANUAL_CAPITAL_REDEPLOYMENT` 尚未实现。
- V1 Core 使用内部虚拟份额；没有行情时明确保留待配置现金。
- 参数改变必须修改 `CAPITAL_MANAGEMENT_VERSION`，历史流水不会覆盖。
