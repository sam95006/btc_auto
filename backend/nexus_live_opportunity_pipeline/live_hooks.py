"""LIVE_READ_ONLY adapter discovery hooks (honest; no exchange write)."""
from __future__ import annotations

import importlib
import os
from typing import Any

# Candidate adapter module paths (V18-A and existing tip surfaces).
_ADAPTER_CANDIDATES: tuple[str, ...] = (
    "backend.nexus_official_market_adapters",
    "backend.nexus_official_readonly_market_adapters",
    "backend.nexus_market_adapters",
    "backend.market.market_price_feed_service",
)


def discover_live_readonly_adapters() -> dict[str, Any]:
    """Probe for read-only market adapters without placing orders.

    Honest reporting: if no adapter package is importable, status is
    ADAPTERS_ABSENT and the pipeline stays on FIXTURE data_class.
    """
    found: list[dict[str, Any]] = []
    for mod_name in _ADAPTER_CANDIDATES:
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:  # noqa: BLE001 — discovery must never fail-open
            found.append(
                {
                    "module": mod_name,
                    "present": False,
                    "error": type(exc).__name__,
                }
            )
            continue
        write_markers = [
            name
            for name in ("place_order", "create_order", "submit_order", "demo_order")
            if hasattr(mod, name)
        ]
        found.append(
            {
                "module": mod_name,
                "present": True,
                "has_write_symbols": write_markers,
                "write_allowed": False,
                "mode": "LIVE_READ_ONLY",
            }
        )

    present = [x for x in found if x.get("present")]
    # Prefer dedicated V18 adapter packages over legacy market feed.
    dedicated = [
        x
        for x in present
        if "official" in x["module"] or x["module"].endswith("market_adapters")
    ]
    usable = dedicated or present
    env_enable = os.environ.get("NEXUS_V18_LIVE_READ_ONLY", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    if not usable:
        status = "ADAPTERS_ABSENT"
        data_class = "FIXTURE"
        live_probe_attempted = False
    elif not env_enable:
        status = "ADAPTERS_PRESENT_HOOK_IDLE"
        data_class = "FIXTURE"
        live_probe_attempted = False
    else:
        status = "LIVE_READ_ONLY_AVAILABLE"
        data_class = "LIVE_READ_ONLY"
        live_probe_attempted = True

    return {
        "status": status,
        "data_class_default": data_class,
        "env_gate": "NEXUS_V18_LIVE_READ_ONLY",
        "env_enabled": env_enable,
        "live_probe_attempted": live_probe_attempted,
        "candidates": found,
        "usable_modules": [x["module"] for x in usable],
        "exchange_write": False,
        "demo_orders": False,
        "mainnet_trading": False,
        "actual_ordered": False,
        "actual_filled": False,
        "note": (
            "Hooks are discovery-only. Fixture E2E is authoritative this lane; "
            "live reads require env gate and present adapters. Never Demo orders."
        ),
    }


def resolve_data_class(*, force_fixture: bool = True) -> tuple[str, dict[str, Any]]:
    hooks = discover_live_readonly_adapters()
    if force_fixture:
        return "FIXTURE", hooks
    return str(hooks["data_class_default"]), hooks
