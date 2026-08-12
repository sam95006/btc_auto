"""V18.2.28 Founder-only real-demo monitor + trading intel contract constants."""
from __future__ import annotations

import os
from pathlib import Path

SCHEMA_ID = "NEXUS_FOUNDER_DEMO_MONITOR_V18_2_28"
LANE = "V18.2.28"
LANE_NAME = "Founder-only real demo monitor (trading intel / live core feed)"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PKG = Path(__file__).resolve().parent


def _env_evidence_root() -> Path | None:
    root = str(os.environ.get("NEXUS_EVIDENCE_COORDINATOR", "") or "").strip()
    return Path(root) if root else None


def _is_zeabur_runtime() -> bool:
    if str(os.environ.get("NEXUS_RUNTIME_LOCATION", "") or "").strip().upper() == "ZEABUR":
        return True
    if str(os.environ.get("NEXUS_ZEABUR_AUTONOMY_DEPLOYED", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return True
    return any(
        bool(str(os.environ.get(k, "") or "").strip())
        for k in (
            "ZEABUR",
            "ZEABUR_SERVICE_ID",
            "ZEABUR_PROJECT_ID",
            "ZEABUR_ENVIRONMENT_ID",
            "KUBERNETES_SERVICE_HOST",
        )
    )


def _runtime_live_candidates() -> tuple[str, ...]:
    """Cloud /data first. No D:\\ fallback when ZEABUR."""
    out: list[str] = []
    # Shared volume paths (unified runtime)
    data_root = str(os.environ.get("NEXUS_DATA_ROOT", "") or "").strip() or (
        "/data" if _is_zeabur_runtime() else ""
    )
    env_root = _env_evidence_root()
    if env_root is not None:
        out.extend(
            [
                str(env_root / "founder_demo_monitor_live.json"),
                str(env_root / "unified_runtime_health.json"),
            ]
        )
    if data_root:
        out.extend(
            [
                str(Path(data_root) / "evidence_coordinator" / "founder_demo_monitor_live.json"),
                str(Path(data_root) / "evidence_coordinator" / "unified_runtime_health.json"),
                str(
                    Path(data_root)
                    / "campaigns"
                    / "research_v18_2_30"
                    / "autonomy"
                    / "founder_demo_monitor_live.json"
                ),
            ]
        )
    if not _is_zeabur_runtime():
        # Local developer fallback only
        out.extend(
            [
                r"D:\NEXUS_RUNTIME\evidence_coordinator\founder_demo_monitor_live.json",
                r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_28_core.json",
            ]
        )
    return tuple(dict.fromkeys(out))


def _repo_live_candidates() -> tuple[str, ...]:
    """Bundled live snapshots for preview deploy (not static V25 fixture)."""
    root = _REPO_ROOT / "data" / "evidence_coordinator"
    return (str(root / "founder_demo_monitor_live.json"),)


def _fixture_fallback_candidates() -> tuple[str, ...]:
    """Static sanitized fixture — last resort only when no live feed mounted."""
    return (str(_PKG / "fixtures" / "founder_demo_monitor_live.json"),)


# Live Agent B / evidence coordinator first; repo bundled live; fixture last.
DEFAULT_LIVE_FEED_CANDIDATES: tuple[str, ...] = (
    _runtime_live_candidates() + _repo_live_candidates() + _fixture_fallback_candidates()
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

CORE_FEED_READY_NAMES = frozenset(
    {
        "founder_demo_monitor_live.json",
        "v18_2_26_core.json",
        "v18_2_27_core.json",
        "v18_2_28_core.json",
        "v18_2_25_core.json",
    }
)

STALE_CORE_NAMES = frozenset(
    {
        "v18_2_24_core.json",
        "v18_2_23_core.json",
    }
)
