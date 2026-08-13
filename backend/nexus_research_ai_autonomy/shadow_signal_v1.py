"""Shadow signal lifecycle — no exchange orders.

Immutable origin ledger: active_shadow_signals.jsonl (append-only, dedupe by signal_id).
Convenience only: active_shadow_signals_latest.json (current cycle batch).
Persistent lifecycle: shadow_signal_state.json (keyed by signal_id).
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

SHADOW_SCHEMA = "v30_shadow_signal_v1"
STATE_SCHEMA = "v30_shadow_signal_state_v1"
LIFECYCLE_STATES = (
    "DETECTED",
    "WATCH",
    "READY",
    "PARTIAL_OUTCOME",
    "INVALIDATED",
    "EXPIRED",
    "OUTCOME",
)
HORIZON_LABELS = {60: "1m", 180: "3m", 300: "5m", 900: "15m", 1800: "30m"}
REQUIRED_HORIZONS_SEC = (60, 180, 300, 900, 1800)


def shadow_dir(campaign_root: Path) -> Path:
    return campaign_root / "autonomy" / "shadow_signals"


def signal_ledger_path(campaign_root: Path) -> Path:
    return shadow_dir(campaign_root) / "active_shadow_signals.jsonl"


def signal_state_path(campaign_root: Path) -> Path:
    return shadow_dir(campaign_root) / "shadow_signal_state.json"


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
        "regime": snapshot.get("regime"),
        "market_structure": snapshot.get("market_structure"),
        "snapshot_decision_id": snapshot.get("decision_id"),
        "outcome": None,
    }


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def ledger_stats(campaign_root: Path) -> dict[str, Any]:
    rows = _read_jsonl_rows(signal_ledger_path(campaign_root))
    ids = [str(r.get("signal_id") or "") for r in rows if r.get("signal_id")]
    unique = set(ids)
    return {
        "ledger_rows": len(rows),
        "unique_signal_ids": len(unique),
        "duplicate_signal_rows": max(0, len(ids) - len(unique)),
    }


def load_shadow_signal_ledger(campaign_root: Path) -> list[dict[str, Any]]:
    """Load unique origin signals from append-only JSONL (first row wins per signal_id)."""
    rows = _read_jsonl_rows(signal_ledger_path(campaign_root))
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        sid = str(row.get("signal_id") or "")
        if not sid or sid in by_id:
            continue
        by_id[sid] = row
    return list(by_id.values())


def load_active_shadow_signals(campaign_root: Path) -> list[dict[str, Any]]:
    """Historical lifecycle source = unique ledger (NOT latest batch overwrite file)."""
    return load_shadow_signal_ledger(campaign_root)


def load_signal_state(campaign_root: Path) -> dict[str, Any]:
    path = signal_state_path(campaign_root)
    if not path.exists():
        return {"schema": STATE_SCHEMA, "signals": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"schema": STATE_SCHEMA, "signals": {}}
    if not isinstance(raw, dict):
        return {"schema": STATE_SCHEMA, "signals": {}}
    signals = raw.get("signals")
    if not isinstance(signals, dict):
        signals = {}
    return {"schema": STATE_SCHEMA, "signals": signals, "updated_at_ms": raw.get("updated_at_ms")}


def save_signal_state(campaign_root: Path, state: dict[str, Any]) -> None:
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    path = signal_state_path(campaign_root)
    payload = {
        "schema": STATE_SCHEMA,
        "updated_at_ms": int(time.time() * 1000),
        "signals": dict(state.get("signals") or {}),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def ensure_signal_state_entry(
    state: dict[str, Any],
    signal: dict[str, Any],
) -> dict[str, Any]:
    signals = state.setdefault("signals", {})
    sid = str(signal.get("signal_id") or "")
    if not sid:
        return {}
    existing = signals.get(sid)
    if isinstance(existing, dict) and existing:
        return existing
    original = str(signal.get("lifecycle_state") or "DETECTED")
    entry = {
        "signal_id": sid,
        "decision_id": signal.get("snapshot_decision_id") or signal.get("decision_id"),
        "created_at_ms": signal.get("detected_at_ms"),
        "original_lifecycle_state": original,
        "lifecycle_state": original,
        "completed_horizons": {HORIZON_LABELS[h]: False for h in REQUIRED_HORIZONS_SEC},
        "completed_horizon_secs": [],
        "horizon_unavailable": {},
        "first_outcome_at_ms": None,
        "last_outcome_at_ms": None,
        "fully_matured": False,
    }
    signals[sid] = entry
    return entry


def mark_horizon_complete(
    entry: dict[str, Any],
    *,
    horizon_sec: int,
    now_ms: int,
    unavailable_reason: str | None = None,
) -> None:
    label = HORIZON_LABELS.get(int(horizon_sec), str(horizon_sec))
    completed = dict(entry.get("completed_horizons") or {})
    secs = list(entry.get("completed_horizon_secs") or [])
    if unavailable_reason:
        unavail = dict(entry.get("horizon_unavailable") or {})
        unavail[label] = unavailable_reason
        entry["horizon_unavailable"] = unavail
        completed[label] = True  # resolved (unavailable still counts as resolved for maturity gate)
    else:
        completed[label] = True
    if int(horizon_sec) not in secs:
        secs.append(int(horizon_sec))
    entry["completed_horizons"] = completed
    entry["completed_horizon_secs"] = secs
    if entry.get("first_outcome_at_ms") is None and unavailable_reason is None:
        entry["first_outcome_at_ms"] = now_ms
    entry["last_outcome_at_ms"] = now_ms

    required_labels = [HORIZON_LABELS[h] for h in REQUIRED_HORIZONS_SEC]
    fully = all(bool(completed.get(lbl)) for lbl in required_labels)
    entry["fully_matured"] = fully
    if fully:
        entry["lifecycle_state"] = "OUTCOME"
    elif any(bool(completed.get(lbl)) for lbl in required_labels):
        # Keep evaluable; do not freeze at first horizon
        if entry.get("lifecycle_state") not in {"INVALIDATED", "EXPIRED", "OUTCOME"}:
            entry["lifecycle_state"] = "PARTIAL_OUTCOME"


def pending_horizons_for_signal(
    entry: dict[str, Any],
    *,
    existing_keys: set[tuple[str, int]],
    signal_id: str,
    horizons: tuple[int, ...] = REQUIRED_HORIZONS_SEC,
) -> list[int]:
    completed = entry.get("completed_horizons") or {}
    out: list[int] = []
    for h in horizons:
        label = HORIZON_LABELS.get(h, str(h))
        if completed.get(label):
            continue
        if (signal_id, int(h)) in existing_keys:
            continue
        out.append(int(h))
    return out


def persist_shadow_signals(campaign_root: Path, signals: list[dict[str, Any]]) -> Path:
    """Append NEW origin signals only; latest file = current-cycle convenience snapshot."""
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    ledger = signal_ledger_path(campaign_root)
    existing = {str(s.get("signal_id") or "") for s in load_shadow_signal_ledger(campaign_root)}
    new_rows = [s for s in signals if str(s.get("signal_id") or "") and str(s.get("signal_id")) not in existing]
    if new_rows:
        with ledger.open("a", encoding="utf-8") as fh:
            for sig in new_rows:
                fh.write(json.dumps(sig, default=str) + "\n")
        state = load_signal_state(campaign_root)
        for sig in new_rows:
            ensure_signal_state_entry(state, sig)
        save_signal_state(campaign_root, state)

    active = d / "active_shadow_signals_latest.json"
    tmp = active.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "updated_at_ms": int(time.time() * 1000),
                "signals": signals,
                "note": "current_cycle_convenience_only_not_historical_lifecycle_source",
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(active)
    return ledger


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
