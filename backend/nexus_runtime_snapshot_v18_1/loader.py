"""Fail-closed loader: read public-safe projection files from RUNTIME_ROOT only.

Never imports private Phase A conductor code — reads JSON artifacts only.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_runtime_snapshot_v18_1.constants import (
    DEFAULT_RUNTIME_ROOT,
    EXIT_FILENAME,
    HEARTBEAT_FILENAME,
    METRICS_FILENAME,
    PRIVATE_BAN_FIELDS,
    PROJECTION_FILENAME,
    PUBLIC_RUNTIME_STATES,
    REQUIRED_SNAPSHOT_FIELDS,
    SCHEMA,
    SCHEMA_VERSION,
    STALE_AFTER_SECONDS,
)


class SnapshotLoadError(RuntimeError):
    """Fail-closed snapshot load / projection violation."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # as_of ms epoch from projection
        try:
            ms = float(value)
            if ms > 1e12:
                return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
            return datetime.fromtimestamp(ms, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_runtime_root(explicit: Path | str | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get("NEXUS_LIVE_SHADOW_RUNTIME_ROOT") or os.environ.get(
        "NEXUS_RUNTIME_SNAPSHOT_ROOT"
    )
    if env:
        return Path(env)
    return Path(DEFAULT_RUNTIME_ROOT)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _read_projection_tail(path: Path, limit: int = 20) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def map_public_runtime_state(raw: str | None) -> str:
    """Map conductor state → member-facing RUNNING/DEGRADED/PAUSED/STOPPED/UNAVAILABLE."""
    if not raw:
        return "UNAVAILABLE"
    s = str(raw).upper().strip()
    if s in PUBLIC_RUNTIME_STATES:
        return s
    if s in {"STOPPING", "FAILED_SAFE"}:
        return "STOPPED"
    if s in {"BACKOFF"}:
        return "DEGRADED"
    if s in {"STARTING", "PREFLIGHT"}:
        return "UNAVAILABLE"
    return "UNAVAILABLE"


def _scrub_projection_row(row: dict[str, Any]) -> dict[str, Any]:
    """Allow-list projection ingest: drop private keys; refuse non-null secrets/order IDs."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        key_l = str(key).lower()
        banned = key_l in PRIVATE_BAN_FIELDS or any(
            ban in key_l
            for ban in ("secret", "api_key", "private_key", "wallet", "founder_capital")
        )
        if banned:
            # Phase A public writer stamps exchange_order_id=null — drop, never emit.
            if value in (None, "", False, 0) and key_l in {
                "exchange_order_id",
                "order_id",
                "client_order_id",
                "fill_id",
            }:
                continue
            raise SnapshotLoadError(f"private_field_banned:{key}")
        if isinstance(value, dict):
            out[key] = _scrub_projection_row(value)
        else:
            out[key] = value
    return out


def _assert_no_private_keys(payload: dict[str, Any], prefix: str = "") -> None:
    for key, value in payload.items():
        key_l = str(key).lower()
        if key_l in PRIVATE_BAN_FIELDS or any(
            ban in key_l
            for ban in ("secret", "api_key", "private_key", "wallet", "founder_capital")
        ):
            raise SnapshotLoadError(f"private_field_banned:{prefix}{key}")
        if isinstance(value, dict):
            _assert_no_private_keys(value, prefix=f"{prefix}{key}.")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    _assert_no_private_keys(item, prefix=f"{prefix}{key}[{i}].")


def _source_health(metrics: dict[str, Any], runtime_state: str) -> dict[str, Any]:
    ok = int(metrics.get("source_read_success_count") or 0)
    fail = int(metrics.get("source_read_failure_count") or 0)
    if runtime_state in {"STOPPED", "UNAVAILABLE"}:
        status = "STOPPED" if runtime_state == "STOPPED" else "UNAVAILABLE"
    elif fail > 0 and ok == 0:
        status = "DEGRADED"
    elif fail > 0:
        status = "PARTIAL"
    elif ok > 0:
        status = "HEALTHY"
    else:
        status = "UNAVAILABLE"
    return {
        "status": status,
        "source_read_success_count": ok,
        "source_read_failure_count": fail,
        "live_records_ingested": int(metrics.get("live_records_ingested") or 0),
        "records_quarantined": int(metrics.get("records_quarantined") or 0),
    }


def _universe_funnel(metrics: dict[str, Any], *, counts_available: bool) -> dict[str, Any]:
    if not counts_available:
        return {
            "contracts_scanned": None,
            "eligible": None,
            "observe_only": None,
            "blocked": None,
            "candidates": None,
            "display": {
                "contracts_scanned": "UNAVAILABLE",
                "eligible": "UNAVAILABLE",
                "observe_only": "UNAVAILABLE",
                "blocked": "UNAVAILABLE",
                "candidates": "UNAVAILABLE",
            },
            "available": False,
        }

    scanned = int(metrics.get("total_contracts_seen") or 0)
    eligible = int(metrics.get("eligible_contracts_latest") or 0)
    observe = int(metrics.get("observe_only_contracts_latest") or 0)
    blocked = int(metrics.get("blocked_contracts_latest") or 0)
    candidates = int(metrics.get("candidates_generated") or 0)
    return {
        "contracts_scanned": scanned,
        "eligible": eligible,
        "observe_only": observe,
        "blocked": blocked,
        "candidates": candidates,
        "display": {
            "contracts_scanned": str(scanned),
            "eligible": str(eligible),
            "observe_only": str(observe),
            "blocked": str(blocked),
            "candidates": str(candidates),
        },
        "available": True,
    }


def _decision_counts(metrics: dict[str, Any], *, counts_available: bool) -> dict[str, Any]:
    keys = ("LONG", "SHORT", "WAIT", "ABSTAIN", "BLOCK")
    if not counts_available:
        return {
            **{k: None for k in keys},
            "display": {k: "UNAVAILABLE" for k in keys},
            "available": False,
        }
    counts = {k: int(metrics.get(f"{k}_count") or 0) for k in keys}
    return {
        **counts,
        "display": {k: str(counts[k]) for k in keys},
        "available": True,
    }


def _ai_gateway_status(metrics: dict[str, Any], runtime_state: str) -> dict[str, Any]:
    req = int(metrics.get("AI_requests") or 0)
    ok = int(metrics.get("AI_success") or 0)
    timeout = int(metrics.get("AI_timeout") or 0)
    invalid = int(metrics.get("AI_invalid_json") or 0)
    if runtime_state in {"STOPPED", "UNAVAILABLE"}:
        health = "STOPPED" if runtime_state == "STOPPED" else "UNAVAILABLE"
    elif timeout or invalid:
        health = "DEGRADED"
    elif req > 0 and ok == req:
        health = "HEALTHY"
    elif req > 0:
        health = "PARTIAL"
    else:
        health = "UNAVAILABLE"
    return {
        "health": health,
        "AI_requests": req,
        "AI_success": ok,
        "AI_timeout": timeout,
        "AI_invalid_json": invalid,
        "deterministic_fallback_count": int(metrics.get("deterministic_fallback_count") or 0),
        "provider_capacity_blocked_count": int(
            metrics.get("provider_capacity_blocked_count") or 0
        ),
    }


def _shadow_status(metrics: dict[str, Any], last_proj: dict[str, Any] | None) -> dict[str, Any]:
    decision = None
    symbol = None
    if last_proj:
        decision = last_proj.get("decision") or (last_proj.get("final_shadow_decision") or {}).get(
            "decision"
        )
        symbol = last_proj.get("symbol")
    return {
        "shadow_opened_count": int(metrics.get("shadow_opened_count") or 0),
        "shadow_closed_count": int(metrics.get("shadow_closed_count") or 0),
        "last_decision": decision,
        "last_symbol": symbol,
        "virtual_research_position": bool(
            (last_proj or {}).get("virtual_research_position") or False
        ),
        "sealed": bool((last_proj or {}).get("sealed") or False),
    }


def _top_opportunities(
    projections: list[dict[str, Any]],
    *,
    is_live_view: bool,
    display_label: str,
) -> list[dict[str, Any]]:
    """Public-safe opportunity rows from recent projections (no private fields)."""
    if display_label in {"UNAVAILABLE"} and not projections:
        return []
    # Dedupe by symbol, newest first.
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for proj in reversed(projections):
        symbol = str(proj.get("symbol") or "").strip()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        decision = str(
            proj.get("decision")
            or (proj.get("final_shadow_decision") or {}).get("decision")
            or "ABSTAIN"
        ).upper()
        note = (
            f"{display_label} · shadow research only"
            if not is_live_view
            else "Live catalog shadow decision · not an order"
        )
        rows.append(
            {
                "rank": len(rows) + 1,
                "market": symbol,
                "contract": f"{symbol}.PERP",
                "side_hint": decision,
                "note": note,
            }
        )
        if len(rows) >= 3:
            break
    return rows


def _degraded_reasons(
    metrics: dict[str, Any],
    runtime_state: str,
    data_class: str,
    heartbeat_age_sec: float | None,
) -> list[str]:
    reasons: list[str] = []
    if runtime_state == "STOPPED":
        reasons.append("runtime_stopped")
    if runtime_state == "UNAVAILABLE":
        reasons.append("runtime_unavailable")
    if runtime_state == "DEGRADED":
        reasons.append("runtime_degraded")
    if data_class in {"LIVE_PARTIAL_DEGRADED", "FAILED_SAFE"}:
        reasons.append(f"data_class:{data_class}")
    if int(metrics.get("eligible_contracts_latest") or 0) == 0 and int(
        metrics.get("total_contracts_seen") or 0
    ) > 0:
        reasons.append("eligible_zero_fail_closed")
    if int(metrics.get("source_read_failure_count") or 0) > 0:
        reasons.append("source_read_failures")
    if int(metrics.get("provider_capacity_blocked_count") or 0) > 0:
        reasons.append("provider_capacity_blocked")
    if heartbeat_age_sec is not None and heartbeat_age_sec > STALE_AFTER_SECONDS:
        reasons.append("heartbeat_stale")
    return reasons


def _lineage_id(
    *,
    runtime_state: str,
    started_at: str | None,
    last_cycle_at: str | None,
    last_proj: dict[str, Any] | None,
) -> str:
    seed = "|".join(
        [
            runtime_state,
            started_at or "",
            last_cycle_at or "",
            str((last_proj or {}).get("shadow_decision_id") or ""),
            str((last_proj or {}).get("as_of") or ""),
        ]
    )
    return "lin_v18_1_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def compute_freshness_and_label(
    *,
    runtime_state: str,
    heartbeat_at: datetime | None,
    now: datetime | None = None,
    data_class_raw: str | None = None,
) -> tuple[str, str, bool]:
    """Return (data_freshness, display_label, is_live_view).

    If runtime not running: MUST NOT present old data as Live.
    """
    now = now or _utc_now()
    if runtime_state == "UNAVAILABLE":
        return "UNAVAILABLE", "UNAVAILABLE", False
    if runtime_state == "STOPPED":
        return "RUNTIME_STOPPED", "RUNTIME_STOPPED", False
    if runtime_state == "PAUSED":
        return "STALE", "PAUSED", False

    age = None
    if heartbeat_at is not None:
        age = (now - heartbeat_at).total_seconds()
        if age > STALE_AFTER_SECONDS:
            return "STALE", "STALE", False

    if runtime_state == "DEGRADED":
        # Degraded may still be live view, but never bare LIVE chrome.
        dc = (data_class_raw or "LIVE_PARTIAL_DEGRADED").upper()
        if "PARTIAL" in dc or "DEGRADED" in dc:
            return "LIVE_PARTIAL_DEGRADED", "DEGRADED", True
        return "STALE", "DEGRADED", True

    # RUNNING
    dc = (data_class_raw or "LIVE_READ_ONLY").upper()
    if dc in {"LIVE_READ_ONLY", "BOUNDED_LIVE_SMOKE"}:
        return "LIVE_READ_ONLY", "RUNNING", True
    if "PARTIAL" in dc or "DEGRADED" in dc:
        return "LIVE_PARTIAL_DEGRADED", "DEGRADED", True
    return "LIVE_READ_ONLY", "RUNNING", True


def load_runtime_snapshot(
    runtime_root: Path | str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Load shared public-safe Runtime Snapshot from D:\\NEXUS_RUNTIME projection files."""
    now = now or _utc_now()
    root = resolve_runtime_root(runtime_root)
    heartbeat = _read_json(root / HEARTBEAT_FILENAME)
    metrics = _read_json(root / METRICS_FILENAME) or {}
    exit_meta = _read_json(root / EXIT_FILENAME) or {}
    projections = _read_projection_tail(root / PROJECTION_FILENAME)

    if heartbeat is None and not metrics and not projections:
        snap = _unavailable_snapshot(
            root=root,
            error="runtime_projection_missing",
            now=now,
        )
        return snap

    # Prefer heartbeat metrics when present.
    if isinstance(heartbeat.get("metrics"), dict) and heartbeat["metrics"]:
        metrics = {**metrics, **heartbeat["metrics"]}

    raw_state = (
        (heartbeat or {}).get("runtime_state")
        or exit_meta.get("runtime_state")
        or ("STOPPED" if exit_meta else None)
    )
    runtime_state = map_public_runtime_state(str(raw_state) if raw_state else None)

    heartbeat_at = _parse_ts((heartbeat or {}).get("heartbeat_at"))
    started_at = _parse_ts(
        (heartbeat or {}).get("started_at") or exit_meta.get("started_at")
    )
    last_cycle_at = _parse_ts(
        (heartbeat or {}).get("last_successful_cycle_at")
        or exit_meta.get("last_successful_cycle_at")
    )
    age = (now - heartbeat_at).total_seconds() if heartbeat_at else None

    data_class_raw = str(
        (heartbeat or {}).get("data_class")
        or exit_meta.get("data_class")
        or (projections[-1].get("data_class") if projections else None)
        or "UNAVAILABLE"
    ).upper()

    data_freshness, display_label, is_live_view = compute_freshness_and_label(
        runtime_state=runtime_state,
        heartbeat_at=heartbeat_at,
        now=now,
        data_class_raw=data_class_raw,
    )

    # Public data_class honesty: never claim LIVE chrome when not live view.
    if not is_live_view:
        if runtime_state == "STOPPED":
            data_class = "RUNTIME_STOPPED"
        elif display_label == "STALE" or data_freshness == "STALE":
            data_class = "STALE"
        else:
            data_class = "UNAVAILABLE"
    else:
        data_class = (
            "LIVE_PARTIAL_DEGRADED"
            if "PARTIAL" in data_class_raw or runtime_state == "DEGRADED"
            else "LIVE_READ_ONLY"
        )

    # Counts may be shown when we have metrics, but labeled non-live when stopped/stale.
    counts_available = bool(metrics)
    projections = [_scrub_projection_row(p) for p in projections]
    last_proj = projections[-1] if projections else None
    if last_proj:
        _assert_no_private_keys(last_proj)

    source_health = _source_health(metrics, runtime_state)
    universe = _universe_funnel(metrics, counts_available=counts_available)
    decisions = _decision_counts(metrics, counts_available=counts_available)
    ai_status = _ai_gateway_status(metrics, runtime_state)
    shadow = _shadow_status(metrics, last_proj)
    top = _top_opportunities(
        projections, is_live_view=is_live_view, display_label=display_label
    )
    degraded = _degraded_reasons(metrics, runtime_state, data_class_raw, age)

    as_of = _iso(last_cycle_at or heartbeat_at or now)
    started_iso = _iso(started_at)
    last_cycle_iso = _iso(last_cycle_at)
    lineage = _lineage_id(
        runtime_state=runtime_state,
        started_at=started_iso,
        last_cycle_at=last_cycle_iso,
        last_proj=last_proj,
    )

    snap: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "runtime_state": runtime_state,
        "runtime_started_at": started_iso,
        "runtime_last_cycle_at": last_cycle_iso,
        "data_freshness": data_freshness,
        "source_health": source_health,
        "universe_funnel": universe,
        "decision_counts": decisions,
        "top_opportunities": top,
        "shadow_status": shadow,
        "AI_gateway_status": ai_status,
        "degraded_reasons": degraded,
        "actual_ordered": False,
        "actual_filled": False,
        "data_class": data_class,
        "as_of": as_of,
        "lineage_id": lineage,
        "display_label": display_label,
        "chrome_label": display_label,
        "binding_mode": "runtime_projection_files",
        "is_live_view": is_live_view,
        "last_updated": _iso(heartbeat_at or last_cycle_at or now),
        "heartbeat_at": _iso(heartbeat_at),
        "source_path": str(root),
        "projection_count": len(projections),
        "read_only": True,
        "trade_buttons": False,
        "fixture_as_live_count": 0,
        "private_field_leak_count": 0,
        "member_execution_control_count": 0,
        "note": (
            f"{display_label} · read-only runtime projection binding · "
            "Shadow Decisions only · NOT INVESTMENT ADVICE · no trade buttons"
        ),
    }

    if not is_live_view and data_class in {
        "LIVE_READ_ONLY",
        "LIVE_PARTIAL_DEGRADED",
        "LIVE",
    }:
        raise SnapshotLoadError("stale_or_stopped_presented_as_live")

    for field in REQUIRED_SNAPSHOT_FIELDS:
        if field not in snap:
            raise SnapshotLoadError(f"missing_required_field:{field}")

    _assert_no_private_keys(snap)
    return snap


def _unavailable_snapshot(
    *,
    root: Path,
    error: str,
    now: datetime,
) -> dict[str, Any]:
    as_of = _iso(now)
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "error": error,
        "runtime_state": "UNAVAILABLE",
        "runtime_started_at": None,
        "runtime_last_cycle_at": None,
        "data_freshness": "UNAVAILABLE",
        "source_health": {
            "status": "UNAVAILABLE",
            "source_read_success_count": 0,
            "source_read_failure_count": 0,
            "live_records_ingested": 0,
            "records_quarantined": 0,
        },
        "universe_funnel": _universe_funnel({}, counts_available=False),
        "decision_counts": _decision_counts({}, counts_available=False),
        "top_opportunities": [],
        "shadow_status": {
            "shadow_opened_count": 0,
            "shadow_closed_count": 0,
            "last_decision": None,
            "last_symbol": None,
            "virtual_research_position": False,
            "sealed": False,
        },
        "AI_gateway_status": {
            "health": "UNAVAILABLE",
            "AI_requests": 0,
            "AI_success": 0,
            "AI_timeout": 0,
            "AI_invalid_json": 0,
            "deterministic_fallback_count": 0,
            "provider_capacity_blocked_count": 0,
        },
        "degraded_reasons": ["runtime_projection_missing"],
        "actual_ordered": False,
        "actual_filled": False,
        "data_class": "UNAVAILABLE",
        "as_of": as_of,
        "lineage_id": "lin_v18_1_unavailable",
        "display_label": "UNAVAILABLE",
        "chrome_label": "UNAVAILABLE",
        "binding_mode": "runtime_projection_files",
        "is_live_view": False,
        "last_updated": as_of,
        "heartbeat_at": None,
        "source_path": str(root),
        "projection_count": 0,
        "read_only": True,
        "trade_buttons": False,
        "fixture_as_live_count": 0,
        "private_field_leak_count": 0,
        "member_execution_control_count": 0,
        "note": "UNAVAILABLE · runtime projection missing · fail-closed · no fabricated Live",
    }
