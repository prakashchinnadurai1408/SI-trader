"""Trailing price and trading-capacity features for monthly research."""

import numpy as np
import pandas as pd

from .monthly_inputs import TURNOVER

EXPERIMENTS = {
    "sector_momentum": "Sector-relative momentum",
    "downside_risk": "Downside beta and gap risk",
    "trade_capacity": "Trade-capacity buy cap",
}

BUY_PARTICIPATION = 0.005
FACTOR_WEIGHT = 0.20


def trailing_features(prices, tri, decision, members):
    calendar = tri.loc[:decision].tail(64).index
    history = prices.loc[pd.IndexSlice[calendar[0]:decision, :], :]
    history = history.loc[history.index.get_level_values("isin").isin(members.index)]
    def panel(column):
        return history[column].unstack("isin").reindex(index=calendar, columns=members.index)

    adjusted = panel("signal_close")
    output = pd.DataFrame(index=members.index, columns=[
        "relative21", "relative63", "downside_beta", "gap_risk", "median_turnover",
    ], dtype=float)
    for span in (21, 63):
        if len(calendar) <= span:
            continue
        sample = adjusted.tail(span + 1)
        returns = (sample.iloc[-1] / sample.iloc[0] - 1).where(sample.notna().all())
        for _, peers in members.groupby("sector"):
            values = returns.reindex(peers.index).dropna()
            if len(values) >= 3:
                for isin, value in values.items():
                    output.at[isin, f"relative{span}"] = value - values.drop(isin).median()

    benchmark = tri.reindex(calendar).pct_change(fill_method=None)
    negative = benchmark[benchmark.lt(0)]
    if len(negative) >= 12 and negative.var() > 1e-12:
        losses = adjusted.pct_change(fill_method=None).loc[negative.index]
        output["downside_beta"] = losses.apply(
            lambda stock: stock.cov(negative) / negative.var() if stock.notna().all() else np.nan
        )

    gap = (panel("open") * panel("split_ratio") / panel("close").shift() - 1).where(panel("dividend").eq(0))
    output["gap_risk"] = (-gap.clip(upper=0)).quantile(0.90).where(gap.count().ge(45))
    if TURNOVER in history and len(calendar) >= 20:
        turnover = panel(TURNOVER).tail(20)
        output["median_turnover"] = turnover.median().where(turnover.notna().all())
    return output


def ranking_outcomes(prices, tri, dates, signals, size):
    outcomes = {}
    for horizon in (5, 21):
        attempts = observed = wins = 0
        for entry, (scores, _, _, _) in signals.items():
            target = dates.get_loc(entry) + horizon
            if target >= len(dates):
                continue
            group = scores.index[:size]
            attempts += len(group)
            expiry = dates[target]
            start = prices.loc[entry, "signal_close"].reindex(group)
            end = prices.loc[expiry, "signal_close"].reindex(group)
            relative = (end / start - tri.loc[expiry] / tri.loc[entry]).dropna()
            observed += len(relative)
            wins += int(relative.gt(0).sum())
        outcomes[str(horizon)] = {"observed": observed, "attempts": attempts,
                                  "winRatePct": wins / observed * 100 if observed else None}
    return outcomes


def apply_experiment(scores, features, experiment, decision):
    observed = features.reindex(scores.index)
    if experiment == "sector_momentum":
        columns = ["relative21", "relative63"]
    elif experiment == "downside_risk":
        columns = ["downside_beta", "gap_risk"]
    else:
        columns = ["median_turnover"]
    available = observed[columns].notna().all(axis=1)
    if len(scores) and available.mean() < 0.90:
        raise ValueError(f"{EXPERIMENTS[experiment]} has under 90% eligible coverage on {decision.date()}.")
    scores = scores.copy()
    if experiment == "trade_capacity":
        scores["buy_capacity_inr"] = observed["median_turnover"].fillna(0) * BUY_PARTICIPATION
        return scores
    selected = observed.loc[available, columns]
    experimental_rank = selected.rank(pct=True, ascending=experiment == "sector_momentum").mean(axis=1)
    scores["score"] = scores["score"] * (1 - FACTOR_WEIGHT) + experimental_rank.reindex(scores.index).fillna(0.5) * FACTOR_WEIGHT
    return scores.sort_index().sort_values("score", ascending=False, kind="stable")
