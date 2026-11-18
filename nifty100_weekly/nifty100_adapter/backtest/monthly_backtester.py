"""Monthly quality, momentum and low-volatility research backtest."""

import argparse
from dataclasses import asdict, dataclass
import json
import math
import re
from pathlib import Path

import pandas as pd

from .gate_g1 import gate_g1
from .monthly_inputs import FACTORS, VETOES, load_frozen_inputs
from .price_experiments import EXPERIMENTS, apply_experiment, ranking_outcomes, trailing_features
from ..config.indian_cost_model import get_cost_model

WEIGHTS = {"quality": 30, "momentum": 30, "volatility": 20, "value": 8,
           "ownership": 6, "earnings_revisions": 3, "news_sentiment": 3}
BASKET = 12
POSITION_CAP = 0.10
SECTOR_CAP = 0.30
TURNOVER_CAP = 0.30
CASH_BUFFER = 0.05
STOP = 0.15
DRAWDOWN_ALERT = 0.10


@dataclass
class Lot:
    bought: pd.Timestamp
    quantity: int
    basis: float


@dataclass
class Holding:
    symbol: str
    sector: str
    lots: list[Lot]
    peak: float
    stopped: bool = False

    @property
    def quantity(self):
        return sum(lot.quantity for lot in self.lots)

    @property
    def basis_per_share(self):
        return sum(lot.quantity * lot.basis for lot in self.lots) / self.quantity


def score_snapshot(snapshot, prices, weights=None):
    weights = WEIGHTS if weights is None else weights
    frame = snapshot.join(prices[["momentum", "volatility", "close"]], how="left")
    frame = frame.dropna(subset=["momentum", "volatility", "close"])
    eligible = frame.loc[~frame[list(VETOES)].any(axis=1) & frame["turnover_crore"].ge(25)].copy()
    if eligible.empty:
        return eligible.assign(score=pd.Series(dtype=float)), len(frame)
    factors = eligible[list(weights)].copy()
    factors["volatility"] = -factors["volatility"]
    eligible["score"] = factors.rank(pct=True).mul(pd.Series(weights)).sum(axis=1)
    eligible = eligible.sort_index().sort_values("score", ascending=False, kind="stable")
    return eligible, len(frame)


