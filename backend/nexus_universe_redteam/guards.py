"""Universe lineage attack detectors — fail-closed seals and drift oracles.

These guards live in the V14-I owned package. They encode Point-in-Time
invariants research must obey for listing bias, rename/mapping/spec drift,
and survivorship-safe reconstruction. Attacks that violate a seal are blocked
by code; unresolved gaps remain explicit Critical blockers.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


CONTROL_FIXTURE_LABEL = "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def seal_instrument_observation(row: dict[str, Any], *, as_of_ms: int) -> dict[str, Any]:
    """Seal the fields that must not silently drift across eras for a PIT as_of."""
    body = {
        "symbol": row.get("symbol"),
        "as_of_ms": int(as_of_ms),
        "listing_ms": row.get("listing_ms"),
        "delisting_ms": row.get("delisting_ms"),
        "observation_ms": row.get("observation_ms"),
        "symbol_mapping": row.get("symbol_mapping"),
        "contract_type": row.get("contract_type"),
        "quote_coin": row.get("quote_coin"),
        "settle_coin": row.get("settle_coin"),
        "contract_specification": row.get("contract_specification") or {},
        "minimum_notional": row.get("minimum_notional"),
        "tick_size": row.get("tick_size"),
        "qty_step": row.get("qty_step"),
        "liquidity_score": row.get("liquidity_score"),
        "funding_available": row.get("funding_available"),
        "canonical_id": row.get("canonical_id") or row.get("symbol"),
        "rename_lineage_id": row.get("rename_lineage_id"),
    }
    return {"ok": True, "status": "SEALED", "seal": _sha(body), "body": body}


def verify_instrument_seal(
    row: dict[str, Any],
    *,
    as_of_ms: int,
    expected_seal: str,
) -> dict[str, Any]:
    sealed = seal_instrument_observation(row, as_of_ms=as_of_ms)
    if sealed["seal"] != expected_seal:
        return {
            "ok": False,
            "status": "INSTRUMENT_SEAL_MISMATCH",
            "expected": expected_seal,
            "actual": sealed["seal"],
        }
    return {"ok": True, "status": "PASS", "seal": sealed["seal"]}


def detect_survivorship_bias(
    *,
    claimed_symbols: list[str],
    pit_eligible_symbols: list[str],
    today_survivor_symbols: list[str],
) -> dict[str, Any]:
    """Survivor-only reconstruction that drops historically-listed names is bias."""
    claimed = set(claimed_symbols)
    pit = set(pit_eligible_symbols)
    survivors = set(today_survivor_symbols)
    # Attack shape: claimed == survivors ∩ pit (or survivors) while pit has more
    dropped_historical = sorted(pit - claimed)
    only_survivors = claimed.issubset(survivors) and len(dropped_historical) > 0
    missing_vs_pit = sorted(pit - claimed)
    extra = sorted(claimed - pit)
    biased = only_survivors or (len(missing_vs_pit) > 0 and claimed == (pit & survivors))
    return {
        "ok": not biased and claimed == pit,
        "status": "SURVIVORSHIP_BIAS" if biased or claimed != pit else "PASS",
        "dropped_historical": dropped_historical,
        "extra": extra,
        "claimed": sorted(claimed),
        "pit_eligible": sorted(pit),
        "today_survivors": sorted(survivors),
    }


def detect_listing_date_leakage(
    *,
    symbol: str,
    listing_ms: int | None,
    as_of_ms: int,
    claimed_eligible: bool,
) -> dict[str, Any]:
    listed = listing_ms is not None and int(listing_ms) <= int(as_of_ms)
    leak = bool(claimed_eligible) and not listed
    return {
        "ok": not leak,
        "status": "LISTING_DATE_LEAKAGE" if leak else "PASS",
        "symbol": symbol,
        "listing_ms": listing_ms,
        "as_of_ms": int(as_of_ms),
        "claimed_eligible": claimed_eligible,
    }


def detect_delisting_leakage(
    *,
    symbol: str,
    delisting_ms: int | None,
    as_of_ms: int,
    claimed_eligible: bool,
    historically_listed: bool,
) -> dict[str, Any]:
    still_listed = delisting_ms is None or int(delisting_ms) > int(as_of_ms)
    post_delist_leak = bool(claimed_eligible) and not still_listed
    # Also: excluding a symbol that was listed and not yet delisted at as_of
    # when reconstructing from a later survivor table (handled by survivorship).
    premature_drop = (
        historically_listed
        and still_listed
        and not claimed_eligible
        and delisting_ms is not None
        and int(delisting_ms) > int(as_of_ms)
    )
    leak = post_delist_leak
    return {
        "ok": not leak,
        "status": "DELISTING_LEAKAGE" if leak else "PASS",
        "symbol": symbol,
        "delisting_ms": delisting_ms,
        "as_of_ms": int(as_of_ms),
        "claimed_eligible": claimed_eligible,
        "premature_survivor_drop_hint": premature_drop,
    }


def detect_rename_leakage(
    *,
    old_symbol: str,
    new_symbol: str,
    rename_effective_ms: int,
    as_of_ms: int,
    rename_lineage_id: str | None,
    claimed_identity: str,
) -> dict[str, Any]:
    """Renames without lineage, or using post-rename identity before effective_ms."""
    has_lineage = bool(rename_lineage_id)
    used_new_before = (
        int(as_of_ms) < int(rename_effective_ms) and claimed_identity == new_symbol
    )
    silent = (not has_lineage) and old_symbol != new_symbol
    blocked = silent or used_new_before
    return {
        "ok": not blocked,
        "status": "RENAME_LEAKAGE" if blocked else "PASS",
        "old_symbol": old_symbol,
        "new_symbol": new_symbol,
        "rename_effective_ms": int(rename_effective_ms),
        "as_of_ms": int(as_of_ms),
        "rename_lineage_id": rename_lineage_id,
        "claimed_identity": claimed_identity,
        "used_new_before_effective": used_new_before,
        "silent_rename": silent,
    }


def detect_contract_spec_drift(
    *,
    sealed_spec: dict[str, Any],
    observed_spec: dict[str, Any],
    as_of_ms: int,
    observation_ms: int | None,
) -> dict[str, Any]:
    future_obs = observation_ms is not None and int(observation_ms) > int(as_of_ms)
    drifted = sealed_spec != observed_spec
    leak = future_obs or drifted
    return {
        "ok": not leak,
        "status": "CONTRACT_SPEC_DRIFT" if leak else "PASS",
        "future_observation": future_obs,
        "drifted": drifted,
        "sealed_spec": sealed_spec,
        "observed_spec": observed_spec,
    }


def detect_today_universe_substitution(
    *,
    as_of_ms: int,
    snapshot_availability_ms: int,
    source_kind: str,
    now_ms: int | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    if source_kind != "sanitized_fixture":
        reasons.append("unsupported_source_kind")
    if int(snapshot_availability_ms) > int(as_of_ms):
        reasons.append("today_or_future_universe_used_for_past_as_of")
    if now_ms is not None:
        day_ms = 86_400_000
        if int(now_ms) - int(as_of_ms) > day_ms and int(now_ms) - int(snapshot_availability_ms) < day_ms:
            reasons.append("live_today_snapshot_rejected_for_historical_as_of")
    return {
        "ok": len(reasons) == 0,
        "status": "TODAY_UNIVERSE_SUBSTITUTION" if reasons else "PASS",
        "reasons": reasons,
    }


def detect_future_liquidity_leakage(
    *,
    as_of_ms: int,
    observation_ms: int | None,
    liquidity_score: float | None,
    claimed_from_future_era: bool,
) -> dict[str, Any]:
    future_obs = observation_ms is not None and int(observation_ms) > int(as_of_ms)
    leak = future_obs or claimed_from_future_era
    return {
        "ok": not leak,
        "status": "FUTURE_LIQUIDITY_LEAKAGE" if leak else "PASS",
        "observation_ms": observation_ms,
        "as_of_ms": int(as_of_ms),
        "liquidity_score": liquidity_score,
        "claimed_from_future_era": claimed_from_future_era,
    }


def detect_future_funding_leakage(
    *,
    as_of_ms: int,
    observation_ms: int | None,
    funding_available: bool | None,
    historical_funding_available: bool | None,
) -> dict[str, Any]:
    future_obs = observation_ms is not None and int(observation_ms) > int(as_of_ms)
    # Using a future funding=True when historical was False
    upgraded = (
        historical_funding_available is False
        and funding_available is True
        and (future_obs or True)
        and historical_funding_available is False
        and funding_available is True
        and (future_obs or observation_ms != as_of_ms)
    )
    # Stricter: any funding claim observed after as_of is leakage
    leak = future_obs or (
        historical_funding_available is False
        and bool(funding_available)
        and (observation_ms is None or int(observation_ms) > int(as_of_ms))
    )
    return {
        "ok": not leak,
        "status": "FUTURE_FUNDING_LEAKAGE" if leak else "PASS",
        "future_observation": future_obs,
        "upgraded_from_historical_false": upgraded and leak,
        "funding_available": funding_available,
        "historical_funding_available": historical_funding_available,
    }


def detect_mapping_drift(
    *,
    sealed_mapping: str | None,
    observed_mapping: str | None,
    as_of_ms: int,
    observation_ms: int | None,
) -> dict[str, Any]:
    future_obs = observation_ms is not None and int(observation_ms) > int(as_of_ms)
    drifted = sealed_mapping != observed_mapping
    leak = future_obs or drifted
    return {
        "ok": not leak,
        "status": "MAPPING_DRIFT" if leak else "PASS",
        "sealed_mapping": sealed_mapping,
        "observed_mapping": observed_mapping,
        "future_observation": future_obs,
    }


def detect_min_notional_drift(
    *,
    sealed_min_notional: float | None,
    observed_min_notional: float | None,
    as_of_ms: int,
    observation_ms: int | None,
) -> dict[str, Any]:
    future_obs = observation_ms is not None and int(observation_ms) > int(as_of_ms)
    try:
        sealed_f = float(sealed_min_notional) if sealed_min_notional is not None else None
        observed_f = float(observed_min_notional) if observed_min_notional is not None else None
    except (TypeError, ValueError):
        sealed_f, observed_f = None, None
    drifted = sealed_f != observed_f
    leak = future_obs or drifted
    return {
        "ok": not leak,
        "status": "MIN_NOTIONAL_DRIFT" if leak else "PASS",
        "sealed_min_notional": sealed_f,
        "observed_min_notional": observed_f,
        "future_observation": future_obs,
    }


def require_attack_disposition(
    *,
    attack_blocked_by_code: bool,
    critical_blocker_code: str | None,
) -> dict[str, Any]:
    """Every attack must be blocked by code OR remain an explicit Critical blocker."""
    if attack_blocked_by_code:
        return {
            "ok": True,
            "status": "BLOCKED_BY_CODE",
            "critical_blocker_code": None,
        }
    if critical_blocker_code:
        return {
            "ok": True,
            "status": "EXPLICIT_CRITICAL_BLOCKER",
            "critical_blocker_code": critical_blocker_code,
        }
    return {
        "ok": False,
        "status": "UNRESOLVED_ATTACK_SURVIVOR",
        "critical_blocker_code": None,
    }
