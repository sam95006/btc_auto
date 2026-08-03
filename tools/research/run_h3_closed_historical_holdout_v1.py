#!/usr/bin/env python3
"""Execute H3 Closed Historical Holdout V1 — real Bybit public history + Demo capital snapshot.

Does NOT: use September OOS, mutate H3E/H3D, place Demo orders, Shadow, canary, deploy.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.closed_historical_holdout import (
    H3D_ID,
    H3E_ID,
    classify_confirmatory,
    classify_primary,
    evaluate_hypothesis_holdout,
    recommendation_from_primary,
)
from backend.nexus_demo_execution.closed_historical_registry import (
    SEPTEMBER_OOS_END_MS,
    SEPTEMBER_OOS_START_MS,
    assert_september_partial_excluded,
    overlaps_any,
    select_closed_historical_period,
)
from backend.nexus_demo_execution.h3_oos_policy_freeze import load_frozen_policy
from backend.nexus_demo_execution.historical_market_data import fetch_or_load_bundle, interval_ms
from backend.nexus_demo_execution.microstructure_history import fetch_or_load_micro_bundle

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / "artifacts" / "readiness"
IMMUTABLE = READINESS / "immutable" / "h3_closed_historical_v1"
RUNTIME = ROOT / ".nexus_runtime" / "oos" / "H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVED"
RESERVATION_PATH = READINESS / "H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVATION.json"

H3E_EXPECT = "bca97fa35cc8c49642901de409cc67cb7760c2ac83dd42a82cbab20999e2ba33"
H3D_EXPECT = "d415675df562e2ddad6cbfbbf77f6207ac2c1c48eebec27d153dc2aff31bb8a7"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
INTERVALS = ["15", "60", "240"]
COMPLETENESS = 0.999
RESERVATION_ID = "H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _expected_bars(start_ms: int, end_ms: int, interval: str) -> int:
    step = interval_ms(interval)
    return max(0, int((end_ms - start_ms) // step))


def _git_head() -> str:
    try:
        import subprocess

        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(ROOT)).strip()
    except Exception:
        return "UNKNOWN"


def _runner_checksum() -> str:
    return _sha_file(Path(__file__))


def fetch_demo_capital_snapshot() -> dict[str, Any]:
    """Read-only Demo capital reference. Never places orders."""
    exchange_write_attempt_count = 0
    try:
        from tools.research.bybit_demo_client import BybitDemoClient

        client = BybitDemoClient(mode="live")
        key = ""
        try:
            key = client._api_key()  # noqa: SLF001 — presence check only
        except Exception:
            key = ""
        if not key:
            raise RuntimeError("NO_DEMO_CREDENTIALS")
        snap = client.get_account_balance()
        exchange_write_attempt_count = 0
        blob = {
            "capital_source": "BYBIT_DEMO_ACCOUNT_SNAPSHOT",
            "live_api": True,
            "account_fingerprint": hashlib.sha256(
                json.dumps(
                    {
                        "wallet": snap.get("wallet_balance"),
                        "equity": snap.get("total_equity"),
                        "ts": snap.get("ts"),
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()[:16],
            "account_epoch": None,
            "wallet_balance": snap.get("wallet_balance"),
            "equity": snap.get("total_equity"),
            "available_balance": snap.get("available_balance"),
            "used_margin": snap.get("used_margin"),
            "unrealized_pnl": snap.get("unrealized_pnl"),
            "snapshot_timestamp": snap.get("ts") or _utc_now(),
            "exchange_write_attempt_count": exchange_write_attempt_count,
        }
        blob["snapshot_checksum"] = _sha_obj(blob)
        return blob
    except Exception as exc:
        # Sealed last-known Demo equity — capital reference only; not a wallet mutation.
        sealed = READINESS / "immutable" / "12h_final" / "NEXUS_12H_V3_FINAL_REPORT.json"
        eq = 5023.27777241
        avail = 5028.60306306
        wallet = 5023.27777241
        fp = "sealed12h"
        ts = _utc_now()
        if sealed.is_file():
            rep = json.loads(sealed.read_text(encoding="utf-8"))
            wallet = float(rep.get("wallet_balance") or wallet)
            eq = float(rep.get("equity") or eq)
            avail = float(rep.get("available_balance") or avail)
            fp = str(rep.get("account_fingerprint_status") or fp)
            ts = str(rep.get("updated_at") or rep.get("session_id") or ts)
        blob = {
            "capital_source": "BYBIT_DEMO_ACCOUNT_SNAPSHOT",
            "live_api": False,
            "live_api_error": type(exc).__name__,
            "capital_reference_note": "LIVE_DEMO_API_UNAVAILABLE_USING_SEALED_12H_EQUITY_READONLY",
            "account_fingerprint": fp,
            "account_epoch": None,
            "wallet_balance": wallet,
            "equity": eq,
            "available_balance": avail,
            "used_margin": 0.0,
            "unrealized_pnl": 0.0,
            "snapshot_timestamp": ts,
            "exchange_write_attempt_count": 0,
            "sealed_source": "artifacts/readiness/immutable/12h_final/NEXUS_12H_V3_FINAL_REPORT.json",
        }
        blob["snapshot_checksum"] = _sha_obj(blob)
        return blob


def _overlap_flags(start_ms: int, end_ms: int, used: list[dict[str, Any]]) -> dict[str, bool]:
    from backend.nexus_demo_execution.closed_historical_registry import UsedInterval

    intervals = [
        UsedInterval(
            source=u["source"],
            label=u["label"],
            start_ms=int(u["start_ms"]),
            end_ms=int(u["end_ms"]),
            category=u["category"],
        )
        for u in used
    ]
    hits = overlaps_any(intervals, start_ms, end_ms)

    def any_cat(*cats: str) -> bool:
        return any(h.category in cats for h in hits)

    return {
        "overlap_training": any_cat("training_replay_walk_forward_research", "prior_research_cache", "filename_stamp", "readiness_manifest_interval"),
        "overlap_replay": any_cat("training_replay_walk_forward_research"),
        "overlap_walk_forward": any_cat("training_replay_walk_forward_research"),
        "overlap_prior_research": any_cat("training_replay_walk_forward_research", "prior_research_cache", "filename_stamp"),
        "overlap_prior_oos": any_cat("prior_consumed_oos", "prior_oos_cache"),
        "overlap_september_oos": any_cat("september_untouched_oos")
        or any(h.start_ms == SEPTEMBER_OOS_START_MS for h in hits),
        "prior_strategy_visibility": False,
        "hit_labels": [h.label for h in hits],
    }


def build_demo_forward_packet(*, capital: dict[str, Any], primary_status: str) -> dict[str, Any]:
    return {
        "packet_id": "H3_BYBIT_DEMO_FORWARD_V1",
        "demo_forward_packet_ready": True,
        "demo_forward_status": "AWAITING_SEPARATE_FOUNDER_AUTHORIZATION",
        "primary_status_required": "CLOSED_HISTORICAL_PERFORMANCE_VALIDATED",
        "primary_status_observed": primary_status,
        "live_public_bybit_market_feed": "REQUIRED",
        "actual_bybit_demo_private_api": "REQUIRED",
        "isolated_25x_enforcement": True,
        "position_margin_usdt": 20,
        "maximum_loss_risk_per_trade_usdt": 3,
        "max_open_positions": 1,
        "max_active_intents": 1,
        "mandatory_sl_tp_confirmation": True,
        "reconciliation_before_after_every_order": True,
        "persistent_outcome_and_reflection": True,
        "demo_order_history_retention_limitation": "ACKNOWLEDGED",
        "session_kill_switch": True,
        "stale_data_veto": True,
        "duplicate_intent_veto": True,
        "cost_gate": True,
        "risk_critic_veto": True,
        "account_epoch": capital.get("account_epoch"),
        "account_fingerprint": capital.get("account_fingerprint"),
        "start_wallet_snapshot": {
            "wallet_balance": capital.get("wallet_balance"),
            "equity": capital.get("equity"),
            "available_balance": capital.get("available_balance"),
            "snapshot_checksum": capital.get("snapshot_checksum"),
        },
        "exchange_write_authorization_gate": "REQUIRES_SEPARATE_FOUNDER_AUTHORIZATION",
        "wallet_residual_blocker": {
            "wallet_delta_classification": "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST",
            "remaining_unattributed_delta": -0.97052039,
            "resolution_required_before_writes": True,
        },
        "auto_start_forbidden": True,
        "created_at": _utc_now(),
    }


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    assert_september_partial_excluded("safe")

    IMMUTABLE.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)

    h3e_before = load_frozen_policy("H3E_OOS_POLICY_V1_FROZEN")
    h3d_before = load_frozen_policy("H3D_OOS_POLICY_V1_FROZEN")
    if h3e_before["policy_checksum"] != H3E_EXPECT or h3d_before["policy_checksum"] != H3D_EXPECT:
        _write(
            IMMUTABLE / "ABORT_POLICY_CHECKSUM.json",
            {"h3e": h3e_before.get("policy_checksum"), "h3d": h3d_before.get("policy_checksum")},
        )
        print("ABORT FROZEN_POLICY_CHECKSUM_MISMATCH")
        return 2

    selection = select_closed_historical_period(root=ROOT, reservation_id=RESERVATION_ID)
    if selection.status != "PERIOD_SELECTED":
        summary = {
            "recommendation": "NEXUS_NO_CLEAN_HISTORICAL_HOLDOUT_AVAILABLE",
            "status": selection.status,
            "interval_registry_checksum": selection.interval_registry_checksum,
            "selection": selection.to_dict(),
            "september_oos_status": "OOS_WINDOW_NOT_MATURE",
            "september_oos_consumed": False,
            "exchange_write_attempt_count": 0,
            "demo_order_count": 0,
            "shadow_status": "NOT_APPLIED",
        }
        _write(IMMUTABLE / "closed_historical_summary.json", summary)
        _write(RESERVATION_PATH, selection.to_dict())
        print(json.dumps(summary, indent=2))
        return 0

    start_ms = selection.reservation_start
    end_ms = selection.reservation_end
    overlaps = _overlap_flags(start_ms, end_ms, selection.used_intervals)
    if any(
        overlaps[k]
        for k in (
            "overlap_training",
            "overlap_replay",
            "overlap_walk_forward",
            "overlap_prior_research",
            "overlap_prior_oos",
            "overlap_september_oos",
        )
    ):
        summary = {
            "recommendation": "NEXUS_NO_CLEAN_HISTORICAL_HOLDOUT_AVAILABLE",
            "status": "OVERLAP_DETECTED_AFTER_SELECTION",
            "overlaps": overlaps,
            "selection": selection.to_dict(),
        }
        _write(IMMUTABLE / "closed_historical_summary.json", summary)
        print(json.dumps(summary, indent=2))
        return 0

    reservation = {
        "reservation_id": RESERVATION_ID,
        "reservation_start": start_ms,
        "reservation_end": end_ms,
        "reservation_duration_days": selection.reservation_duration_days,
        "selection_rule": selection.selection_rule,
        "interval_registry_checksum": selection.interval_registry_checksum,
        "policy_checksums": {"H3E": H3E_EXPECT, "H3D": H3D_EXPECT},
        "source_commit": _git_head(),
        "symbols": SYMBOLS,
        "intervals": INTERVALS,
        "created_at": _utc_now(),
        "downloaded": False,
        "executed": False,
        "window_fully_closed": True,
        **{k: overlaps[k] for k in overlaps if k != "hit_labels"},
        "september_reservation_excluded": True,
        "partial_september_cache_excluded": True,
    }
    _write(RESERVATION_PATH, reservation)
    _write(IMMUTABLE / "interval_reservation_manifest.json", reservation)

    capital = fetch_demo_capital_snapshot()
    _write(IMMUTABLE / "demo_capital_snapshot.json", capital)

    # Download real Bybit public history into ignored runtime cache.
    kline_dir = RUNTIME / "market_cache"
    micro_dir = RUNTIME / "micro_cache"
    kline_dir.mkdir(parents=True, exist_ok=True)
    micro_dir.mkdir(parents=True, exist_ok=True)

    per_file: list[dict[str, Any]] = []
    invalid: list[str] = []
    total_records = 0
    missing_total = 0
    dup_total = 0
    out_of_order = 0
    coverage: dict[str, float] = {}
    datasets_by_iv: dict[str, list] = {}

    for interval in INTERVALS:
        max_pages = 120 if interval == "15" else 50
        bundle = fetch_or_load_bundle(
            symbols=SYMBOLS,
            interval=interval,
            start_ms=start_ms,
            end_ms=end_ms,
            cache_dir=kline_dir,
            use_network=True,
            max_pages=max_pages,
        )
        datasets_by_iv[interval] = bundle
        expected = _expected_bars(start_ms, end_ms, interval)
        for ds in bundle:
            assert_september_partial_excluded(str(kline_dir / f"{ds.symbol}_{interval}"))
            path = kline_dir / f"{ds.symbol}_{interval}_{start_ms}_{end_ms}.json"
            file_sha = _sha_file(path) if path.exists() else ds.data_checksum
            cov = (ds.record_count / expected) if expected else 0.0
            coverage[f"{ds.symbol}_{interval}"] = round(cov, 6)
            complete = cov >= COMPLETENESS
            if ds.classification != "REAL_HISTORICAL_MARKET_DATA":
                invalid.append(f"{ds.symbol}_{interval}:{ds.classification}")
            if not complete:
                invalid.append(f"{ds.symbol}_{interval}:INCOMPLETE:{cov:.4f}")
            if not ds.timestamps_monotonic:
                out_of_order += 1
            total_records += int(ds.record_count)
            missing_total += int(ds.missing_interval_count)
            dup_total += int(ds.duplicate_interval_count)
            per_file.append(
                {
                    "symbol": ds.symbol,
                    "interval": interval,
                    "record_count": ds.record_count,
                    "expected": expected,
                    "coverage_ratio": round(cov, 6),
                    "sha256": file_sha,
                    "data_checksum": ds.data_checksum,
                    "classification": ds.classification,
                    "first_timestamp": ds.start_time,
                    "last_timestamp": ds.end_time,
                    "missing_interval_count": ds.missing_interval_count,
                }
            )

    micro = fetch_or_load_micro_bundle(
        symbols=SYMBOLS, start_ms=start_ms, end_ms=end_ms, cache_dir=micro_dir, use_network=True
    )
    funding_cov = {
        s: getattr((micro.get("funding") or {}).get(s), "supported_status", None)
        if not isinstance((micro.get("funding") or {}).get(s), dict)
        else (micro.get("funding") or {}).get(s, {}).get("supported_status")
        for s in SYMBOLS
    }
    oi_cov = {
        s: getattr((micro.get("open_interest") or {}).get(s), "supported_status", None)
        if not isinstance((micro.get("open_interest") or {}).get(s), dict)
        else (micro.get("open_interest") or {}).get(s, {}).get("supported_status")
        for s in SYMBOLS
    }

    expected_total = sum(_expected_bars(start_ms, end_ms, iv) * len(SYMBOLS) for iv in INTERVALS)
    aggregate = _sha_obj({"reservation_id": RESERVATION_ID, "files": sorted(per_file, key=lambda x: (x["symbol"], x["interval"]))})
    integrity_pass = (
        not invalid
        and missing_total == 0
        and out_of_order == 0
        and all(v >= COMPLETENESS for v in coverage.values())
    )
    provenance = {
        "provider": "bybit",
        "symbols": SYMBOLS,
        "timeframes": INTERVALS,
        "start_timestamp": start_ms,
        "end_timestamp": end_ms,
        "expected_record_count": expected_total,
        "actual_record_count": total_records,
        "missing_record_count": missing_total,
        "duplicate_record_count": dup_total,
        "out_of_order_count": out_of_order,
        "coverage_ratio_by_symbol_timeframe": coverage,
        "funding_coverage": funding_cov,
        "oi_coverage": oi_cov,
        "mark_price_coverage": "TRADE_PRICE_CANDLES_USED_AS_PRIMARY",
        "instrument_metadata_coverage": "RUNTIME_DEFAULTS_FROM_FROZEN_POLICY",
        "per_file": per_file,
        "aggregate_dataset_SHA256": aggregate,
        "window_fully_closed": True,
        "dataset_integrity_status": "PASS" if integrity_pass else "FAIL",
        "invalid_flags": invalid[:50],
        **{k: overlaps[k] for k in overlaps if k != "hit_labels"},
        "synthetic_forbidden": True,
        "september_partial_excluded": True,
    }
    _write(IMMUTABLE / "dataset_provenance_checksum_manifest.json", provenance)
    reservation["downloaded"] = True
    reservation["checksum"] = aggregate
    reservation["data_integrity"] = provenance["dataset_integrity_status"]
    _write(RESERVATION_PATH, reservation)

    policy_manifest = {
        "h3e_policy_checksum_before": h3e_before["policy_checksum"],
        "h3d_policy_checksum_before": h3d_before["policy_checksum"],
        "h3e_policy_unchanged": True,
        "h3d_policy_unchanged": True,
        "policy_semantic_difference_count": 0,
    }
    _write(IMMUTABLE / "policy_checksum_manifest.json", policy_manifest)

    if not integrity_pass:
        summary = {
            "recommendation": "NEXUS_H3_CLOSED_HISTORICAL_DATA_INVALID",
            "primary_status": "CLOSED_HISTORICAL_DATA_INVALID",
            "confirmatory_status": "CONFIRMATORY_DATA_INVALID",
            "dataset_integrity_status": "FAIL",
            "dataset_checksum": aggregate,
            "dataset_record_count": total_records,
            "selection": selection.to_dict(),
            "overlaps": {k: overlaps[k] for k in overlaps if k != "hit_labels"},
            "capital": capital,
            "historical_execution_mode": "HISTORICAL_SIMULATION_ONLY",
            "exchange_write_attempt_count": 0,
            "demo_order_count": 0,
            "demo_wallet_changed_by_test": False,
            "september_oos_status": "OOS_WINDOW_NOT_MATURE",
            "september_oos_consumed": False,
            "wallet_delta_classification": "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST",
            "remaining_unattributed_delta": -0.97052039,
            "trading_db_status": "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED",
            "shadow_status": "NOT_APPLIED",
            "demo_canary_started": False,
            "policy": policy_manifest,
        }
        _write(IMMUTABLE / "closed_historical_summary.json", summary)
        print(json.dumps({"recommendation": summary["recommendation"], "records": total_records}, indent=2))
        return 0

    # Mark consumed at H3E execution start.
    exec_start = _utc_now()
    consumed = {
        "reservation_id": RESERVATION_ID,
        "reservation_start": start_ms,
        "reservation_end": end_ms,
        "dataset_checksum": aggregate,
        "interval_registry_checksum": selection.interval_registry_checksum,
        "h3e_policy_checksum": H3E_EXPECT,
        "h3d_policy_checksum": H3D_EXPECT,
        "source_commit": _git_head(),
        "runner_checksum": _runner_checksum(),
        "execution_start": exec_start,
        "execution_end": None,
        "primary_verdict": None,
        "status": "EXECUTING_H3E",
        "classification": "CONSUMED_IN_PROGRESS",
    }
    _write(IMMUTABLE / "consumed_holdout_registry_entry.json", consumed)

    print("H3E primary holdout...", flush=True)
    h3e = evaluate_hypothesis_holdout(
        hypothesis_id=H3E_ID,
        datasets_15=datasets_by_iv["15"],
        datasets_60=datasets_by_iv["60"],
        datasets_240=datasets_by_iv["240"],
        micro=micro,
    )
    primary_status = classify_primary(h3e, data_valid=True)
    # Seal H3E before H3D
    _write(IMMUTABLE / "h3e_result_sealed.json", {"primary_status": primary_status, "metrics": h3e, "sealed_at": _utc_now()})

    print("H3D confirmatory holdout...", flush=True)
    h3d = evaluate_hypothesis_holdout(
        hypothesis_id=H3D_ID,
        datasets_15=datasets_by_iv["15"],
        datasets_60=datasets_by_iv["60"],
        datasets_240=datasets_by_iv["240"],
        micro=micro,
    )
    confirmatory_status = classify_confirmatory(h3d, data_valid=True)
    # H3D cannot rescue H3E
    if primary_status != "CLOSED_HISTORICAL_PERFORMANCE_VALIDATED":
        assert confirmatory_status != "IGNORED"

    exec_end = _utc_now()
    if primary_status == "CLOSED_HISTORICAL_PERFORMANCE_FAILED":
        consumed_class = "CONSUMED_FAILED_CLOSED_HISTORICAL_HOLDOUT"
    elif primary_status == "CLOSED_HISTORICAL_INSUFFICIENT_SAMPLE":
        consumed_class = "CONSUMED_INSUFFICIENT_CLOSED_HISTORICAL_HOLDOUT"
    elif primary_status == "CLOSED_HISTORICAL_PERFORMANCE_VALIDATED":
        consumed_class = "CONSUMED_VALIDATED_CLOSED_HISTORICAL_HOLDOUT"
    else:
        consumed_class = "CONSUMED_DATA_INVALID_CLOSED_HISTORICAL_HOLDOUT"

    consumed.update(
        {
            "execution_end": exec_end,
            "primary_verdict": primary_status,
            "confirmatory_verdict": confirmatory_status,
            "status": "CONSUMED",
            "classification": consumed_class,
        }
    )
    _write(IMMUTABLE / "consumed_holdout_registry_entry.json", consumed)

    h3e_after = load_frozen_policy("H3E_OOS_POLICY_V1_FROZEN")
    h3d_after = load_frozen_policy("H3D_OOS_POLICY_V1_FROZEN")
    policy_manifest.update(
        {
            "h3e_policy_checksum_after": h3e_after["policy_checksum"],
            "h3d_policy_checksum_after": h3d_after["policy_checksum"],
            "h3e_policy_unchanged": h3e_after["policy_checksum"] == H3E_EXPECT,
            "h3d_policy_unchanged": h3d_after["policy_checksum"] == H3D_EXPECT,
            "policy_semantic_difference_count": 0
            if h3e_after["policy_checksum"] == H3E_EXPECT and h3d_after["policy_checksum"] == H3D_EXPECT
            else 1,
        }
    )
    _write(IMMUTABLE / "policy_checksum_manifest.json", policy_manifest)

    demo_forward_packet_ready = primary_status == "CLOSED_HISTORICAL_PERFORMANCE_VALIDATED"
    demo_forward_status = (
        "AWAITING_SEPARATE_FOUNDER_AUTHORIZATION" if demo_forward_packet_ready else "NOT_APPLICABLE_PRIMARY_NOT_VALIDATED"
    )
    if demo_forward_packet_ready:
        packet = build_demo_forward_packet(capital=capital, primary_status=primary_status)
        _write(IMMUTABLE / "demo_forward_readiness_packet.json", packet)

    reservation["executed"] = True
    reservation["primary_status"] = primary_status
    _write(RESERVATION_PATH, reservation)

    summary = {
        "schema": "h3_closed_historical_holdout_v1",
        "updated_at": _utc_now(),
        "reservation_id": RESERVATION_ID,
        "reservation_start": start_ms,
        "reservation_end": end_ms,
        "reservation_duration_days": selection.reservation_duration_days,
        "selection_rule": selection.selection_rule,
        "interval_registry_checksum": selection.interval_registry_checksum,
        "overlaps": {k: overlaps[k] for k in overlaps if k != "hit_labels"},
        "dataset_provider": "bybit",
        "dataset_symbols": SYMBOLS,
        "dataset_timeframes": INTERVALS,
        "dataset_record_count": total_records,
        "dataset_checksum": aggregate,
        "dataset_integrity_status": "PASS",
        "capital": capital,
        "historical_execution_mode": "HISTORICAL_SIMULATION_ONLY",
        "historical_simulated_ledger": {
            "starting_equity": capital.get("equity"),
            "note": "Simulated ledger only; actual Bybit Demo wallet untouched",
        },
        "actual_bybit_demo_wallet": {
            "unchanged_by_test": True,
            "exchange_write_attempt_count": 0,
        },
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "demo_wallet_changed_by_test": False,
        "h3e": {
            "primary_status": primary_status,
            **{k: h3e.get(k) for k in h3e},
        },
        "h3d": {
            "confirmatory_status": confirmatory_status,
            "completed_trade_count": h3d.get("completed_trade_count"),
            "net_expectancy": h3d.get("net_expectancy") or h3d.get("expectancy"),
            "profit_factor": h3d.get("profit_factor") or h3d.get("net_profit_factor"),
            "adverse_profit_factor": h3d.get("adverse_profit_factor"),
            "maximum_drawdown": h3d.get("maximum_drawdown"),
            "metrics": h3d,
        },
        "consumed_holdout_registry_status": "CONSUMED",
        "consumed_holdout_classification": consumed_class,
        "demo_forward_packet_ready": demo_forward_packet_ready,
        "demo_forward_status": demo_forward_status,
        "policy": policy_manifest,
        "september_oos_status": "OOS_WINDOW_NOT_MATURE",
        "september_oos_consumed": False,
        "wallet_delta_classification": "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST",
        "remaining_unattributed_delta": -0.97052039,
        "trading_db_status": "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED",
        "shadow_status": "NOT_APPLIED",
        "demo_canary_started": False,
        "timed_session_started": False,
        "mainnet": False,
        "real_money": False,
        "recommendation": recommendation_from_primary(primary_status),
    }
    _write(IMMUTABLE / "closed_historical_summary.json", summary)
    print(
        json.dumps(
            {
                "recommendation": summary["recommendation"],
                "primary_status": primary_status,
                "confirmatory_status": confirmatory_status,
                "h3e_trades": h3e.get("completed_trade_count"),
                "h3d_trades": h3d.get("completed_trade_count"),
                "records": total_records,
                "checksum": aggregate,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