class Portfolio:
    def __init__(self, capital, tax):
        self.cash = capital
        self.tax = tax
        self.model = get_cost_model()
        self.holdings = {}
        self.trades = []
        self.alerts = []

    def quote(self, prices, isin, field):
        if isin not in prices.index:
            raise ValueError(f"Held or selected ISIN {isin} has no quote on {self.day.date()}.")
        return float(prices.at[isin, field])

    def equity(self, prices, field):
        return self.cash + sum(item.quantity * self.quote(prices, isin, field)
                               for isin, item in self.holdings.items())

    def actions(self, prices):
        for isin, item in self.holdings.items():
            split = self.quote(prices, isin, "split_ratio")
            dividend = self.quote(prices, isin, "dividend")
            for lot in item.lots:
                split_quantity = lot.quantity * split
                if abs(split_quantity - round(split_quantity)) > 1e-8:
                    raise ValueError(f"Fractional corporate action needs a cash-in-lieu record for {isin}.")
                lot.quantity = round(split_quantity)
                lot.basis /= split
            item.peak /= split
            self.cash += item.quantity * dividend * (1 - self.tax["dividend_tax"])

    def fee(self, price, quantity, is_buy):
        model = self.model
        value = price * quantity
        brokerage = model.brokerage_min + model.brokerage_rate * value
        statutory = (model.stt_buy + model.stamp_duty_buy) if is_buy else (model.stt_sell + model.stamp_duty_sell)
        return (brokerage * (1 + model.gst_on_brokerage) + value *
                (statutory + model.sebi_charge + model.exchange_tax + model.estimated_slippage)
                + (0 if is_buy else model.dp_charge_sell))

    def sell(self, isin, quantity, price, reason):
        holding = self.holdings[isin]
        fee = self.fee(price, quantity, False)
        remaining = quantity
        taxes = 0.0
        while remaining:
            lot = holding.lots[0]
            sold = min(remaining, lot.quantity)
            long_term = self.day > lot.bought + pd.DateOffset(years=1)
            rate = self.tax["long_term_tax" if long_term else "short_term_tax"]
            taxes += max(0, (price - fee / quantity - lot.basis) * sold) * rate
            lot.quantity -= sold
            remaining -= sold
            if not lot.quantity:
                holding.lots.pop(0)
        self.cash += price * quantity - fee - taxes
        self.record(isin, holding.symbol, "sell", quantity, price, fee, taxes, reason)
        if not holding.lots:
            del self.holdings[isin]

    def buy(self, isin, stock, quantity, price):
        fee = self.fee(price, quantity, True)
        self.cash -= price * quantity + fee
        if isin not in self.holdings:
            self.holdings[isin] = Holding(stock.symbol, stock.sector, [], price)
        self.holdings[isin].lots.append(Lot(self.day, quantity, price + fee / quantity))
        self.record(isin, stock.symbol, "buy", quantity, price, fee, 0, "monthly allocation")

    def record(self, isin, symbol, side, quantity, price, fee, taxes, reason):
        self.trades.append({"date": str(self.day.date()), "isin": isin, "symbol": symbol, "side": side,
                            "quantity": quantity, "open": price, "fees": fee, "tax": taxes, "reason": reason})

    def target_weights(self, scores, snapshot, exposure, signal_day):
        ranks = {isin: rank for rank, isin in enumerate(scores.index, start=1)}
        keep = []
        exits = {}
        for isin, holding in self.holdings.items():
            if holding.stopped:
                exits[isin] = "weekly stop alert"
            elif isin not in snapshot.index or snapshot.loc[isin, list(VETOES)].any():
                exits[isin] = "membership or veto"
            elif isin not in ranks:
                exits[isin] = "filter"
            elif ranks[isin] <= 25:
                keep.append(isin)
            else:
                oldest = holding.lots[0].bought
                age = (signal_day - oldest).days
                if 335 <= age <= 365 and scores.at[isin, "close"] > holding.basis_per_share and exposure > 0:
                    keep.append(isin)
                else:
                    exits[isin] = "rank exit"
        priority = sorted(keep, key=lambda isin: ranks[isin])
        priority.extend(isin for isin in scores.index if isin not in keep and isin not in exits)
        remaining_sector = {}
        weights = {}
        for isin in priority:
            if len(weights) == BASKET or exposure <= 0:
                break
            sector = scores.at[isin, "sector"]
            room = remaining_sector.get(sector, SECTOR_CAP)
            weight = min(POSITION_CAP, exposure / BASKET, room)
            if weight > 1e-9:
                weights[isin] = weight
                remaining_sector[sector] = room - weight
        return weights, exits

    def rebalance(self, prices, scores, snapshot, exposure, signal_day):
        nav = self.equity(prices, "open")
        turnover_room = TURNOVER_CAP * nav
        targets, exits = self.target_weights(scores, snapshot, exposure, signal_day)
        prices_open = {isin: self.quote(prices, isin, "open") for isin in set(self.holdings) | set(targets)}
        for isin in self.holdings:
            if isin in snapshot.index:
                self.holdings[isin].sector = snapshot.at[isin, "sector"]
        desired_shares = {isin: math.floor(nav * weight / prices_open[isin]) for isin, weight in targets.items()}

        for isin in exits:
            holding = self.holdings[isin]
            price = prices_open[isin]
            reason = exits[isin]
            mandatory = reason in ("weekly stop alert", "membership or veto")
            quantity = holding.quantity if mandatory else min(
                holding.quantity, math.floor(max(0, turnover_room) / price)
            )
            if quantity:
                turnover_room -= quantity * price
                self.sell(isin, quantity, price, reason)

        for isin, holding in list(self.holdings.items()):
            price = prices_open[isin]
            quantity = min(max(0, holding.quantity - desired_shares.get(isin, 0)),
                           math.floor(max(0, turnover_room) / price))
            if quantity:
                self.sell(isin, quantity, price, "rebalance trim")
                turnover_room -= quantity * price

        sector_value = {}
        for isin, holding in self.holdings.items():
            sector_value[holding.sector] = sector_value.get(holding.sector, 0) + holding.quantity * prices_open[isin]

        for isin in targets:
            stock = scores.loc[isin]
            price = prices_open[isin]
            current_qty = self.holdings[isin].quantity if isin in self.holdings else 0
            if isin not in self.holdings and len(self.holdings) >= BASKET:
                continue
            cash_budget = max(0, self.cash - CASH_BUFFER * nav)
            sector_room = max(0, SECTOR_CAP * nav - sector_value.get(stock.sector, 0))
            cap = min(max(0, turnover_room), cash_budget, sector_room, stock.get("buy_capacity_inr", math.inf))
            qty = max(0, min(desired_shares[isin] - current_qty, math.floor(cap / price)))
            if qty:
                fixed_fee = self.fee(price, 0, True)
                unit_cost = price + self.fee(price, 1, True) - fixed_fee
                qty = max(0, min(qty, math.floor((cash_budget - fixed_fee) / unit_cost)))
            if qty:
                self.buy(isin, stock, qty, price)
                sector_value[stock.sector] = sector_value.get(stock.sector, 0) + qty * price
                turnover_room -= qty * price

