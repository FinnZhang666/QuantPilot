# QMR Backtest Report

真实数据库最终验收运行：`run_id=2`  
范围：2016-08-24 至 2026-08-24  
源模型：`buy-score-v1`  
策略版本：`QMR-v1.0`

## 结论

**QMR Strategy Status：RESEARCH**

当前真实数据库没有历史 `buy_scores`，也没有带有效期的历史 QQQ/SPY 成分记录。因此本次运行验证了迁移、任务、指标、持久化和报告流程，但没有统计样本，不能评价策略优势，更不能标记 `VALIDATED` 或 `REJECTED`。

## 核心问题

1. 历史触发：0。
2. EARLY / CONFIRMED / STRONG：0 / 0 / 0。
3. 胜率最高级别：无法计算。
4. 期望收益最高级别：无法计算。
5. 平均距离局部最低点：无法计算。
6. 买入后平均最大回撤：无法计算。
7. 1/3/5/10/20日表现：全部 `MISSING`（样本为0）。
8. 最佳平均持有时间：无法计算。
9. 最佳止盈止损组合：无法计算。
10. 最佳行业：无法计算。
11. 最佳市场状态：无法计算。
12. 最有效失败过滤条件：无法计算。
13. In-Sample / Out-of-Sample：`INSUFFICIENT_YEARS`。
14. 是否达到 VALIDATED：否。缺少历史事件、OOS正收益、PF、足够样本和无幸存者偏差的Universe证据。

## 覆盖与限制

- 请求覆盖：10年。
- 实际信号覆盖：无。
- 历史Universe：`UNAVAILABLE`。
- Point-in-Time结构检查：通过；没有越界事件。
- 估算存储上限：52,492,813 bytes；实际没有复制 market bars。
- 所有统计均保留为缺失值，没有用0伪装收益。

下一步需要先补充可信的历史 QQQ/SPY 成分有效期，并以 Point-in-Time 方式生成历史 Quality、Mispricing、Recovery 和 Buy Score，之后再运行正式研究回测。
