"""Print trading blockers from one live runtime tick (no secrets)."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return None

load_dotenv()


def _pick(obj, *keys, default=None):
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def main():
    from backend.services.nexus_runtime import NexusRuntime

    runtime = NexusRuntime()
    runtime.tick()

    snap = runtime.snapshot()
    system = snap.get("system", {}) or {}
    growth = snap.get("growth_mode", {}) or {}
    truth = snap.get("truth_layer_status", {}) or {}
    learning = snap.get("learning_status", {}) or {}
    portfolio = snap.get("portfolio_status", {}) or {}
    validation = snap.get("validation_status", {}) or {}
    capital = snap.get("capital", {}) or {}
    radar = snap.get("radar_dispatch", {}) or {}

    fleet_status = system.get("fleet_status", {}) or {}
    fleet_lines = []
    for fleet, data in sorted(fleet_status.items()):
        fleet_lines.append(
            f"  {fleet}: status={data.get('status')} signal={data.get('last_signal')} reason={data.get('last_reason')}"
        )

    learning_fleets = _pick(learning, "calibration_snapshot", "fleet_adjustments") or _pick(
        learning, "fleet_adjustments"
    ) or {}
    learning_lines = []
    for fleet, adj in sorted(learning_fleets.items()):
        if not isinstance(adj, dict):
            continue
        flags = []
        if adj.get("pause_new_entries"):
            flags.append("PAUSE_NEW_ENTRIES")
        if adj.get("consecutive_losses", 0) >= 3:
            flags.append(f"consecutive_losses={adj.get('consecutive_losses')}")
        if adj.get("blocked_regimes"):
            flags.append(f"blocked_regimes={adj.get('blocked_regimes')}")
        if flags:
            learning_lines.append(f"  {fleet}: " + ", ".join(flags))

    portfolio_lines = []
    for fleet, data in sorted((portfolio.get("fleet_restrictions") or {}).items()):
        if not data.get("allowed_new_entries", True):
            portfolio_lines.append(f"  {fleet}: blocked ({data.get('reasons')})")

    audit = snap.get("decision_audit", []) or []
    recent_rejects = [
        item
        for item in audit[:12]
        if not item.get("approved", True)
    ]

    report = {
        "worker": {
            "system_health": system.get("system_health"),
            "trading_paused": system.get("trading_paused"),
            "alert_level": system.get("alert_level"),
            "module_health": system.get("module_health"),
        },
        "capital": {
            "treasury_assets": capital.get("treasury_assets"),
            "total": capital.get("total"),
            "futures_usdt": capital.get("futures_total"),
            "spot_usdt": capital.get("spot_usdt_total"),
        },
        "growth_mode": growth,
        "truth_layer": {
            "futures_ready_for_ai": truth.get("futures_ready_for_ai"),
            "spot_ready_for_ai": truth.get("spot_ready_for_ai"),
            "stale_reasons": truth.get("stale_reasons"),
        },
        "binance_sync": snap.get("binance_sync"),
        "open_positions": [
            {
                "fleet": p.get("fleet"),
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "quantity": p.get("quantity"),
            }
            for p in (snap.get("positions") or [])
        ],
        "radar_dispatch": radar,
        "validation_status": validation,
        "recent_rejects": recent_rejects[:8],
        "strategy_adaptation": _pick(learning, "strategy_adaptation"),
    }

    print("=== NEXUS trading blocker diagnostic ===")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    print("\n=== Fleet status ===")
    print("\n".join(fleet_lines) or "  (none)")
    if learning_lines:
        print("\n=== Learning blocks ===")
        print("\n".join(learning_lines))
    if portfolio_lines:
        print("\n=== Portfolio blocks ===")
        print("\n".join(portfolio_lines))


if __name__ == "__main__":
    main()
