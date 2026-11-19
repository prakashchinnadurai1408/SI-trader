"""Tutorial System for SI-Trader Platform.

BRD Section 23: Interactive onboarding tutorials for new users.
Covers: platform navigation, auto-investing setup, risk management basics,
parameter selection, and first trade walkthrough.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import json
import os


class TutorialStatus(Enum):
    """Progress status for a tutorial module."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class TutorialTopic(Enum):
    """Available tutorial topics."""
    PLATFORM_NAVIGATION = "platform_navigation"
    AUTO_INVESTING_SETUP = "auto_investing_setup"
    RISK_MANAGEMENT = "risk_management"
    PARAMETER_SELECTION = "parameter_selection"
    FIRST_TRADE = "first_trade"
    PORTFOLIO_MONITORING = "portfolio_monitoring"


@dataclass
class TutorialStep:
    """A single step in a tutorial sequence."""
    id: str
    title: str
    content: str  # HTML or markdown content
    interactive: bool  # Whether step requires user interaction
    estimated_minutes: int
    completion_condition: Optional[str] = None  # JS condition or check


@dataclass
class TutorialModule:
    """A complete tutorial topic with multiple steps."""
    topic: TutorialTopic
    title: str
    description: str
    steps: List[TutorialStep]
    estimated_total_minutes: int
    status: TutorialStatus = TutorialStatus.NOT_STARTED
    completed_steps: int = 0
    last_step_time: Optional[float] = None  # timestamp


