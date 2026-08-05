"""V13-D Point-in-Time Dynamic Market Discovery.

Discover eligible/rejected linear-USDT universes as of a historical timestamp
using sanitized fixtures only. Never uses today's universe to simulate the past.
No exchange writes, no Demo, no PR27 merge.
"""
from __future__ import annotations

from backend.nexus_market_discovery.adversarial import run_adversarial_suite
from backend.nexus_market_discovery.constants import (
    DISCOVERY_SCHEMA,
    EVALUATION_DIMENSIONS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    SCHEMA,
    UNIVERSE_ID,
)
from backend.nexus_market_discovery.discovery import (
    PitDiscoveryError,
    compare_eras,
    discover_universe,
)
from backend.nexus_market_discovery.evaluator import InstrumentEvaluation, evaluate_instrument
from backend.nexus_market_discovery.fixtures import (
    ERA_2024_06_01_MS,
    ERA_2024_12_01_MS,
    ERA_2025_03_01_MS,
    PitSnapshotError,
    materialize_fixtures,
    select_snapshot_for_as_of,
)
from backend.nexus_market_discovery.lineage import build_lineage, sha_obj, universe_checksum
from backend.nexus_market_discovery.public_metadata import (
    LIVE_AS_OF_TOLERANCE_MS,
    assert_live_read_allowed,
    live_public_metadata_unavailable_by_design,
)

__all__ = [
    "LIVE_AS_OF_TOLERANCE_MS",
    "assert_live_read_allowed",
    "live_public_metadata_unavailable_by_design",
    "DISCOVERY_SCHEMA",
    "ERA_2024_06_01_MS",
    "ERA_2024_12_01_MS",
    "ERA_2025_03_01_MS",
    "EVALUATION_DIMENSIONS",
    "HARD_BANS",
    "InstrumentEvaluation",
    "LANE",
    "LANE_NAME",
    "PitDiscoveryError",
    "PitSnapshotError",
    "SCHEMA",
    "UNIVERSE_ID",
    "build_lineage",
    "compare_eras",
    "discover_universe",
    "evaluate_instrument",
    "materialize_fixtures",
    "run_adversarial_suite",
    "select_snapshot_for_as_of",
    "sha_obj",
    "universe_checksum",
]