def defensive_exposure(observed):
    month_ends = observed.groupby(observed.index.to_period("M")).last().tail(10)
    if len(month_ends) < 10 or month_ends.index[-1].ordinal - month_ends.index[0].ordinal != 9:
        raise ValueError("The defensive variant needs ten consecutive completed month-end TRI observations.")
    return 0.25 if month_ends.iloc[-1] < month_ends.mean() else 0.95


def month_end_signal(prices, snapshots, tri, decision, weights=None, defensive=False, experiment=None):
    if decision not in snapshots.index.get_level_values("date"):
        raise ValueError(f"Missing point-in-time Nifty 100 snapshot for {decision.date()}.")
    snapshot = snapshots.loc[decision]
    if len(snapshot) != 100:
        raise ValueError(f"{decision.date()} requires exactly 100 point-in-time members.")
    if decision not in prices.index.get_level_values("date"):
        raise ValueError(f"Missing decision prices for {decision.date()}.")
    scores, scoreable = score_snapshot(snapshot, prices.loc[decision], weights)
    observed = tri.loc[:decision]
    vol = observed.pct_change().tail(63).std() * math.sqrt(252)
    if scoreable < 90 or len(observed) < 64 or pd.isna(vol):
        raise ValueError(f"Insufficient history or factor coverage for {decision.date()} ({scoreable}/100).")
    exposure = 0.95 * min(1.0, 0.18 / vol) if vol else 0.95
    if observed.iloc[-1] / observed.tail(21).max() - 1 <= -0.10:
        exposure = min(exposure, 0.50)
    if defensive:
        exposure = defensive_exposure(observed)
    if experiment:
        scores = apply_experiment(scores, trailing_features(prices, tri, decision, snapshot[["sector"]]), experiment, decision)
    return scores, snapshot, float(exposure), scoreable


def build_signals(prices, snapshots, tri, dates, complete_months, weights=None, defensive=False, experiment=None):
    sessions = pd.Series(tri.index, index=tri.index.to_period("M"))
    signals = {}
    coverage = []
    for month in complete_months - 1:
        previous = sessions.loc[month]
        decision = previous.iloc[-1] if isinstance(previous, pd.Series) else previous
        scores, snapshot, exposure, scoreable = month_end_signal(prices, snapshots, tri, decision, weights, defensive, experiment)
        execution = dates[dates.to_period("M") == month + 1][0]
        signals[execution] = (scores, snapshot, exposure, decision)
        coverage.append({"decision": str(decision.date()), "execution": str(execution.date()),
                         "scoreable": scoreable, "eligible": len(scores), "target_exposure": exposure})
    return signals, coverage


def research_window(tri, start, end):
    if any(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month) is None for month in (start, end)):
        raise ValueError("Start and end must use YYYY-MM.")
    complete_months = pd.period_range(start, end, freq="M")
    if not len(complete_months):
        raise ValueError("Choose an ordered start and end month.")
    date_months = tri.index.to_period("M")
    required_months = pd.period_range(complete_months[0] - 1, complete_months[-1] + 1, freq="M")
    if not required_months.isin(date_months).all():
        raise ValueError("TRI needs every test month plus the preceding and following months.")
    dates = tri.index[date_months.isin(complete_months)]
    return complete_months, dates


def run(folder, start, end, capital, weights=None, defensive=False):
    hashes, inputs = load_frozen_inputs(folder)
    return run_prepared(inputs, hashes, start, end, capital, weights, defensive)


