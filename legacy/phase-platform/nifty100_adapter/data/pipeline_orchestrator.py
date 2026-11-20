"""Data Pipeline Orchestrator for SI-Trader.

Orchestrates data refresh across all 48 parameters according to their
refresh schedules. Coordinates all data adapters and provides a unified
interface for data refresh, validation, and quality checks.

Data Sources Orchestrated:
1. NSE Price Adapter - price_momentum, liquidity, volatility
2. Fundamentals Adapter - F-Score, Altman Z-Score, PE, ROE, etc.
3. Shareholding Adapter - promoter holding, pledging, FII/DII/MF
4. News Sentiment Adapter - news sentiment scores
5. Regulatory Adapter - SEBI/RBI/NSE/BSE announcements, legal cases

Refresh Schedules:
- daily: price_momentum_daily, liquidity_floor, ASM/GSM
- weekly: price_momentum_weekly, fii_dii_mf_trend, historical_news_sentiment
- monthly: customer_feedback
- quarterly: f_score, altman_z_score, pe_ratio_vs_sector, roe_trend, etc.
- on-event: midcap_corp_action, international_war_situation, regulatory_actions
- per_trade: cost_vs_edge_check, stt_rate_equity, stcg_tax_rate, brokerage_rate
- fy_update: stt_rate_equity, stcg_tax_rate
- annually: competitive_plans
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timedelta
import logging
import asyncio
import time

logger = logging.getLogger(__name__)


@dataclass
class DataRefreshResult:
    """Result of a data refresh operation."""
    data_source: str
    parameter_keys: List[str]
    success: bool
    records_updated: int
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class PipelineHealth:
    """Pipeline health status."""
    overall_status: str  # HEALTHY, DEGRADED, CRITICAL
    last_refresh: Optional[str]
    failed_sources: List[str] = field(default_factory=list)
    stale_sources: List[str] = field(default_factory=list)
    total_parameters: int = 48
    enabled_parameters: int = 30
    data_coverage_pct: float = 0.0


class DataPipelineOrchestrator:
    """Orchestrates data refresh across all 48 parameters.

    Manages the lifecycle of data fetching from multiple sources,
    tracks freshness, and coordinates refresh schedules.

    Usage:
        orchestrator = DataPipelineOrchestrator()
        await orchestrator.register_adapter("nse_price", nse_adapter)
        await orchestrator.refresh_all()
        status = orchestrator.get_health()
    """

    def __init__(self):
        self.adapters: Dict[str, Any] = {}
        self.adapter_schedules: Dict[str, str] = {}  # adapter_name -> schedule
        self.adapter_parameters: Dict[str, List[str]] = {}  # adapter_name -> parameter_keys
        self.last_refresh: Dict[str, datetime] = {}
        self.refresh_results: List[DataRefreshResult] = []
        self.max_results_history = 100

        # Schedule definitions (refresh interval in minutes)
        self.schedule_intervals = {
            "daily": 1440,      # 24 hours
            "weekly": 10080,    # 7 days
            "monthly": 43200,   # 30 days
            "quarterly": 129600, # 90 days
            "annually": 525600,  # 365 days
            "on-event": 0,       # Event-driven, no schedule
            "per_trade": 0,      # Per trade, no schedule
            "fy_update": 525600, # Financial year update
        }

        logger.info("DataPipelineOrchestrator initialized")

    def register_adapter(self, name: str, adapter: Any,
                         schedule: str,
                         parameter_keys: List[str]):
        """Register a data adapter with the orchestrator.

        Args:
            name: Adapter name
            adapter: Adapter instance
            schedule: Refresh schedule (daily, weekly, monthly, etc.)
            parameter_keys: List of parameter keys this adapter provides
        """
        self.adapters[name] = adapter
        self.adapter_schedules[name] = schedule
        self.adapter_parameters[name] = parameter_keys
        self.last_refresh[name] = None

        logger.info(f"Registered adapter: {name} (schedule: {schedule}, params: {len(parameter_keys)})")

    def is_due_for_refresh(self, adapter_name: str) -> bool:
        """Check if an adapter is due for refresh."""
        if adapter_name not in self.adapters:
            return False

        schedule = self.adapter_schedules.get(adapter_name)
        if not schedule or schedule in ("on-event", "per_trade"):
            return False  # Event-driven or per-trade, not scheduled

        last_refresh = self.last_refresh.get(adapter_name)
        if last_refresh is None:
            return True  # Never refreshed

        interval_minutes = self.schedule_intervals.get(schedule, 1440)
        next_refresh = last_refresh + timedelta(minutes=interval_minutes)

        return datetime.now() >= next_refresh

    def get_stale_adapters(self) -> List[str]:
        """Get list of adapters that need refreshing."""
        return [name for name in self.adapters if self.is_due_for_refresh(name)]

    async def refresh_adapter(self, name: str) -> DataRefreshResult:
        """Refresh a single adapter."""
        if name not in self.adapters:
            return DataRefreshResult(
                data_source=name,
                parameter_keys=[],
                success=False,
                records_updated=0,
                errors=[f"Adapter {name} not registered"],
            )

        adapter = self.adapters[name]
        parameter_keys = self.adapter_parameters.get(name, [])
        start_time = datetime.now()

        try:
            # Call the appropriate refresh method based on adapter type
            if hasattr(adapter, 'refresh_all'):
                result = await adapter.refresh_all()
            elif hasattr(adapter, 'refresh'):
                result = await adapter.refresh()
            else:
                # Generic refresh - call get methods for all parameters
                result = await self._generic_refresh(adapter, parameter_keys)

            duration = (datetime.now() - start_time).total_seconds()

            refresh_result = DataRefreshResult(
                data_source=name,
                parameter_keys=parameter_keys,
                success=True,
                records_updated=result.get("records_updated", 0) if isinstance(result, dict) else 0,
                timestamp=start_time.isoformat(),
                duration_seconds=duration,
            )

            self.last_refresh[name] = start_time
            self.refresh_results.append(refresh_result)

            # Trim history
            if len(self.refresh_results) > self.max_results_history:
                self.refresh_results = self.refresh_results[-self.max_results_history:]

            logger.info(f"Refreshed adapter {name}: {refresh_result.records_updated} records in {duration:.2f}s")
            return refresh_result

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Refresh failed for adapter {name}: {error_msg}")

            refresh_result = DataRefreshResult(
                data_source=name,
                parameter_keys=parameter_keys,
                success=False,
                records_updated=0,
                errors=[error_msg],
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                timestamp=start_time.isoformat(),
            )

            self.refresh_results.append(refresh_result)
            return refresh_result

    async def _generic_refresh(self, adapter: Any,
                               parameter_keys: List[str]) -> Dict[str, Any]:
        """Generic refresh method for adapters without specific refresh methods."""
        records_updated = 0

        for param_key in parameter_keys:
            try:
                # Try common refresh method names
                for method_name in [f"refresh_{param_key}", f"update_{param_key}", f"get_{param_key}"]:
                    if hasattr(adapter, method_name):
                        method = getattr(adapter, method_name)
                        if asyncio.iscoroutinefunction(method):
                            await method()
                        else:
                            method()
                        records_updated += 1
                        break
            except Exception as e:
                logger.warning(f"Refresh failed for {param_key}: {e}")

        return {"records_updated": records_updated}

    async def refresh_all(self) -> List[DataRefreshResult]:
        """Refresh all adapters that are due for refresh."""
        results = []
        adapters_to_refresh = [name for name in self.adapters if self.is_due_for_refresh(name)]

        logger.info(f"Refreshing {len(adapters_to_refresh)} adapters")

        for name in adapters_to_refresh:
            result = await self.refresh_adapter(name)
            results.append(result)

        return results

    async def refresh_now(self, adapter_names: Optional[List[str]] = None) -> List[DataRefreshResult]:
        """Force refresh specific adapters or all adapters."""
        if adapter_names is None:
            adapter_names = list(self.adapters.keys())

        results = []
        for name in adapter_names:
            if name in self.adapters:
                result = await self.refresh_adapter(name)
                results.append(result)

        return results

    def get_health(self) -> PipelineHealth:
        """Get pipeline health status."""
        failed_sources = []
        stale_sources = []

        for name in self.adapters:
            last = self.last_refresh.get(name)
            if last is None:
                stale_sources.append(name)
            elif self.is_due_for_refresh(name):
                stale_sources.append(name)

        # Check for recent failures
        recent_results = self.refresh_results[-10:] if self.refresh_results else []
        for result in recent_results:
            if not result.success:
                failed_sources.append(result.data_source)

        total_params = 48
        enabled_params = 30
        coverage = (len([r for r in self.refresh_results if r.success]) /
                    max(len(self.refresh_results), 1)) * 100 if self.refresh_results else 0

        overall_status = "HEALTHY"
        if failed_sources:
            overall_status = "CRITICAL"
        elif stale_sources:
            overall_status = "DEGRADED"

        return PipelineHealth(
            overall_status=overall_status,
            last_refresh=max([r.timestamp for r in self.refresh_results],
                            default=None) if self.refresh_results else None,
            failed_sources=list(set(failed_sources)),
            stale_sources=stale_sources,
            total_parameters=total_params,
            enabled_parameters=enabled_params,
            data_coverage_pct=round(coverage, 1),
        )

    def get_refresh_summary(self) -> Dict[str, Any]:
        """Get refresh summary statistics."""
        total_refreshes = len(self.refresh_results)
        successful = sum(1 for r in self.refresh_results if r.success)
        failed = total_refreshes - successful

        avg_duration = sum(r.duration_seconds for r in self.refresh_results) / max(total_refreshes, 1)

        return {
            "total_refreshes": total_refreshes,
            "successful": successful,
            "failed": failed,
            "success_rate": round((successful / max(total_refreshes, 1)) * 100, 1),
            "avg_duration_seconds": round(avg_duration, 2),
            "adapters_registered": len(self.adapters),
            "adapters_due": len(self.get_stale_adapters()),
            "last_refresh": self.refresh_results[-1].timestamp if self.refresh_results else None,
        }