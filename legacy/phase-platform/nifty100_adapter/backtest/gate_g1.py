"""Evaluate the frozen Gate G1 criteria on a paired daily equity series."""

import pandas as pd


def gate_g1(equity, complete_months, research_data):
    """Equity and TRI are paired at each date, including the opening baseline."""
    years = (equity.index[-1] - equity.index[0]).days / 365.2425
    nav = equity["equity"]
    tri = equity["benchmark"]
    strategy_cagr = float((nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1)
    benchmark_cagr = float((tri.iloc[-1] / tri.iloc[0]) ** (1 / years) - 1)
    monthly = equity.groupby(equity.index.to_period("M")).last()
    monthly = monthly.loc[monthly.index.isin(complete_months.insert(0, complete_months[0] - 1))]
    returns = monthly.div(monthly.shift(36)).dropna()
    wins = int((returns["equity"] > returns["benchmark"] + 1e-12).sum())
    windows = len(returns)
    win_rate = wins / windows if windows else None
    drawdown = float((1 - nav.div(nav.cummax())).max())
    spread = strategy_cagr - benchmark_cagr
    passed = spread >= 0.01 and win_rate is not None and win_rate >= 0.60 and drawdown <= 0.30
    eligible = research_data and len(complete_months) >= 60 and windows > 0
    return {
        "status": ("pass" if passed else "fail") if eligible else "inconclusive",
        "research_data_declared": research_data,
        "complete_months": len(complete_months),
        "net_cagr": strategy_cagr,
        "benchmark_cagr": benchmark_cagr,
        "annualized_excess": spread,
        "rolling_36m_wins": wins,
        "rolling_36m_windows": windows,
        "rolling_36m_win_rate": win_rate,
        "rolling_windows_overlap": True,
        "maximum_daily_drawdown": drawdown,
    }