def run_prepared(inputs, hashes, start, end, capital, weights=None, defensive=False, experiment=None):
    if experiment is not None and (experiment not in EXPERIMENTS or weights is not None or defensive):
        raise ValueError("Select one price-input experiment against the fixed baseline.")
    if defensive and weights is not None:
        raise ValueError("Test the defensive overlay separately with the frozen factor weights.")
    manifest, prices, snapshots, tri = inputs
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("Starting capital must be finite and positive.")
    complete_months, dates = research_window(tri, start, end)
    baseline = tri.index[tri.index < dates[0]][-1]
    signals, coverage = build_signals(prices, snapshots, tri, dates, complete_months, weights, defensive, experiment)
    week_ends = set(dates.to_series().groupby(dates.to_period("W-FRI")).max())
    ledger = [{"date": baseline, "equity": capital, "cash": capital, "benchmark": float(tri.loc[baseline])}]
    peak_nav = capital
    portfolio = Portfolio(capital, manifest)
    price_days = set(prices.index.get_level_values("date"))
    turnover = []
    for day in dates:
        if day not in price_days:
            raise ValueError(f"Missing NSE prices for benchmark session {day.date()}.")
        portfolio.day = day
        quotes = prices.loc[day]
        portfolio.actions(quotes)
        if day in signals:
            first_trade = len(portfolio.trades)
            open_nav = portfolio.equity(quotes, "open")
            portfolio.rebalance(quotes, *signals[day])
            new_trades = portfolio.trades[first_trade:]
            traded = sum(trade["open"] * trade["quantity"] for trade in new_trades) / open_nav
            turnover.append(traded * 100)
            if traded > TURNOVER_CAP + 1e-9:
                portfolio.alerts.append({"date": str(day.date()), "type": "forced_exit_turnover", "value": traded})
        nav = portfolio.equity(quotes, "close")
        peak_nav = max(peak_nav, nav)
        ledger.append({"date": day, "equity": nav, "cash": portfolio.cash, "benchmark": float(tri.loc[day])})
        for isin, holding in portfolio.holdings.items():
            close = portfolio.quote(quotes, isin, "close")
            holding.peak = max(holding.peak, close)
            if day in week_ends and not holding.stopped and close <= holding.peak * (1 - STOP):
                holding.stopped = True
                portfolio.alerts.append({"date": str(day.date()), "type": "weekly_stop", "symbol": holding.symbol})
        if day in week_ends and nav <= peak_nav * (1 - DRAWDOWN_ALERT):
            portfolio.alerts.append({"date": str(day.date()), "type": "weekly_drawdown", "value": 1 - nav / peak_nav})
    equity = pd.DataFrame.from_records(ledger).set_index("date")
    strategy_name = "monthly_defensive" if defensive else "monthly_challenger" if weights is not None else "monthly_baseline"
    if experiment:
        strategy_name = "monthly_" + experiment
    gate = gate_g1(equity, complete_months, manifest["mode"] == "research" and strategy_name == "monthly_baseline")
    if strategy_name != "monthly_baseline":
        gate["qualification_note"] = "An experimental variant cannot authorize the frozen Gate G1 pilot."
    return equity, {
        "gate_g1": gate, "strategy": strategy_name,
        "factor_weights": WEIGHTS if weights is None else weights,
        "input_sha256": hashes,
        "start_month": str(complete_months[0]), "end_month": str(complete_months[-1]),
        "starting_capital": capital, "coverage": coverage, "trades": portfolio.trades, "alerts": portfolio.alerts,
        "transaction_cost_model": asdict(portfolio.model),
        "data_manifest": manifest,
        "average_rebalance_turnover_pct": sum(turnover) / len(turnover) if turnover else None,
        "ranking_outcomes": ranking_outcomes(prices, tri, dates, signals, BASKET),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--start", required=True, help="First test month (YYYY-MM)")
    parser.add_argument("--end", required=True, help="Last test month (YYYY-MM)")
    parser.add_argument("--capital", type=float, default=1000000)
    parser.add_argument("--out", type=Path, required=True, help="New report directory")
    experiment = parser.add_mutually_exclusive_group()
    experiment.add_argument("--challenger", type=Path, help="Exported AI proposal, evaluated for research only")
    experiment.add_argument("--defensive", action="store_true", help="Test the 10-month trend overlay")
    args = parser.parse_args()
    try:
        if args.challenger:
            from ..strategy_builder import read_challenger
            weights = read_challenger(args.challenger)
        else:
            weights = None
        equity, report = run(args.data, args.start, args.end, args.capital, weights, args.defensive)
        args.out.mkdir(parents=True, exist_ok=False)
        equity.to_csv(args.out / "daily_equity.csv")
        (args.out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    except (ValueError, OSError) as error:
        parser.exit(1, f"Monthly backtest: {error}\n")
    print(json.dumps(report["gate_g1"], indent=2))


if __name__ == "__main__":
    main()
