"""Weekly delivery backtester for Nifty 100 universe.

Implements the weekly scoring pipeline as defined in BRD Section 27.5:
1. Universe: Nifty 100 constituents
2. Filters: liquidity, ASM/GSM, regulatory
3. Vetoes: pledging, legal cases, regulatory actions
4. Score: weighted sum of enabled parameters
5. Cost-and-tax edge check
6. Select top N for weekly basket

Also includes Indian cost model integration and STCG tax.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ..config.indian_cost_model import IndianCostModel, get_cost_model
from ..config.parameter_catalogue import (
    PARAMETER_CATALOGUE,
    get_enabled_parameters,
    get_parameters_by_role,
    RoleType,
    validate_weight_total,
)

# Cost-model rate parameters are model inputs, not per-stock FILTER/VETO checks.
RATES_SET = {"stt_rate_equity", "stcg_tax_rate", "brokerage_rate_param"}


class UniverseFilter:
    """Filters applied to Nifty 100 universe each week."""

    @staticmethod
    def apply_liquidity_filter(
        stocks: pd.DataFrame,
        min_turnover_crore: float = 25.0
    ) -> pd.DataFrame:
        """Filter stocks by minimum daily turnover (liquidity floor)."""
        if "daily_turnover_crore" not in stocks.columns:
            raise ValueError("Stocks DataFrame must contain 'daily_turnover_crore' column")

        filtered = stocks[stocks["daily_turnover_crore"] >= min_turnover_crore].copy()
        return filtered

    @staticmethod
    def apply_asm_gsm_filter(stocks: pd.DataFrame) -> pd.DataFrame:
        """Filter stocks under ASM (Additional Surveillance Measure) or GSM (Graded Surveillance Measure)."""
        if "asm_status" not in stocks.columns:
            # If no ASM data, assume all pass (conservative for backtest)
            return stocks

        filtered = stocks[~stocks["asm_status"].str.contains("ASM|GSM", case=False, na=False)].copy()
        return filtered

    @staticmethod
    def apply_legal_surveillance_filter(stocks: pd.DataFrame) -> pd.DataFrame:
        """Filter stocks with pending serious legal or regulatory action."""
        if "has_pending_legal" not in stocks.columns:
            return stocks

        filtered = stocks[~stocks["has_pending_legal"]].copy()
        return filtered


class VetoChecker:
    """Applies veto rules that automatically disqualify stocks."""

    def __init__(self, cost_model: Optional[IndianCostModel] = None):
        self.cost_model = cost_model or get_cost_model()

    def check_pledging_veto(self, stocks: pd.DataFrame) -> pd.DataFrame:
        """Veto if promoter pledging > configured threshold (default 25%)."""
        if "promoter_pledging_pct" not in stocks.columns:
            return stocks

        filtered = stocks[stocks["promoter_pledging_pct"] <= 25].copy()
        filtered["veto_pledging"] = stocks["promoter_pledging_pct"] > 25
        return filtered

    def check_legal_cases_veto(self, stocks: pd.DataFrame) -> pd.DataFrame:
        """Veto if serious legal cases against directors/promoters."""
        if "legal_cases_directors" not in stocks.columns:
            return stocks

        filtered = stocks[~stocks["legal_cases_directors"]].copy()
        filtered["veto_legal"] = stocks["legal_cases_directors"]
        return filtered

    def check_regulatory_actions_veto(self, stocks: pd.DataFrame) -> pd.DataFrame:
        """Veto if regulatory actions from SEBI/RBI/NSE/BSE."""
        if "regulatory_actions" not in stocks.columns:
            return stocks

        filtered = stocks[~stocks["regulatory_actions"]].copy()
        filtered["veto_regulatory"] = stocks["regulatory_actions"]
        return filtered

    def check_cost_vs_edge_veto(
        self,
        stocks: pd.DataFrame,
        buy_price: float,
        expected_holding_weeks: int = 1
    ) -> pd.DataFrame:
        """Veto if net edge after costs+tax ≤ 0.

        For weekly delivery: holding period = 1 week.
        After adjusting brokerage, STT, STCG 20%, and slippage,
        if expected return doesn't cover costs, stock is vetoed.
        """
        # Calculate approximate costs for a round trip
        # Assuming stock at price level, we calculate cost % roundtrip
        roundtrip_cost_pct = self.cost_model.total_roundtrip_cost_pct

        # Also add STCG tax on potential gain
        # For edge check, we need to know: if we gain X%, after 20% tax and costs,
        # do we still have positive edge?

        # Simplified: calculate cost-adjusted expected return
        # If a stock has historical weekly momentum of M%,
        # gross gain ≈ M%, costs ≈ roundtrip_cost_pct + STCG on gain

        # For the veto check, we estimate:
        # net_edge = expected_gross_return - total_costs_including_tax
        # If net_edge ≤ 0, veto

        # In backtest, we'll calculate this per stock based on its price
        # For now, apply a flat cost check

        cost_pct = roundtrip_cost_pct / 100  # Convert to decimal

        # Mark all stocks for cost check (they'll be evaluated in score pipeline)
        stocks = stocks.copy()
        stocks["cost_pct"] = cost_pct
        stocks["veto_cost_edge"] = False  # Will be set by score pipeline
        return stocks


class ScoreCalculator:
    """Calculates weighted scores for Nifty 100 stocks.

    Applies the full 48-parameter catalogue:
    - SCORE parameters contribute weight to the raw score
    - FILTER parameters disqualify stocks that fall outside bounds
    - VETO parameters automatically exclude stocks
    """

    def __init__(self, cost_model: Optional[IndianCostModel] = None):
        self.cost_model = cost_model or get_cost_model()
        self.enabled_params = get_enabled_parameters()
        self.veto_params = get_parameters_by_role(RoleType.VETO)
        self.score_params = get_parameters_by_role(RoleType.SCORE)
        self.filter_params = get_parameters_by_role(RoleType.FILTER)

    def apply_vetoes(self, stock_data: Dict[str, float]) -> bool:
        """Return True if the stock passes all VETO checks (not vetoed)."""
        for param in self.veto_params:
            value = stock_data.get(param.parameter_key)
            if value is None or pd.isna(value):
                continue
            # VETO params are boolean: True means exclude
            if bool(value):
                return False
        return True

    def apply_filters(self, stock_data: Dict[str, float]) -> bool:
        """Return True if the stock passes all FILTER checks."""
        for param in self.filter_params:
            value = stock_data.get(param.parameter_key)
            if value is None or pd.isna(value):
                continue
            if param.min_value is not None and value < param.min_value:
                return False
            if param.max_value is not None and value > param.max_value:
                return False
        return True

    def calculate_raw_score(self, stock_data: Dict[str, float]) -> float:
        """Calculate weighted raw score for a stock.

        For each SCORE-type parameter, if the stock's value is within acceptable range,
        add the parameter's weight. If outside range, don't add weight.
        """
        score = 0.0

        for param in self.score_params:
            value = stock_data.get(param.parameter_key)
            if pd.isna(value):
                continue

            # Check bounds
            if param.min_value is not None and value < param.min_value:
                continue  # Stock doesn't meet minimum
            if param.max_value is not None and value > param.max_value:
                continue  # Stock exceeds maximum

            # Stock qualifies for this parameter's weight
            score += param.weight

        return score

    def calculate_score(self, stock_row: pd.Series) -> float:
        """Calculate score from a DataFrame row of stock fundamentals/prices."""
        stock_data = stock_row.to_dict()
        return self.calculate_raw_score(stock_data)


class CostEdgeChecker:
    """Checks cost-and-tax edge for each stock."""

    def __init__(self, cost_model: IndianCostModel):
        self.cost_model = cost_model

    def check_edge(self,
                   expected_weekly_return_pct: float,
                   buy_price: float,
                   sell_price: float,
                   quantity: int) -> Dict[str, any]:
        """Check if the trade has positive net edge after costs and tax.

        Returns dict with 'pass' boolean and breakdown.
        """
        # Calculate net P&L using the cost model
        pnl_dict = self.cost_model.calculate_net_pnl(
            buy_price=buy_price,
            sell_price=sell_price,
            quantity=quantity
        )

        gross_pnl = pnl_dict["gross_pnl"]
        net_after_tax = pnl_dict["net_after_tax"]
        total_costs = pnl_dict["total_costs"]

        # Calculate expected return percentages
        total_investment = buy_price * quantity
        gross_return_pct = (gross_pnl / total_investment) * 100 if total_investment > 0 else 0
        net_return_pct = (net_after_tax / total_investment) * 100 if total_investment > 0 else 0

        # Edge = net return after ALL costs
        # Pass if net return > 0 (positive edge after costs+tax)
        edge_pct = net_return_pct
        passes = edge_pct > 0

        return {
            "passes": passes,
            "edge_pct": round(edge_pct, 2),
            "gross_return_pct": round(gross_return_pct, 2),
            "total_costs_pct": round(
                (total_costs / total_investment) * 100 if total_investment > 0 else 0, 2
            ),
            "cost_breakdown": pnl_dict["breakdown"],
            "gross_pnl": gross_pnl,
            "net_after_tax": net_after_tax,
            "stcg_tax": pnl_dict["stcg_tax"],
        }


class WeeklyBacktester:
    """Main weekly backtester orchestrator."""

    def __init__(
        self,
        universe: pd.DataFrame,
        cost_model: Optional[IndianCostModel] = None,
        top_n: int = 10,
        min_liquidity_crore: float = 25.0
    ):
        self.universe = universe.copy()
        self.cost_model = cost_model or get_cost_model()
        self.top_n = top_n
        self.min_liquidity_crore = min_liquidity_crore

        self.filters = UniverseFilter()
        self.veto_checker = VetoChecker(self.cost_model)
        self.score_calc = ScoreCalculator(self.cost_model)
        self.edge_checker = CostEdgeChecker(self.cost_model)

    def run_weekly_pipeline(self) -> Dict[str, any]:
        """Run the complete weekly selection pipeline.

        Returns selection results with scores, costs, and edge analysis.
        """
        print(f"=== Weekly Backtest Run: {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
        print(f"Universe size: {len(self.universe)} stocks")
        print(f"Top N selection: {self.top_n}")
        print(f"Minimum liquidity: ₹{self.min_liquidity_crore} crore daily turnover")
        print()

        # Step 1: Apply liquidity filter
        universe_filtered = self.filters.apply_liquidity_filter(
            self.universe,
            min_turnover_crore=self.min_liquidity_crore
        )
        print(f"After liquidity filter (≥₹{self.min_liquidity_crore} crore): {len(universe_filtered)} stocks")

        # Step 2: Apply ASM/GSM filter
        universe_filtered = self.filters.apply_asm_gsm_filter(universe_filtered)
        print(f"After ASM/GSM filter: {len(universe_filtered)} stocks")

        # Step 3: Apply legal surveillance filter
        universe_filtered = self.filters.apply_legal_surveillance_filter(universe_filtered)
        print(f"After legal surveillance filter: {len(universe_filtered)} stocks")

        # Step 4: Apply veto rules
        # Veto 1: Promoter pledging
        universe_filtered = self.veto_checker.check_pledging_veto(universe_filtered)
        # Veto 2: Legal cases
        universe_filtered = self.veto_checker.check_legal_cases_veto(universe_filtered)
        # Veto 3: Regulatory actions
        universe_filtered = self.veto_checker.check_regulatory_actions_veto(universe_filtered)

        # Step 4b: Apply all catalogue FILTER and VETO parameters
        catalogue_vetoed = set()
        filter_stats_detail = {}
        for param in self.score_calc.veto_params:
            if param.parameter_key in RATES_SET:
                continue  # Rate parameters are cost-model inputs, not stock vetoes
            failures = set()
            for _, row in universe_filtered.iterrows():
                value = row.get(param.parameter_key)
                if value is None or pd.isna(value):
                    continue
                if bool(value):
                    failures.add(row.get("symbol", row.name))
            catalogue_vetoed.update(failures)
            filter_stats_detail[param.parameter_key] = len(failures)
        for param in self.score_calc.filter_params:
            if param.parameter_key in RATES_SET:
                continue
            failures = set()
            for _, row in universe_filtered.iterrows():
                value = row.get(param.parameter_key)
                if value is None or pd.isna(value):
                    continue
                if (param.min_value is not None and value < param.min_value) or \
                   (param.max_value is not None and value > param.max_value):
                    failures.add(row.get("symbol", row.name))
            catalogue_vetoed.update(failures)
            filter_stats_detail[param.parameter_key] = len(failures)

        if catalogue_vetoed:
            universe_filtered = universe_filtered.loc[
                ~universe_filtered["symbol"].isin(catalogue_vetoed)
            ].copy()

        vetoed_count = len(self.universe) - len(universe_filtered)
        print(f"After veto rules (pledging/legal/regulatory + catalogue filters/vetoes): "
              f"{len(universe_filtered)} stocks ({vetoed_count} vetoed)")
        if filter_stats_detail:
            detail = ", ".join(f"{k}={v}" for k, v in filter_stats_detail.items() if v)
            if detail:
                print(f"  Catalogue filter/veto rejections: {detail}")

        if len(universe_filtered) == 0:
            return {
                "selection": [],
                "message": "No stocks passed all filters and vetoes.",
                "total_considered": len(self.universe)
            }

        # Step 5: Calculate scores for remaining stocks
        # Score requires specific fundamental data columns
        # We'll use available columns; if missing, use default values
        score_columns = [p.parameter_key for p in self.score_calc.score_params]
        filter_columns = [p.parameter_key for p in self.score_calc.filter_params]
        veto_columns = [p.parameter_key for p in self.score_calc.veto_params]

        # Ensure required columns exist
        for col in score_columns + filter_columns + veto_columns:
            if col not in universe_filtered.columns:
                universe_filtered[col] = np.nan

        # Apply per-stock filter and veto checks before scoring
        passed_mask = universe_filtered.apply(
            lambda row: self.score_calc.apply_filters(row.to_dict())
            and self.score_calc.apply_vetoes(row.to_dict()),
            axis=1
        )
        filtered_count = len(universe_filtered)
        universe_filtered = universe_filtered[passed_mask].copy()
        per_stock_filtered = filtered_count - len(universe_filtered)
        if per_stock_filtered:
            print(f"After per-stock catalogue filter/veto check: "
                  f"{len(universe_filtered)} stocks ({per_stock_filtered} filtered)")

        # Calculate raw scores
        universe_filtered["raw_score"] = universe_filtered.apply(
            self.score_calc.calculate_score, axis=1
        )
        print(f"Scores calculated for {len(universe_filtered)} stocks")

        # Step 6: Cost-and-tax edge check
        # For each stock, estimate edge based on current price and momentum
        # We'll use price_momentum_weekly as a proxy for expected return

        # Need buy_price (entry) and sell_price (exit after 1 week)
        # For backtest: we simulate buying at current price and selling
        # at price + weekly_momentum

        if "price_momentum_weekly" in universe_filtered.columns:
            # Estimate exit price = entry * (1 + momentum/100)
            universe_filtered["estimated_exit_price"] = (
                universe_filtered["close"] *
                (1 + universe_filtered["price_momentum_weekly"] / 100)
            )
            universe_filtered["estimated_gross_pnl"] = (
                (universe_filtered["estimated_exit_price"] - universe_filtered["close"]) *
                1  # 1 share basis for cost calculation
            )
        else:
            universe_filtered["estimated_exit_price"] = universe_filtered["close"]
            universe_filtered["estimated_gross_pnl"] = 0

        # Apply edge check to each stock
        edge_results = []
        for idx, row in universe_filtered.iterrows():
            result = self.edge_checker.check_edge(
                expected_weekly_return_pct=row.get("price_momentum_weekly", 0),
                buy_price=row["close"],
                sell_price=row.get("estimated_exit_price", row["close"]),
                quantity=1  # 1 share for per-unit cost calculation
            )
            edge_results.append(result)

        # Attach edge results
        universe_filtered["edge_passes"] = [r["passes"] for r in edge_results]
        universe_filtered["edge_pct"] = [r["edge_pct"] for r in edge_results]
        universe_filtered["total_costs_pct"] = [r["total_costs_pct"] for r in edge_results]

        # Count passes/fails
        passes_count = sum(1 for r in edge_results if r["passes"])
        fails_count = len(edge_results) - passes_count
        print(f"Cost-and-tax edge check: {passes_count} pass, {fails_count} veto")

        # Step 7: Filter to stocks that pass edge check
        universe_passed = universe_filtered[universe_filtered["edge_passes"]].copy()
        print(f"After cost-and-tax edge check: {len(universe_passed)} stocks")

        if len(universe_passed) == 0:
            return {
                "selection": [],
                "message": "No stocks passed the cost-and-tax edge check. "
                          "Strategy edge too small after brokerage, STT, and 20% tax.",
                "total_considered": len(self.universe),
                "filter_stats": {
                    "liquidity": len(self.universe),
                    "after_liquidity": len(universe_filtered),
                    "after_veto": len(universe_filtered),
                    "edge_passes": 0,
                    "edge_fails": len(universe_filtered)
                }
            }

        # Step 8: Select top N by raw score
        universe_passed = universe_passed.sort_values(
            by="raw_score",
            ascending=False
        ).head(self.top_n)

        # Step 9: Construct selection result
        selections = []
        for _, stock in universe_passed.iterrows():
            selections.append({
                "symbol": stock.get("symbol", "Unknown"),
                "company_name": stock.get("company_name", "Unknown"),
                "score": round(float(stock["raw_score"]), 1),
                "edge_pct": round(float(stock["edge_pct"]), 2),
                "costs_pct": round(float(stock["total_costs_pct"]), 2),
                "liquidity_crore": float(stock.get("daily_turnover_crore", 0)),
                "promoter_pledging_pct": float(stock.get("promoter_pledging_pct", 0)),
                "price": float(stock["close"]),
            })

        # Sort final selection by edge (best first)
        selections.sort(key=lambda x: x["edge_pct"], reverse=True)

        result = {
            "selection": selections,
            "total_considered": len(self.universe),
            "filter_stats": {
                "liquidity": len(self.universe),
                "after_liquidity": len(universe_filtered),
                "after_veto": len(universe_filtered),
                "edge_passes": passes_count,
                "edge_fails": fails_count,
                "selected_top_n": len(selections)
            },
            "cost_model_used": {
                "stt_buy": self.cost_model.stt_buy,
                "stt_sell": self.cost_model.stt_sell,
                "brokerage_rate": self.cost_model.brokerage_rate,
                "stcg_tax_rate": self.cost_model.stcg_tax_rate,
                "total_roundtrip_cost_pct": self.cost_model.total_roundtrip_cost_pct,
            },
            "parameter_weight_total": sum(p.weight for p in self.score_calc.enabled_params),
        }

        print(f"\n=== Selected {len(selections)} stocks for weekly basket ===")
        for i, s in enumerate(selections, 1):
            print(f"  {i}. {s['symbol']} - Score: {s['score']}, Edge: {s['edge_pct']}%, Costs: {s['costs_pct']}%")

        return result

    def run_backtest_period(
        self,
        historical_data: Dict[str, pd.DataFrame],
        start_date: str,
        end_date: str
    ) -> Dict[str, any]:
        """Run backtest across a historical period.

        Args:
            historical_data: Dict of {symbol: DataFrame with OHLCV + fundamentals}
            start_date: Start date string (YYYY-MM-DD)
            end_date: End date string (YYYY-MM-DD)

        Returns comprehensive backtest results.
        """
        all_weekly_results = []
        capital = 25000  # Rs. 25,000 pilot capital (from user decision)
        capital_allocated = 0
        trades_log = []

        # Get date range
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)

        # Get sorted list of all trading days in range
        all_dates = []
        for symbol, df in historical_data.items():
            if "date" in df.columns:
                dates = pd.to_datetime(df["date"])
                mask = (dates >= start) & (dates <= end)
                all_dates.extend(dates[mask].tolist())

        if not all_dates:
            return {"error": "No historical data found for the given period"}

        all_dates = sorted(set(all_dates))

        print(f"Backtest period: {start_date} to {end_date}")
        print(f"Total trading days to process: {len(all_dates)}")
        print(f"Pilot capital: ₹{capital:,}")
        print()

        # Process each week (approximately weekly rebalancing)
        # For simplicity, process each unique date that has data
        for i, trade_date in enumerate(all_dates):
            trade_date_str = trade_date.strftime("%Y-%m-%d")

            # Collect universe data for this date
            weekly_universe = []

            for symbol, df in historical_data.items():
                # Find data closest to this date
                df_dates = pd.to_datetime(df["date"])
                closest_idx = (df_dates - trade_date).abs().idxmin()
                closest_date = df_dates.iloc[closest_idx]

                if abs((df_dates.iloc[closest_idx] - trade_date).days) <= 3:
                    row = df.loc[closest_idx]
                    # Only include if we have enough data
                    if not pd.isna(row.get("close", np.nan)):
                        weekly_universe.append({
                            "symbol": symbol,
                            "date": trade_date_str,
                            "close": float(row["close"]),
                            "daily_turnover_crore": float(row.get("daily_turnover_crore", 0)),
                            # Include any fundamental data that's available
                            **{k: float(row.get(k, np.nan)) for k in
                               ["pe_ratio_vs_sector", "debt_equity_ratio", "roe_trend",
                                "price_momentum_weekly", "promoter_pledging_pct"]
                               if k in row.index}
                        })

            if not weekly_universe:
                continue

            # Convert to DataFrame and run pipeline
            uni_df = pd.DataFrame(weekly_universe)

            # Skip if too few stocks
            if len(uni_df) < 5:
                continue

            # Run the weekly pipeline
            result = self.run_weekly_pipeline_from_dataframe(uni_df)
            result["reference_date"] = trade_date_str
            all_weekly_results.append(result)

            # Simple capital allocation simulation
            if i % 4 == 0 and i > 0:  # Rebalance every ~4 weeks
                # Equal weight allocation within top N
                allocation_per_stock = capital / self.top_n
                # This is tracked but not executed in this backtest run
                # In live trading, would allocate capital_per_stock per position

        # Summary calculation
        total_trades = sum(r["filter_stats"]["selected_top_n"] for r in all_weekly_results if "filter_stats" in r)
        avg_edge = float(np.mean([r["filter_stats"]["edge_pct"] for r in all_weekly_results
                                  if "filter_stats" in r and r["filter_stats"]["edge_pct"]]))
        avg_costs = float(np.mean([r["filter_stats"]["total_costs_pct"] for r in all_weekly_results
                                   if "filter_stats" in r]))

        # Calculate equity curve assuming equal capital allocation
        # This is a simplified simulation
        successful_weeks = 0
        losing_weeks = 0

        for result in all_weekly_results:
            if "filter_stats" in result and "edge_pct" in result["filter_stats"]:
                if result["filter_stats"]["edge_pct"] > 0:
                    successful_weeks += 1
                else:
                    losing_weeks += 1

        # Overall stats
        summary = {
            "period": f"{start_date} to {end_date}",
            "total_weeks_processed": len(all_weekly_results),
            "pilot_capital": capital,
            "total_trades_simulated": total_trades,
            "average_edge_pct": round(avg_edge, 2),
            "average_costs_pct": round(avg_costs, 2),
            "successful_weeks": successful_weeks,
            "losing_weeks": losing_weeks,
            "win_rate_pct": round((successful_weeks / len(all_weekly_results) * 100) if all_weekly_results else 0, 1),
            "results": all_weekly_results,
        }

        return summary

    def run_weekly_pipeline_from_dataframe(self, df: pd.DataFrame) -> Dict[str, any]:
        """Run the weekly pipeline on a pre-built DataFrame.

        This is a convenience method that sets up the universe from a DataFrame
        and runs the full pipeline.
        """
        # Prepare universe DataFrame with required columns
        # Ensure key columns exist
        required_cols = ["symbol", "close", "daily_turnover_crore"]
        for col in required_cols:
            if col not in df.columns:
                if col == "symbol":
                    df["symbol"] = df.index.astype(str)
                elif col == "daily_turnover_crore":
                    df["daily_turnover_crore"] = 50.0  # Default assumption

        # Run the full pipeline
        return self.run_weekly_pipeline()


# Example usage demonstration
if __name__ == "__main__":
    print("=== Nifty 100 Weekly Delivery Backtester ===\n")
    print("This backtester implements the BRD Section 27.5 pipeline:")
    print("  1. Liquidity filter (≥₂₅ crore daily turnover)")
    print("  2. ASM/GSM surveillance filter")
    print("  3. Legal/regulatory vetoes")
    print("  4. Weighted score calculation")
    print("  5. Cost-and-tax edge check (STT 0.1%, STCG 20%, brokerage, slippage)")
    print("  6. Select top N for weekly basket\n")

    # Demonstrate parameter catalogue validation
    from ..config.parameter_catalogue import validate_weight_total
    print(f"Parameter weight total valid: {validate_weight_total()}")
    print(f"Enabled parameters: {len(get_enabled_parameters())}")
    print("=" * 60)