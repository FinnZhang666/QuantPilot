from decimal import Decimal


D = Decimal


def compare_profit_lock(initial_capital, realized_profit_path, scenarios, core_return_path=None,
                        periods_per_year=252):
    """Pure capital-policy comparison; strategy returns remain untouched."""
    initial = D(str(initial_capital))
    output = []
    for scenario in scenarios:
        trigger = D(str(scenario["trigger_ratio"])) * initial
        lock_ratio = D(str(scenario["lock_ratio"]))
        reserve_ratio = D(str(scenario["reserve_ratio"]))
        active, reserve, core, hwm = initial, D("0"), D("0"), D("0")
        peak_active, max_active_dd = initial, D("0")
        peak_total, max_total_dd = initial, D("0")
        recovery_index = None
        previous_profit = D("0")
        for index, raw_profit in enumerate(realized_profit_path):
            profit = D(str(raw_profit))
            active += profit - previous_profit
            previous_profit = profit
            crossed = (max(D("0"), profit) // trigger) * trigger if trigger else D("0")
            if crossed > hwm:
                locked = (crossed - hwm) * lock_ratio
                active -= locked; reserve += locked * reserve_ratio; core += locked * (D("1") - reserve_ratio)
                hwm = crossed
            if core_return_path and index < len(core_return_path):
                core *= D("1") + D(str(core_return_path[index]))
            total = active + reserve + core
            peak_active = max(peak_active, active); peak_total = max(peak_total, total)
            max_active_dd = min(max_active_dd, active / peak_active - 1)
            max_total_dd = min(max_total_dd, total / peak_total - 1)
            if recovery_index is None and reserve >= initial: recovery_index = index
        periods = max(1, len(realized_profit_path))
        years = periods / periods_per_year
        strategy_final = initial + previous_profit
        total_final = active + reserve + core
        strategy_cagr = (float(strategy_final / initial) ** (1 / years) - 1) if strategy_final > 0 else -1
        wealth_cagr = (float(total_final / initial) ** (1 / years) - 1) if total_final > 0 else -1
        output.append({"name": scenario["name"], "strategy_profit": str(previous_profit),
            "strategy_cagr": strategy_cagr, "total_wealth_cagr": wealth_cagr,
            "active_equity": str(active), "locked_profit": str(reserve), "core_value": str(core),
            "final_total_wealth": str(total_final), "active_account_drawdown": str(max_active_dd),
            "total_wealth_drawdown": str(max_total_dd), "initial_capital_recovery_index": recovery_index})
    return output
