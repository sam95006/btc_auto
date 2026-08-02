"""Active research pipeline facade.

Re-exports existing implementations without relocating frozen H3 semantics.
Wave labels live in configuration/evidence; processing engines remain stable.
"""
from __future__ import annotations

# market data
from backend.nexus_demo_execution.historical_market_data import (  # noqa: F401
    Candle,
    MarketDataset,
    load_dataset,
)

# candidate / structure context
from backend.nexus_demo_execution.cohort_matrix import build_context  # noqa: F401

# event simulation
from backend.nexus_demo_execution.market_event_sim import (  # noqa: F401
    MarketCandidate,
    simulate_natural_trade,
)
from backend.nexus_demo_execution.oos_risk_audit import simulate_with_risk_sizing  # noqa: F401

# cohort / metrics
from backend.nexus_demo_execution.cohort_edge_research import _summ_rows  # noqa: F401

# OOS gate
from backend.nexus_demo_execution.oos import oos_runner_dry_run  # noqa: F401

ACTIVE_RESEARCH_FACADE = True
FROZEN_SEMANTICS_MUTATED = False
