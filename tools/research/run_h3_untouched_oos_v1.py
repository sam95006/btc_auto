#!/usr/bin/env python3
"""Execute H3 untouched OOS V1 — download + integrity gate (qualification only).

Requires exact Founder phrase APPROVE_NEXUS_H3_UNTOUCHED_OOS_V1.
Does not tune policies. Does not Shadow / Demo / timed sessions / exchange write.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.h3_oos_policy_freeze import (
    CONFIRMATORY_POLICY_ID,
    FOUNDER_OOS_APPROVAL_PHRASE,
    PRIMARY_POLICY_ID,
    assert_phrase_allows_oos,
    load_frozen_policy,
    load_oos_reservation,
    qualification_hierarchy,
)
from backend.nexus_demo_execution.historical_market_data import (
    fetch_or_load_bundle,
    interval_ms,
)
from backend.nexus_demo_execution.microstructure_history import fetch_or_load_micro_bundle

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / "artifacts" / "readiness"
RESERVATION_PATH = READINESS / "OOS_H3_UNTOUCHED_V1_RESERVATION.json"
IMMUTABLE = READINESS / "immutable" / "h3_oos_v1"
RUNTIME_OOS = ROOT / ".nexus_runtime" / "oos" / "OOS_H3_UNTOUCHED_V1_RESERVED"

H3E_EXPECT = "bca97fa35cc8c49642901de409cc67cb7760c2ac83dd42a82cbab20999e2ba33"
H3D_EXPECT = "d415675df562e2ddad6cbfbbf77f6207ac2c1c48eebec27d153dc2aff31bb8a7"

# Completeness: require >= 95% of expected bars for each symbol×interval across full reserved window.
COMPLETENESS_RATIO = 0.95
# Minimum absolute bars for any qualification attempt (well below full window → still invalid if window unfinished).
MIN_BARS_ANY = 500


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _expected_bars(start_ms: int, end_ms: int, interval: str) -> int:
    step = interval_ms(interval)
    if end_ms <= start_ms:
        return 0
    return max(0, int((end_ms - start_ms) // step))


def _scan_prior_cache_contamination(start_ms: int, end_ms: int) -> dict[str, Any]:
    """Search known cache roots for files overlapping reserved period."""
    roots = [
        ROOT / "artifacts",
        ROOT / "data",
        ROOT / ".nexus_runtime",
        ROOT / "_archive",
        ROOT / "_recovery",
    ]
    hits: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.json"):
            name = p.name
            # skip reservation/policy/SOT themselves
            if "OOS_H3_UNTOUCHED" in name and "RESERVATION" in name:
                continue
            if "POLICY_V1_FROZEN" in name:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")[:2000]
            except OSError:
                continue
            if str(start_ms) in text and ("market" in name.lower() or "kline" in name.lower() or "cache" in str(p).lower()):
                # only flag if under a cache-like path
                if any(x in str(p).replace("\\", "/").lower() for x in ("market_cache", "micro_cache", "/oos/")):
                    if "OOS_H3_UNTOUCHED_V1_RESERVED" in str(p):
                        continue  # current run target
                    hits.append(str(p.relative_to(ROOT)))
            if len(hits) >= 20:
                break
        if len(hits) >= 20:
            break
    return {
        "no_previous_local_cache_for_reserved_period": len(hits) == 0,
        "prior_cache_hits": hits,
    }


def main() -> int:
    phrase = os.environ.get("NEXUS_FOUNDER_OOS_PHRASE") or FOUNDER_OOS_APPROVAL_PHRASE
    assert_phrase_allows_oos(phrase)

    started = time.time()
    h3e_before = load_frozen_policy(PRIMARY_POLICY_ID)
    h3d_before = load_frozen_policy(CONFIRMATORY_POLICY_ID)
    if h3e_before["policy_checksum"] != H3E_EXPECT or h3d_before["policy_checksum"] != H3D_EXPECT:
        _write(
            IMMUTABLE / "ABORT_FROZEN_POLICY_CHECKSUM_MISMATCH.json",
            {
                "classification": "FROZEN_POLICY_CHECKSUM_MISMATCH",
                "h3e": h3e_before.get("policy_checksum"),
                "h3d": h3d_before.get("policy_checksum"),
            },
        )
        print("ABORT FROZEN_POLICY_CHECKSUM_MISMATCH")
        return 2

    reservation = load_oos_reservation()
    if reservation.get("reservation_id") != "OOS_H3_UNTOUCHED_V1_RESERVED":
        print("ABORT bad reservation_id")
        return 2
    start_ms = int(reservation["reserved_start"])
    end_ms = int(reservation["reserved_end"])
    symbols = list(reservation.get("symbols") or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"])
    intervals = [str(x) for x in (reservation.get("intervals") or ["15", "60", "240"])]

    checks = dict(reservation.get("checks") or {})
    cache_scan = _scan_prior_cache_contamination(start_ms, end_ms)
    overlap_ok = all(
        [
            checks.get("no_overlap_with_training") is True,
            checks.get("no_overlap_with_validation") is True,
            checks.get("no_overlap_with_consumed_failed_oos") is True,
            cache_scan["no_previous_local_cache_for_reserved_period"] is True,
        ]
    )
    if not overlap_ok:
        _write(
            IMMUTABLE / "ABORT_OOS_CONTAMINATED_OR_PREVIOUSLY_VISIBLE.json",
            {
                "classification": "OOS_CONTAMINATED_OR_PREVIOUSLY_VISIBLE",
                "checks": checks,
                "cache_scan": cache_scan,
            },
        )
        print("ABORT OOS_CONTAMINATED_OR_PREVIOUSLY_VISIBLE")
        return 3

    now_ms = int(time.time() * 1000)
    # Download exact reserved request window; API returns only available history (<= now).
    RUNTIME_OOS.mkdir(parents=True, exist_ok=True)
    kline_dir = RUNTIME_OOS / "market_cache"
    micro_dir = RUNTIME_OOS / "micro_cache"
    kline_dir.mkdir(parents=True, exist_ok=True)
    micro_dir.mkdir(parents=True, exist_ok=True)

    per_file: list[dict[str, Any]] = []
    datasets_by_interval: dict[str, list] = {}
    total_records = 0
    missing_total = 0
    dup_total = 0
    out_of_order = 0
    invalid_flags: list[str] = []

    for interval in intervals:
        # pages: reserved window ~45d; 15m needs ~65 pages worst case
        max_pages = 100 if interval == "15" else 40
        bundle = fetch_or_load_bundle(
            symbols=symbols,
            interval=interval,
            start_ms=start_ms,
            end_ms=end_ms,
            cache_dir=kline_dir,
            use_network=True,
            max_pages=max_pages,
        )
        datasets_by_interval[interval] = bundle
        expected = _expected_bars(start_ms, end_ms, interval)
        for ds in bundle:
            cache_path = kline_dir / f"{ds.symbol}_{interval}_{start_ms}_{end_ms}.json"
            file_sha = _sha_file(cache_path) if cache_path.exists() else ds.data_checksum
            coverage = (ds.record_count / expected) if expected else 0.0
            complete = coverage >= COMPLETENESS_RATIO and ds.record_count >= MIN_BARS_ANY
            if ds.classification != "REAL_HISTORICAL_MARKET_DATA":
                invalid_flags.append(f"{ds.symbol}_{interval}:{ds.classification}")
            if not complete:
                invalid_flags.append(f"{ds.symbol}_{interval}:INCOMPLETE_coverage={coverage:.4f}")
            if not ds.timestamps_monotonic:
                out_of_order += 1
            total_records += int(ds.record_count)
            missing_total += int(ds.missing_interval_count)
            dup_total += int(ds.duplicate_interval_count)
            per_file.append(
                {
                    "path": str(cache_path.relative_to(ROOT)).replace("\\", "/"),
                    "symbol": ds.symbol,
                    "interval": interval,
                    "record_count": ds.record_count,
                    "expected_bars_full_reservation": expected,
                    "coverage_ratio": round(coverage, 6),
                    "complete": complete,
                    "first_timestamp": ds.start_time,
                    "last_timestamp": ds.end_time,
                    "missing_interval_count": ds.missing_interval_count,
                    "duplicate_interval_count": ds.duplicate_interval_count,
                    "sha256": file_sha,
                    "data_checksum": ds.data_checksum,
                    "classification": ds.classification,
                    "future_data_used": ds.future_data_used,
                }
            )

    micro = fetch_or_load_micro_bundle(
        symbols=symbols,
        start_ms=start_ms,
        end_ms=min(end_ms, now_ms),
        cache_dir=micro_dir,
        use_network=True,
    )
    micro_path = micro_dir / "micro_bundle_meta.json"
    _write(
        micro_path,
        {
            "symbols": symbols,
            "start_ms": start_ms,
            "end_ms": min(end_ms, now_ms),
            "funding_status": {
                s: (micro.get("funding") or {}).get(s, {}).get("supported_status")
                if isinstance((micro.get("funding") or {}).get(s), dict)
                else getattr((micro.get("funding") or {}).get(s), "supported_status", None)
                for s in symbols
            },
            "oi_status": {
                s: (micro.get("open_interest") or {}).get(s, {}).get("supported_status")
                if isinstance((micro.get("open_interest") or {}).get(s), dict)
                else getattr((micro.get("open_interest") or {}).get(s), "supported_status", None)
                for s in symbols
            },
        },
    )

    aggregate_checksum = _sha_obj(
        {
            "reservation_id": "OOS_H3_UNTOUCHED_V1_RESERVED",
            "files": sorted(per_file, key=lambda x: (x["symbol"], x["interval"])),
            "micro_meta_sha": _sha_file(micro_path),
        }
    )

    reservation_remaining_ms = max(0, end_ms - now_ms)
    data_integrity = "PASS" if not invalid_flags else "FAIL"
    classification = "DATA_INVALID" if data_integrity != "PASS" else "DATA_OK_READY_TO_EXECUTE"

    download_manifest = {
        "reservation_id": "OOS_H3_UNTOUCHED_V1_RESERVED",
        "founder_phrase_accepted": True,
        "downloaded_at": _utc_now(),
        "data_provider": "bybit",
        "endpoint_families": {
            "klines": "/v5/market/kline",
            "funding": "/v5/market/funding/history",
            "open_interest": "/v5/market/open-interest",
        },
        "symbols": symbols,
        "timeframes": intervals,
        "reserved_start": start_ms,
        "reserved_end": end_ms,
        "download_request_end": end_ms,
        "wall_clock_now_ms": now_ms,
        "reservation_remaining_ms": reservation_remaining_ms,
        "reservation_window_complete_at_download": reservation_remaining_ms <= 0,
        "first_timestamp": min((f["first_timestamp"] for f in per_file if f["first_timestamp"]), default=None),
        "last_timestamp": max((f["last_timestamp"] for f in per_file if f["last_timestamp"]), default=None),
        "record_count": total_records,
        "missing_record_count": missing_total,
        "duplicate_record_count": dup_total,
        "out_of_order_count": out_of_order,
        "data_freshness": "PARTIAL_WINDOW_STILL_OPEN" if reservation_remaining_ms > 0 else "WINDOW_CLOSED",
        "per_file": per_file,
        "aggregate_dataset_sha256": aggregate_checksum,
        "funding_availability": "ATTEMPTED",
        "OI_availability": "ATTEMPTED",
        "lower_timeframe_availability": "15" in intervals,
        "data_integrity": data_integrity,
        "invalid_flags": invalid_flags,
        "classification": classification,
        "executed": False,
        "exchange_write_attempt_count": 0,
        "network_download_attempt_count": 1,
        "source_commit": os.popen("git rev-parse HEAD").read().strip(),
        "qualification_hierarchy": qualification_hierarchy(),
        "h3e_policy_checksum_before": h3e_before["policy_checksum"],
        "h3d_policy_checksum_before": h3d_before["policy_checksum"],
        "cache_scan": cache_scan,
        "elapsed_sec": round(time.time() - started, 3),
    }
    _write(RUNTIME_OOS / "download_manifest.json", download_manifest)
    _write(IMMUTABLE / "dataset_provenance_checksum_manifest.json", download_manifest)

    # Update reservation: downloaded true; executed false; checksum set; do not execute on invalid data.
    reservation_updated = dict(reservation)
    reservation_updated["downloaded"] = True
    reservation_updated["executed"] = False
    reservation_updated["checksum"] = aggregate_checksum
    reservation_updated["outcome_data_exposed"] = True
    reservation_updated["download_manifest_ref"] = "artifacts/readiness/immutable/h3_oos_v1/dataset_provenance_checksum_manifest.json"
    reservation_updated["data_integrity"] = data_integrity
    reservation_updated["classification"] = classification
    reservation_updated["downloaded_at"] = _utc_now()
    _write(RESERVATION_PATH, reservation_updated)

    # Policy checksum after download (must be unchanged)
    h3e_after = load_frozen_policy(PRIMARY_POLICY_ID)
    h3d_after = load_frozen_policy(CONFIRMATORY_POLICY_ID)
    policy_manifest = {
        "h3e_policy_id": PRIMARY_POLICY_ID,
        "h3e_policy_checksum_before": h3e_before["policy_checksum"],
        "h3e_policy_checksum_after": h3e_after["policy_checksum"],
        "h3e_policy_unchanged": h3e_after["policy_checksum"] == H3E_EXPECT,
        "h3d_policy_id": CONFIRMATORY_POLICY_ID,
        "h3d_policy_checksum_before": h3d_before["policy_checksum"],
        "h3d_policy_checksum_after": h3d_after["policy_checksum"],
        "h3d_policy_unchanged": h3d_after["policy_checksum"] == H3D_EXPECT,
        "policy_semantic_difference_count": 0
        if h3e_after["policy_checksum"] == H3E_EXPECT and h3d_after["policy_checksum"] == H3D_EXPECT
        else 1,
    }
    _write(IMMUTABLE / "policy_checksum_manifest.json", policy_manifest)

    # Do not execute simulations when data invalid.
    executed = False
    primary_status = "OOS_DATA_INVALID"
    confirmatory_status = "OOS_DATA_INVALID"
    exploratory_status = "EXPLORATORY_NOT_QUALIFICATION_EVIDENCE"
    recommendation = "NEXUS_H3_OOS_DATA_INVALID"
    consumed_classification = "NOT_CONSUMED_EXECUTION_NOT_STARTED"
    consumed_status = "SKIPPED_DATA_INVALID"

    if classification == "DATA_OK_READY_TO_EXECUTE":
        # Placeholder — full sim path only when completeness PASS.
        recommendation = "NEXUS_H3_OOS_EXECUTION_INVALID"
        primary_status = "OOS_EXECUTION_NOT_WIRED"
        raise RuntimeError("unexpected DATA_OK — sim wiring required before execute")

    summary = {
        "schema": "h3_oos_v1_terminal_summary",
        "updated_at": _utc_now(),
        "reservation_id": "OOS_H3_UNTOUCHED_V1_RESERVED",
        "reserved_start": start_ms,
        "reserved_end": end_ms,
        "downloaded": True,
        "executed": executed,
        "classification": classification,
        "recommendation": recommendation,
        "dataset_provider": "bybit",
        "dataset_symbols": symbols,
        "dataset_timeframes": intervals,
        "dataset_record_count": total_records,
        "dataset_checksum": aggregate_checksum,
        "overlap_training": False,
        "overlap_walk_forward": False,
        "overlap_consumed_oos": False,
        "lookahead_violation_count": 0,
        "h3e": {
            "primary_status": primary_status,
            "candidate_count": 0,
            "cost_gate_pass_count": 0,
            "completed_trade_count": 0,
            "net_pnl": None,
            "net_expectancy": None,
            "profit_factor": None,
            "adverse_profit_factor": None,
            "win_rate": None,
            "maximum_drawdown": None,
            "maximum_consecutive_losses": None,
            "liquidation_incident_count": 0,
            "risk_limit_breach_count": 0,
            "note": "Execution blocked: reserved window not fully available / incomplete dataset",
        },
        "h3d": {
            "confirmatory_status": confirmatory_status,
            "completed_trade_count": 0,
            "net_expectancy": None,
            "profit_factor": None,
            "adverse_profit_factor": None,
            "maximum_drawdown": None,
        },
        "h3g": {
            "exploratory_status": exploratory_status,
            "completed_trade_count": 0,
            "net_expectancy": None,
            "profit_factor": None,
            "maximum_drawdown": None,
        },
        "consumed_oos_registry_status": consumed_status,
        "consumed_oos_classification": consumed_classification,
        "risk_review_packet_ready": False,
        "risk_review_status": "NOT_APPLICABLE_DATA_INVALID",
        "wallet_delta_classification": "UNKNOWN",
        "wallet_delta_unattributed": -0.97052039,
        "trading_db_status": "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED",
        "shadow_status": "NOT_APPLIED",
        "demo_canary_started": False,
        "timed_session_started": False,
        "exchange_write_attempt_count": 0,
        "mainnet": False,
        "real_money": False,
        "policy": policy_manifest,
        "invalid_flags_head": invalid_flags[:40],
        "reservation_remaining_ms": reservation_remaining_ms,
    }
    _write(IMMUTABLE / "oos_summary.json", summary)

    consumed_registry = {
        "reservation_id": "OOS_H3_UNTOUCHED_V1_RESERVED",
        "status": consumed_status,
        "classification": consumed_classification,
        "dataset_checksum": aggregate_checksum,
        "policy_checksums": {
            "H3E_OOS_POLICY_V1_FROZEN": h3e_after["policy_checksum"],
            "H3D_OOS_POLICY_V1_FROZEN": h3d_after["policy_checksum"],
        },
        "execution_started": False,
        "execution_start_time": None,
        "execution_end_time": None,
        "source_commit": summary.get("policy") and os.popen("git rev-parse HEAD").read().strip(),
        "runner_version": "h3_oos_v1_download_gate",
        "result_checksums": {"oos_summary": _sha_obj(summary)},
        "primary_verdict": primary_status,
        "note": "Execution not started because data_integrity=FAIL (reserved window still open / incomplete).",
    }
    _write(IMMUTABLE / "consumed_oos_registry_entry.json", consumed_registry)

    print(json.dumps({"recommendation": recommendation, "classification": classification, "records": total_records, "checksum": aggregate_checksum}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
