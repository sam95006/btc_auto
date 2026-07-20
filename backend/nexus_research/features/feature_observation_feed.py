"""Feed scanner tickers into FeatureObservation store + MSI components."""
from __future__ import annotations

import time
from typing import Any

PRIORITY_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def refresh_feature_observations_from_scanner() -> dict[str, Any]:
    """Record latest scanner fields as NATURAL + SHADOW observations."""
    from backend.nexus_research.features.registry import Namespace, get_feature_registry

    registry = get_feature_registry()
    now = time.time()
    recorded = 0
    symbols: list[str] = []

    try:
        from backend.market.scanner.scanner_service import get_market_scanner

        scanner = get_market_scanner()
        for c in scanner.candidates(limit=80):
            sym = str(c.get("symbol") or "").upper()
            if not sym:
                continue
            symbols.append(sym)
            mapping = {
                "close": c.get("lastPrice"),
                "return_5": (float(c.get("priceChange5mPct") or 0) / 100.0) if c.get("priceChange5mPct") is not None else None,
                "volume": c.get("volume24h"),
                "funding_rate": c.get("fundingRate"),
                "open_interest": c.get("openInterest"),
                "open_interest_change": c.get("oiChange5mPct"),
            }
            for fname, val in mapping.items():
                quality = "COMPLETE" if val is not None else "UNAVAILABLE"
                for ns in (Namespace.NATURAL, Namespace.SHADOW):
                    registry.record_value(
                        fname,
                        val,
                        event_time=now,
                        quality=quality,
                        namespace=ns,
                        reason=None if val is not None else "scanner_field_missing",
                        metadata={"symbol": sym, "provider": "market_scanner"},
                    )
                    recorded += 1
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "recorded": recorded,
        "symbols": symbols[:20],
        "researchOnly": True,
    }


def build_msi_components_from_scanner() -> dict[str, Any]:
    """Build MSI component dict for market intelligence summary."""
    components: dict[str, Any] = {}
    try:
        from backend.market.scanner.scanner_service import get_market_scanner

        st = get_market_scanner().status()
        charts = st.get("charts") or {}
        breadth = charts.get("breadth") or {}
        rising = float(breadth.get("rising") or 0)
        falling = float(breadth.get("falling") or 0)
        total = max(1.0, rising + falling)
        components["breadth"] = (rising - falling) / total

        btc = next((c for c in get_market_scanner().candidates(limit=50) if c.get("symbol") == "BTCUSDT"), None)
        if btc:
            ch5 = float(btc.get("priceChange5mPct") or 0)
            components["price_momentum"] = max(-1.0, min(1.0, ch5 / 5.0))
            fr = btc.get("fundingRate")
            if fr is not None:
                components["funding_rate"] = max(-1.0, min(1.0, float(fr) * 1000))
            oi = btc.get("oiChange5mPct")
            if oi is not None:
                components["open_interest_change"] = max(-1.0, min(1.0, float(oi) / 10.0))
            vol = btc.get("volume24h")
            if vol is not None:
                components["volume_momentum"] = 0.3  # placeholder normalized until z-score wired
    except Exception:  # noqa: BLE001
        pass
    return components
