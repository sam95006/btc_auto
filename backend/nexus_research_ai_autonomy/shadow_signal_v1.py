"""Shadow signal lifecycle — no exchange orders."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

SHADOW_SCHEMA = "v30_shadow_signal_v1"
LIFECYCLE_STATES = ("DETECTED", "WATCH", "READY", "INVALIDATED", "EXPIRED", "OUTCOME")


def shadow_dir(campaign_root: Path) -> Path:
    return campaign_root / "autonomy" / "shadow_signals"


def create_shadow_signal(
    snapshot: dict[str, Any],
    *,
    state: str = "DETECTED",
) -> dict[str, Any]:
    sid = f"sig_{uuid.uuid4().hex[:16]}"
    action = snapshot.get("final_action") or "WAIT"
    if action == "SELECT":
        state = "READY"
    elif action == "WATCH":
        state = "WATCH"
    return {
        "schema": SHADOW_SCHEMA,
        "signal_id": sid,
        "lifecycle_state": state,
        "detected_at_ms": snapshot.get("timestamp_ms"),
        "symbol": snapshot.get("symbol"),
        "direction": snapshot.get("side"),
        "entry_price": snapshot.get("price"),
        "expected_net_edge": snapshot.get("expected_net_edge"),
        "entry_quality_score": snapshot.get("entry_quality_score"),
        "direction_confidence_quant": snapshot.get("direction_confidence_quant"),
        "supporting_evidence": list(snapshot.get("supporting_evidence") or []),
        "contradicting_evidence": list(snapshot.get("contradicting_evidence") or []),
        "snapshot_decision_id": snapshot.get("decision_id"),
        "outcome": None,
    }


def persist_shadow_signals(campaign_root: Path, signals: list[dict[str, Any]]) -> Path:
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "active_shadow_signals.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for sig in signals:
            fh.write(json.dumps(sig, default=str) + "\n")
    active = d / "active_shadow_signals_latest.json"
    tmp = active.with_suffix(".tmp")
    tmp.write_text(json.dumps({"updated_at_ms": int(time.time() * 1000), "signals": signals}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(active)
    return path


def record_shadow_outcome(
    campaign_root: Path,
    *,
    signal_id: str,
    horizon_sec: int,
    mfe: float | None,
    mae: float | None,
    post_cost_hypothetical: float | None,
    target_before_stop: bool | None,
) -> None:
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "shadow_outcomes.jsonl"
    row = {
        "signal_id": signal_id,
        "horizon_sec": horizon_sec,
        "recorded_at_ms": int(time.time() * 1000),
        "MFE": mfe,
        "MAE": mae,
        "post_cost_hypothetical": post_cost_hypothetical,
        "target_before_stop": target_before_stop,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
