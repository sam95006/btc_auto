"""V18.2.25 Founder-only real-demo monitor contract constants."""
from __future__ import annotations

from pathlib import Path

SCHEMA_ID = "NEXUS_FOUNDER_DEMO_MONITOR_V18_2_25"
LANE = "V18.2.26"
LANE_NAME = "Founder-only real demo monitor"

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo_feed_candidates() -> tuple[str, ...]:
    """Deploy-bundled feeds (Zeabur/Linux) — no secrets, sanitized snapshot only."""
    pkg = Path(__file__).resolve().parent
    root = _REPO_ROOT / "data" / "evidence_coordinator"
    return (
        str(pkg / "fixtures" / "founder_demo_monitor_live.json"),
        str(root / "founder_demo_monitor_live.json"),
        str(root / "v18_2_25_core.json"),
    )


# Prefer dedicated live feed from Agent B; fall back to core evidence envelopes.
DEFAULT_LIVE_FEED_CANDIDATES: tuple[str, ...] = _repo_feed_candidates() + (
    r"D:\NEXUS_RUNTIME\evidence_coordinator\founder_demo_monitor_live.json",
    r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_25_core.json",
    r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_24_core.json",
    r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_23_core.json",
)

ENV_FEED_PATH = "NEXUS_FOUNDER_DEMO_MONITOR_FEED"
ENV_EVIDENCE_ROOT = "NEXUS_EVIDENCE_COORDINATOR"
ENV_FEED_ONLY = "NEXUS_FOUNDER_DEMO_MONITOR_FEED_ONLY"

# Keys that must never leave the founder demo-monitor boundary.
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "apiKey",
        "api_key",
        "apiSecret",
        "api_secret",
        "privateKey",
        "private_key",
        "secret",
        "password",
        "token",
        "accessToken",
        "refreshToken",
        "walletAddress",
        "wallet_address",
        "exchangeCredentials",
        "orderId",
        "fillId",
        "bybit_orderId",
        "bybit_executionId",
    }
)

LANE_LABEL_RESEARCH = "PNL_BEARING_RESEARCH"
LANE_LABEL_CANARY = "EXECUTION_CANARY"
