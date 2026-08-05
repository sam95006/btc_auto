"""Real / local public-safe source readers for PUB-C.

LIVE mode: read real sources or return UNAVAILABLE/STALE/DEGRADED/BLOCKED.
Never fabricate values. Never silently substitute fixture data.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.nexus_public_live_data.constants import (
    ALLOWED_SYMBOLS,
    BYBIT_CATEGORY,
    BYBIT_PUBLIC_REST,
    BYBIT_TICKERS_PATH,
)
from backend.nexus_public_live_data.lineage import (
    LineageBoundValue,
    completeness_for,
    freshness_from_age,
    make_lineage_id,
    parse_iso,
    unavailable_bound,
    utc_iso,
    utc_now,
)

_UA = "NEXUS-PUB-C-LiveDataAdapter/1.0 (read-only; no orders)"


def _age_seconds(as_of: str | None, retrieved_at: str) -> float | None:
    dt = parse_iso(as_of)
    if dt is None:
        return None
    retrieved = parse_iso(retrieved_at) or utc_now()
    return max(0.0, (retrieved - dt).total_seconds())


def fetch_bybit_public_ticker(symbol: str, *, timeout: float = 8.0) -> dict[str, Any]:
    """Read-only Bybit Mainnet public ticker. No keys. No private endpoints."""
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError(f"symbol_not_allowlisted:{symbol}")
    qs = urllib.parse.urlencode({"category": BYBIT_CATEGORY, "symbol": symbol})
    url = f"{BYBIT_PUBLIC_REST}{BYBIT_TICKERS_PATH}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as raw:
        payload = json.loads(raw.read().decode("utf-8"))
    if int(payload.get("retCode", -1)) != 0:
        raise RuntimeError(payload.get("retMsg") or "bybit_error")
    rows = ((payload.get("result") or {}).get("list")) or []
    if not rows:
        raise RuntimeError(f"empty_ticker:{symbol}")
    return rows[0]


def bind_market_field(
    *,
    field_id: str,
    symbol: str,
    source_field: str,
    unit: str,
    extractor: Callable[[dict[str, Any]], Any],
    fetch: Callable[[str], dict[str, Any]] | None = None,
) -> LineageBoundValue:
    """Bind one market field from public REST. On failure → UNAVAILABLE (no fixture)."""
    endpoint = f"{BYBIT_PUBLIC_REST}{BYBIT_TICKERS_PATH}?category={BYBIT_CATEGORY}&symbol={symbol}"
    retrieved = utc_iso()
    try:
        fetcher = fetch or fetch_bybit_public_ticker
        row = fetcher(symbol)
        value = extractor(row)
        if value is None or value == "":
            return unavailable_bound(
                field_id=field_id,
                source_system="BYBIT_PUBLIC_REST",
                source_endpoint=endpoint,
                source_field=source_field,
                fallback="display_UNAVAILABLE",
                reason="source_field_empty",
                retrieved_at=retrieved,
            )
        # Prefer exchange timestamp when present
        ts_ms = row.get("ts")
        if ts_ms not in (None, ""):
            as_of = utc_iso(datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc))
        else:
            as_of = retrieved
        age = _age_seconds(as_of, retrieved)
        freshness = freshness_from_age(age, mode="LIVE", available=True)
        return LineageBoundValue(
            field_id=field_id,
            value=float(value) if unit in ("USD", "rate") else value,
            unit=unit,
            mode="LIVE",
            source_system="BYBIT_PUBLIC_REST",
            source_endpoint=endpoint,
            source_field=source_field,
            as_of=as_of,
            retrieved_at=retrieved,
            freshness=freshness,
            completeness=completeness_for(mode="LIVE", value=value),
            lineage_id=make_lineage_id(field_id, "BYBIT_PUBLIC_REST", as_of, retrieved),
            fallback="display_UNAVAILABLE_on_error",
            quality="public_read_only",
            demo_data=False,
            display_state=freshness,
            notes=["public_mainnet_linear_read_only", "no_api_keys"],
        )
    except Exception as exc:  # noqa: BLE001 — surface as UNAVAILABLE, never fabricate
        return unavailable_bound(
            field_id=field_id,
            source_system="BYBIT_PUBLIC_REST",
            source_endpoint=endpoint,
            source_field=source_field,
            fallback="display_UNAVAILABLE",
            reason=f"fetch_failed:{type(exc).__name__}",
            retrieved_at=retrieved,
        )


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def bind_runtime_health(*, runtime_root: Path | None = None) -> LineageBoundValue:
    """Bind local runtime health. Missing file → UNAVAILABLE (not fabricated OK)."""
    field_id = "system.runtime_health"
    root = runtime_root or Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME"))
    candidates = [
        root / "runtime_health.json",
        root / "ms_accum_v13_integrity_14d_health.json",
        Path.cwd() / "artifacts" / "runtime_health.json",
    ]
    endpoint = "file://runtime_health.json"
    retrieved = utc_iso()
    for path in candidates:
        data = _read_json_file(path)
        if data is None:
            continue
        status = data.get("status") or data.get("health") or data.get("integrity_status")
        as_of = data.get("as_of") or data.get("generated_at") or data.get("updated_at") or retrieved
        age = _age_seconds(str(as_of) if as_of else None, retrieved)
        freshness = freshness_from_age(age, mode="LIVE", available=status is not None)
        return LineageBoundValue(
            field_id=field_id,
            value=status,
            unit="status",
            mode="LIVE",
            source_system="LOCAL_RUNTIME",
            source_endpoint=f"file://{path.as_posix()}",
            source_field="status|health|integrity_status",
            as_of=str(as_of) if as_of else retrieved,
            retrieved_at=retrieved,
            freshness=freshness,
            completeness=completeness_for(mode="LIVE", value=status),
            lineage_id=make_lineage_id(field_id, "LOCAL_RUNTIME", str(as_of), retrieved),
            fallback="display_UNAVAILABLE",
            quality="local_file_read",
            demo_data=False,
            display_state=freshness,
            notes=[f"path={path.name}"],
        )
    return unavailable_bound(
        field_id=field_id,
        source_system="LOCAL_RUNTIME",
        source_endpoint=endpoint,
        source_field="status|health|integrity_status",
        fallback="display_UNAVAILABLE",
        reason="runtime_health_file_missing",
        retrieved_at=retrieved,
    )


def bind_capture_campaign_health(*, runtime_root: Path | None = None) -> LineageBoundValue:
    field_id = "system.capture_campaign_health"
    root = runtime_root or Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME"))
    path = root / "ms_accum_v13_integrity_14d_health.json"
    retrieved = utc_iso()
    data = _read_json_file(path)
    if data is None:
        return unavailable_bound(
            field_id=field_id,
            source_system="CAPTURE_SUPERVISOR",
            source_endpoint=f"file://{path.as_posix()}",
            source_field="health|status|integrity_status",
            fallback="display_UNAVAILABLE",
            reason="capture_health_unavailable",
            retrieved_at=retrieved,
        )
    status = data.get("integrity_status") or data.get("health") or data.get("status")
    as_of = data.get("as_of") or data.get("generated_at") or retrieved
    age = _age_seconds(str(as_of), retrieved)
    freshness = freshness_from_age(age, mode="LIVE", available=status is not None)
    return LineageBoundValue(
        field_id=field_id,
        value=status,
        unit="status",
        mode="LIVE",
        source_system="CAPTURE_SUPERVISOR",
        source_endpoint=f"file://{path.as_posix()}",
        source_field="integrity_status|health|status",
        as_of=str(as_of),
        retrieved_at=retrieved,
        freshness=freshness,
        completeness=completeness_for(mode="LIVE", value=status),
        lineage_id=make_lineage_id(field_id, "CAPTURE_SUPERVISOR", str(as_of), retrieved),
        fallback="display_UNAVAILABLE",
        quality="campaign_file_read",
        demo_data=False,
        display_state=freshness,
        notes=["campaign=ms_accum_v13_integrity_14d"],
    )


def bind_reflection_v23_progress(*, runtime_root: Path | None = None) -> LineageBoundValue:
    field_id = "system.reflection_v23_progress"
    root = runtime_root or Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME"))
    candidates = [
        root / "reflection_v23_checkpoint.json",
        root / "v23_checkpoint.json",
    ]
    retrieved = utc_iso()
    for path in candidates:
        data = _read_json_file(path)
        if data is None:
            continue
        status = data.get("checkpoint_status") or data.get("status") or data.get("terminal_status")
        as_of = data.get("as_of") or data.get("updated_at") or retrieved
        age = _age_seconds(str(as_of), retrieved)
        freshness = freshness_from_age(age, mode="LIVE", available=status is not None)
        return LineageBoundValue(
            field_id=field_id,
            value=status,
            unit="status",
            mode="LIVE",
            source_system="REFLECTION_V23_CHECKPOINT",
            source_endpoint=f"file://{path.as_posix()}",
            source_field="checkpoint_status|status|terminal_status",
            as_of=str(as_of),
            retrieved_at=retrieved,
            freshness=freshness,
            completeness=completeness_for(mode="LIVE", value=status),
            lineage_id=make_lineage_id(field_id, "REFLECTION_V23_CHECKPOINT", str(as_of), retrieved),
            fallback="display_UNAVAILABLE",
            quality="checkpoint_file_read",
            demo_data=False,
            display_state=freshness,
            notes=[f"path={path.name}"],
        )
    return unavailable_bound(
        field_id=field_id,
        source_system="REFLECTION_V23_CHECKPOINT",
        source_endpoint="file://reflection_v23_checkpoint.json",
        source_field="checkpoint_status|status|terminal_status",
        fallback="display_UNAVAILABLE",
        reason="checkpoint_unavailable",
        retrieved_at=retrieved,
    )


def bind_qualification_state() -> LineageBoundValue:
    """Public-safe honesty: qualification remains BLOCKED until formal readiness.

    This is not a fabricated positive — BLOCKED is the real authorized public state
    per Founder directive (no formal walk-forward / OOS).
    """
    field_id = "system.qualification_state"
    retrieved = utc_iso()
    value = "BLOCKED"
    return LineageBoundValue(
        field_id=field_id,
        value=value,
        unit="status",
        mode="LIVE",
        source_system="PUBLIC_POLICY",
        source_endpoint="policy://qualification_public_safe",
        source_field="qualification.state",
        as_of=retrieved,
        retrieved_at=retrieved,
        freshness="BLOCKED",
        completeness="BLOCKED",
        lineage_id=make_lineage_id(field_id, "PUBLIC_POLICY", retrieved, retrieved),
        fallback="display_BLOCKED",
        quality="directive_hard_ban_no_formal_oos",
        demo_data=False,
        display_state="BLOCKED",
        notes=["formal_walkforward_banned", "real_oos_banned", "public_safe_BLOCKED"],
    )


def bind_event_study_readiness() -> LineageBoundValue:
    field_id = "system.event_study_readiness"
    retrieved = utc_iso()
    value = "NOT_READY"
    return LineageBoundValue(
        field_id=field_id,
        value=value,
        unit="status",
        mode="LIVE",
        source_system="PUBLIC_POLICY",
        source_endpoint="policy://event_study_public_safe",
        source_field="event_study.readiness",
        as_of=retrieved,
        retrieved_at=retrieved,
        freshness="BLOCKED",
        completeness="BLOCKED",
        lineage_id=make_lineage_id(field_id, "PUBLIC_POLICY", retrieved, retrieved),
        fallback="display_BLOCKED",
        quality="directive_event_study_not_ready",
        demo_data=False,
        display_state="BLOCKED",
        notes=["event_study_NOT_READY"],
    )


def bind_qualification_ready_count() -> LineageBoundValue:
    field_id = "system.qualification_ready_count"
    retrieved = utc_iso()
    # Directive example: real qualification_ready_count=0 — not a fake positive.
    value = 0
    return LineageBoundValue(
        field_id=field_id,
        value=value,
        unit="count",
        mode="LIVE",
        source_system="PUBLIC_POLICY",
        source_endpoint="policy://qualification_ready_count",
        source_field="qualification.ready_count",
        as_of=retrieved,
        retrieved_at=retrieved,
        freshness="BLOCKED",
        completeness="COMPLETE",
        lineage_id=make_lineage_id(field_id, "PUBLIC_POLICY", retrieved, retrieved),
        fallback="display_BLOCKED",
        quality="directive_ready_count_zero",
        demo_data=False,
        display_state="BLOCKED",
        notes=["qualification_ready_count=0", "no_fake_positive"],
    )


def bind_decision_cloud_freshness(*, decision_cloud_meta: dict[str, Any] | None = None) -> LineageBoundValue:
    field_id = "decision.cloud.freshness"
    retrieved = utc_iso()
    if not decision_cloud_meta:
        return unavailable_bound(
            field_id=field_id,
            source_system="PUBLIC_DECISION_CLOUD",
            source_endpoint="/api/public/decision-cloud/freshness",
            source_field="freshness.band",
            fallback="display_UNAVAILABLE",
            reason="decision_cloud_not_bound",
            retrieved_at=retrieved,
        )
    band = decision_cloud_meta.get("band") or decision_cloud_meta.get("freshness_band")
    as_of = decision_cloud_meta.get("as_of") or retrieved
    age = _age_seconds(str(as_of), retrieved)
    freshness = freshness_from_age(age, mode="LIVE", available=band is not None)
    return LineageBoundValue(
        field_id=field_id,
        value=band,
        unit="band",
        mode="LIVE",
        source_system="PUBLIC_DECISION_CLOUD",
        source_endpoint="/api/public/decision-cloud/freshness",
        source_field="freshness.band",
        as_of=str(as_of),
        retrieved_at=retrieved,
        freshness=freshness,
        completeness=completeness_for(mode="LIVE", value=band),
        lineage_id=make_lineage_id(field_id, "PUBLIC_DECISION_CLOUD", str(as_of), retrieved),
        fallback="display_UNAVAILABLE",
        quality="decision_cloud_binding",
        demo_data=False,
        display_state=freshness,
        notes=["sanitized_public_dto_only"],
    )


def bind_decision_cloud_availability(*, available: bool | None = None) -> LineageBoundValue:
    field_id = "decision.cloud.availability"
    retrieved = utc_iso()
    if available is None:
        return unavailable_bound(
            field_id=field_id,
            source_system="PUBLIC_DECISION_CLOUD",
            source_endpoint="/api/public/decision-cloud/meta",
            source_field="availability.status",
            fallback="display_UNAVAILABLE",
            reason="decision_cloud_availability_unknown",
            retrieved_at=retrieved,
        )
    value = "AVAILABLE" if available else "UNAVAILABLE"
    freshness = "FRESH" if available else "UNAVAILABLE"
    return LineageBoundValue(
        field_id=field_id,
        value=value,
        unit="status",
        mode="LIVE",
        source_system="PUBLIC_DECISION_CLOUD",
        source_endpoint="/api/public/decision-cloud/meta",
        source_field="availability.status",
        as_of=retrieved,
        retrieved_at=retrieved,
        freshness=freshness,
        completeness=completeness_for(mode="LIVE", value=value),
        lineage_id=make_lineage_id(field_id, "PUBLIC_DECISION_CLOUD", retrieved, retrieved),
        fallback="display_UNAVAILABLE",
        quality="decision_cloud_probe",
        demo_data=False,
        display_state=value,
        notes=[],
    )