# Base tutorial content per BRD Section 23
TUTORIAL_MODULES: Dict[TutorialTopic, TutorialModule] = {
    TutorialTopic.PLATFORM_NAVIGATION: TutorialModule(
        topic=TutorialTopic.PLATFORM_NAVIGATION,
        title="Platform Navigation",
        description="Learn your way around the SI-Trader dashboard",
        steps=[
            TutorialStep(
                id="step1",
                title="Dashboard Overview",
                content="<p>The dashboard shows your portfolio, daily checklist, and quick actions.</p>"
                       "<p>Key areas: Positions, Watchlist, Daily Checklist, Settings.</p>",
                interactive=False,
                estimated_minutes=5
            ),
            TutorialStep(
                id="step2",
                title="Menu Navigation",
                content="<p>Use the left sidebar to navigate between:</p>"
                       "<ul>"
                       "<li>Trader Journey (BRD Sections 20-22)</li>"
                       "<i>Compliance Gates (Section 14)</i>"
                       "<i>Weekly Backtester (Section 27.5)</i>"
                       "<i>Paper Trading Mode</li>"
                       "</ul>",
                interactive=False,
                estimated_minutes=5
            ),
            TutorialStep(
                id="step3",
                title="User Authentication",
                content="<p>Login with phone: 9820065335 | Password: 123456</p>"
                       "<p>Role hierarchy: trader < manager ≤ compliance < admin</p>"
                       "<p>Lockout after 3 failed login attempts.</p>",
                interactive=True,
                estimated_minutes=3,
                completion_condition="login_attempts < 3"
            ),
        ],
        estimated_total_minutes=13
    ),
    TutorialTopic.AUTO_INVESTING_SETUP: TutorialModule(
        topic=TutorialTopic.AUTO_INVESTING_SETUP,
        title="Weekly Auto-Investing Setup",
        description="Configure your weekly delivery auto-investing strategy",
        steps=[
            TutorialStep(
                id="step1",
                title="Set Pilot Capital",
                content="<p>Default pilot capital: Rs. 25,000</p>"
                       "<p>Configure allocation per position and top-N selection.</p>",
                interactive=True,
                estimated_minutes=5,
                completion_condition="capital_set"
            ),
            TutorialStep(
                id="step2",
                title="Select Strategy Parameters",
                content="<p>30 enabled parameters with total weight = 100</p>"
                       "<p>Score parameters (11), Filter parameters (9), Veto parameters (4)</p>"
                       "<p>Weights scaled exactly to 100 for BRD compliance.</p>",
                interactive=True,
                estimated_minutes=8,
                completion_condition="parameters_validated"
            ),
            TutorialStep(
                id="step3",
                title="Risk Limits Configuration",
                content="<p>Max position size: 10% of portfolio</p>"
                       "<p>Max single trade: 5% of capital</p>"
                       "<p>Max weekly loss: Rs. 5,000 kill switch</p>"
                       "<p>Paper trading mode default (PAPER).</p>",
                interactive=True,
                estimated_minutes=5,
                completion_condition="risk_limits_configured"
            ),
        ],
        estimated_total_minutes=18
    ),
    TutorialTopic.RISK_MANAGEMENT: TutorialModule(
        topic=TutorialTopic.RISK_MANAGEMENT,
        title="Risk Management Basics",
        description="Understand and configure risk controls",
        steps=[
            TutorialStep(
                id="step1",
                title="Cost Model Overview",
                content="<p>STT: 0.1% both sides (buy & sell)</p>"
                       "<p>Brokerage: 0.05%</p>"
                       "<p>STCG Tax: 20% for weekly delivery (< 12 months)</p>"
                       "<p>Roundtrip cost: ~0.38% of turnover</p>"
                       "<p>Edge must exceed cost+tax to be profitable.</p>",
                interactive=False,
                estimated_minutes=5
            ),
            TutorialStep(
                id="step2",
                title="Veto Rules",
                content="<p>Liquidity filter: ≥₹25 crore (large-cap), ≥₹5 crore (mid-cap)</p>"
                       "<p>ASM/GSM surveillance filtering</p>"
                       "<p>Legal cases veto (≥15% of stocks have serious cases)</p>"
                       "<p>Promoter pledging: ≥25% promoter shares = veto</p>"
                       "<p>Midcap universe: 39 stocks beyond Nifty 100.</p>",
                interactive=False,
                estimated_minutes=6
            ),
            TutorialStep(
                id="step3",
                title="Position Limits",
                content="<p>Max 10 positions per weekly basket</p>"
                       "<p>Max 5% per single trade</p>"
                       "<p>Weekly rebalancing</p>"
                       "<p>3+ month paper trading required before REAL_MONEY.</p>",
                interactive=False,
                estimated_minutes=4
            ),
        ],
        estimated_total_minutes=15
    ),
    TutorialTopic.PARAMETER_SELECTION: TutorialModule(
        topic=TutorialTopic.PARAMETER_SELECTION,
        title="Parameter Selection & Weights",
        description="Configure the 30 enabled parameters for stock scoring",
        steps=[
            TutorialStep(
                id="step1",
                title="Parameter Catalogue Structure",
                content="<p>30 parameters across 6 role types:</p>"
                       "<ul>"
                       "<li>Score: 11 parameters (weight: 32 total)</li>"
                       "<li>Filter: 9 parameters (weight: 29 total)</li>"
                       "<li>Veto: 4 parameters (weight: 19 total)</li>"
                       "<li>Market dial: 1 parameter (weight: 3)</li>"
                       "<li>Advisory: 4 parameters (weight: 14 total)</li>"
                       "<li>Flag: 1 parameter (weight: 3)</li>"
                       "</ul>"
                       "<p>Total: exactly 100 weight points.</p>"
                       "<p>BRD thesis: edge must exceed ~0.3% roundtrip cost+tax.</p>",
                interactive=False,
                estimated_minutes=6
            ),
            TutorialStep(
                id="step2",
                title="Validate Weight Total",
                content="<p>Run <code>validate_weight_total()</code></p>"
                       "<p>Returns <code>True</code> when weights sum to 100.</p>"
                       "<p>Ensures BRD parameter integrity.</p>"
                       "<p>Core guard: no generic AI edge; edge from own material only.</p>",
                interactive=True,
                estimated_minutes=3,
                completion_condition="weight_total_validated"
            ),
            TutorialStep(
                id="step3",
                title="Enable/Disable Parameters",
                content="<p>Toggle parameters on/off per trader role</p>"
                       "<p>Score params influence stock ranking</p>"
                       "<p>Filter params screen in/out stocks</p>"
                       "<p>Veto params exclude high-risk stocks</p>"
                       "<p>Parameter weights are fixed; only enable/disable active.</p>",
                interactive=True,
                estimated_minutes=4
            ),
        ],
        estimated_total_minutes=13
    ),
    TutorialTopic.FIRST_TRADE: TutorialModule(
        topic=TutorialTopic.FIRST_TRADE,
        title="Your First Weekly Trade",
        description="Walkthrough of placing your first weekly delivery trade",
        steps=[
            TutorialStep(
                id="step1",
                title="Weekly Selection Pipeline",
                content="<p>BRD Section 27.5 7-step pipeline:</p>"
                       "<ol>"
                       "<li>Universe: Nifty 100 (54 large-cap) or Midcap (93 total)</li>"
                       "<li>Liquidity filter: ≥ threshold daily turnover</li>"
                       "<li>ASM/GSM surveillance filter</li>"
                       "<li>Legal & regulatory vetoes</li>"
                       "<li>Promoter pledging ≥25% veto</li>"
                       "<li>Weighted score calculation</li>"
                       "<li>Cost-and-tax edge check (STT, STCG, brokerage)</li>"
                       "<li>Select top N stocks</li>"
                       "</ol>",
                interactive=False,
                estimated_minutes=6
            ),
            TutorialStep(
                id="step2",
                title="Run First Pipeline",
                content="<p>Click: Weekly Backtester → Run Pipeline</p>"
                       "<p>View: stocks passing all filters</p>"
                       "<p>View: edge % after STT 0.1%/side + STCG 20% + brokerage</p>"
                       "<p>View: top N selected for weekly basket</p>"
                       "<p>Average edge: ~0.15% after costs+tax.</p>",
                interactive=True,
                estimated_minutes=8,
                completion_condition="pipeline_run"
            ),
            TutorialStep(
                id="step3",
                title="Paper Trading Execution",
                content="<p>Default mode: PAPER (no real money)</p>"
                       "<p>Position size: 10% of pilot capital per stock</p>"
                       "<p>Max single trade: 5% of capital</p>"
                       "<p>Kill switch: triggers on max weekly loss ₹5,000</p>"
                       "<p>Manual approval required for first live order (BRD Section 14)</p>"
                       "<p>Trade executes with: STT 0.1% both sides + brokerage 0.05% + STCG 20%</p>",
                interactive=True,
                estimated_minutes=7,
                completion_condition="paper_trade_executed"
            ),
        ],
        estimated_total_minutes=21
    ),
    TutorialTopic.PORTFOLIO_MONITORING: TutorialModule(
        topic=TutorialTopic.PORTFOLIO_MONITORING,
        title="Portfolio Monitoring & Rebalancing",
        description="Track and rebalance your weekly auto-investing portfolio",
        steps=[
            TutorialStep(
                id="step1",
                title="Daily 08:30 Pre-Market Checklist",
                content="<p>14-item checklist generated each trading day</p>"
                       "<p>Completed items track: market status, open positions,</p>"
                       "<p>pending orders, liquidity checks, compliance status</p>"
                       "<p>Ready-to-trade flag: green when ≥11/14 items passed</p>"
                       "<p>Per BRD Section 20.</p>",
                interactive=False,
                estimated_minutes=5
            ),
            TutorialStep(
                id="step2",
                title="Weekly Rebalancing",
                content="<p>Pipeline runs weekly (every 7 days)</p>"
                       "<p>Top N stocks selected based on weighted scores</p>"
                       "<p>Capital reallocated: ₹25,000 / N positions</p>"
                       "<p>Historical backtest: 3-year period, average edge 0.09%</p>"
                       "<p>14 stocks with positive edge after costs+tax.</p>",
                interactive=False,
                estimated_minutes=5
            ),
            TutorialStep(
                id="step3",
                title="Transition to REAL_MONEY",
                content="<p>Required: 3+ months paper trading with all gates pass</p>"
                       "<p>SEBI legal review before commercial launch</p>"
                       "<p>All 5 compliance gates must pass</p>"
                       "<p>Kill switch remains active until transition</p>"
                       "<p>Transition triggers: sustained positive edge, compliance sign-off.</p>",
                interactive=False,
                estimated_minutes=5
            ),
        ],
        estimated_total_minutes=15
    ),
}


