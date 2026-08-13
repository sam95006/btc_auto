"""Regime provenance — preserve engine output separately from market_structure."""
from __future__ import annotations

from typing import Any

MAPPING_VERSION = "v1_c1_provenance"


def attach_regime_provenance(
    regime_info: dict[str, Any],
    *,
    enrichment: dict[str, Any],
) -> dict[str, Any]:
    """Narrow mapping repair: engine regime is authoritative; structure is separate."""
    engine_regime = str(regime_info.get("regime") or regime_info.get("engine_regime") or "UNCERTAIN")
    structure = str(regime_info.get("market_structure") or "UNDETERMINED")
    ts = int(enrichment.get("timestamp_ms") or 0)
    return {
        **regime_info,
        "engine_regime": engine_regime,
        "market_structure": structure,
        # Canonical regime field = engine output (NOT structure alias).
        "regime": engine_regime,
        "regime_source": "MarketStateEngine",
        "regime_timestamp_ms": ts if ts > 0 else None,
        "regime_confidence": regime_info.get("regime_confidence"),
        "mapping_version": MAPPING_VERSION,
    }