def get_tutorial_topic(topic: TutorialTopic) -> Optional[TutorialModule]:
    """Get a tutorial module by topic."""
    return TUTORIAL_MODULES.get(topic, None)


def get_all_modules() -> List[TutorialModule]:
    """Get all tutorial modules."""
    return list(TUTORIAL_MODULES.values())


def get_module_progress(user_progress: Dict[str, TutorialStatus]) -> Dict[TutorialTopic, int]:
    """Calculate progress for each module based on user status."""
    progress = {}
    for topic, module in TUTORIAL_MODULES.items():
        status = user_progress.get(topic, TutorialStatus.NOT_STARTED)
        if status == TutorialStatus.COMPLETED:
            progress[topic] = 100
        elif status == TutorialStatus.IN_PROGRESS:
            progress[topic] = 50
        else:
            progress[topic] = 0
    return progress


def save_user_progress(user_id: str, progress: Dict[str, TutorialStatus]) -> str:
    """Save user tutorial progress to file."""
    progress_dir = Path(__file__).parent.parent / "user_data" / user_id
    progress_dir.mkdir(parents=True, exist_ok=True)
    progress_file = progress_dir / "tutorial_progress.json"
    
    # Convert enum to string for JSON serialization
    serializable = {
        topic.value: status.value
        for topic, status in progress.items()
    }
    
    with open(progress_file, 'w') as f:
        json.dump(serializable, f, indent=2)
    
    return str(progress_file)


def load_user_progress(user_id: str) -> Dict[str, TutorialStatus]:
    """Load user tutorial progress from file."""
    progress_file = Path(__file__).parent.parent / "user_data" / user_id / "tutorial_progress.json"
    
    if not progress_file.exists():
        return {topic: TutorialStatus.NOT_STARTED for topic in TUTORIAL_MODULES.keys()}
    
    try:
        with open(progress_file, 'r') as f:
            data = json.load(f)
        
        return {
            topic: TutorialStatus(status_str)
            for topic, status_str in data.items()
            if topic in TUTORIAL_MODULES
        }
    except (json.JSONDecodeError, KeyError):
        return {topic: TutorialStatus.NOT_STARTED for topic in TUTORIAL_MODULES.keys()}


# Initialize user data directory
def init_user_data_dir():
    """Ensure user data directory exists."""
    user_data_dir = Path(__file__).parent.parent / "user_data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    return str(user_data_dir)


# Export for web app integration
__all__ = [
    'TutorialStatus', 'TutorialTopic', 'TutorialStep', 'TutorialModule',
    'get_tutorial_topic', 'get_all_modules', 'get_module_progress',
    'save_user_progress', 'load_user_progress', 'init_user_data_dir',
    'TUTORIAL_MODULES'
]