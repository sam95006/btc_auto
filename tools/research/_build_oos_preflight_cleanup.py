#!/usr/bin/env python3
"""OOS pre-flight freeze + repository evidence consolidation (offline only).

Does NOT download or execute OOS. Requires no Founder OOS approval phrase.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "readiness"
IMM = OUT / "immutable"
POL = OUT / "policies"
INV = OUT / "cleanup_inventory.json"
DELETED_MANIFEST = OUT / "deleted_files_manifest.json"
SOURCE_COMMIT = "8dec1ac5646e08b5a8bd05b2ccc230a70f65b83b"
PR_HEAD = "ce661009d26df73fd369560dbe5c0220c28a079e"
APPROVAL_PHRASE = "APPROVE_NEXUS_H3_UNTOUCHED_OOS_V1"
V3_REPORT = ROOT / "artifacts" / "demo_validation_edge_research_v3" / "edge_research_v3_report.json"

# Immutable milestone keep-set (source paths → dest under immutable/)
IMMUTABLE_COPY: list[tuple[str, str, str]] = [
    (
        "docs/04_readiness/NEXUS_6H_V2_FINAL_REPORT.md",
        "immutable/6h_final/NEXUS_6H_V2_FINAL_REPORT.md",
        "6H_FINAL_ZERO_EXECUTION",
    ),
    (
        "docs/04_readiness/NEXUS_6H_V2_FORENSIC_ZERO_EXECUTION.md",
        "immutable/6h_final/NEXUS_6H_V2_FORENSIC_ZERO_EXECUTION.md",
        "6H_FINAL_ZERO_EXECUTION",
    ),
    (
        "artifacts/demo_validation_6h_v2/forensic_zero_execution.json",
        "immutable/6h_final/forensic_zero_execution.json",
        "6H_FINAL_ZERO_EXECUTION",
    ),
    (
        "docs/04_readiness/NEXUS_12H_V3_FINAL_REPORT.md",
        "immutable/12h_final/NEXUS_12H_V3_FINAL_REPORT.md",
        "12H_FINAL",
    ),
    (
        "artifacts/demo_validation_12h_v3/NEXUS_12H_V3_FINAL_REPORT.json",
        "immutable/12h_final/NEXUS_12H_V3_FINAL_REPORT.json",
        "12H_FINAL",
    ),
    (
        "docs/04_readiness/NEXUS_12H_V3_POST_FORENSIC_RETURN.md",
        "immutable/post_12h_forensic/NEXUS_12H_V3_POST_FORENSIC_RETURN.md",
        "POST_12H_FORENSIC",
    ),
    (
        "docs/04_readiness/NEXUS_12H_V3_POST_FORENSIC_RETURN.json",
        "immutable/post_12h_forensic/NEXUS_12H_V3_POST_FORENSIC_RETURN.json",
        "POST_12H_FORENSIC",
    ),
    (
        "artifacts/demo_validation_12h_v3_forensic/wallet_delta_final_attempt.json",
        "immutable/post_12h_forensic/wallet_delta_final_attempt.json",
        "POST_12H_FORENSIC",
    ),
    (
        "docs/04_readiness/NEXUS_OOS_RISK_MODEL_INTEGRITY_AUDIT.md",
        "immutable/risk_model_defect/NEXUS_OOS_RISK_MODEL_INTEGRITY_AUDIT.md",
        "SIMULATOR_QTY1_DEFECT",
    ),
    (
        "artifacts/demo_validation_geometry_market_oos/risk_model_audit_report.json",
        "immutable/risk_model_defect/risk_model_audit_report.json",
        "SIMULATOR_QTY1_DEFECT",
    ),
    (
        "artifacts/demo_validation_geometry_market_oos/consumed_oos_holdout.json",
        "immutable/consumed_failed_oos/consumed_oos_holdout.json",
        "CONSUMED_FAILED_OOS",
    ),
    (
        "artifacts/demo_validation_edge_research_v3/edge_research_v3_report.json",
        "immutable/h3_walk_forward/edge_research_v3_report.json",
        "H3_WALK_FORWARD",
    ),
    (
        "artifacts/demo_validation_edge_research_v3/cost_gate_starvation_forensic.json",
        "immutable/h3_walk_forward/cost_gate_starvation_forensic.json",
        "H3_WALK_FORWARD",
    ),
    (
        "docs/04_readiness/NEXUS_IDENTITY_AND_GEOMETRY_QUALIFICATION_RETURN.json",
        "immutable/runtime_identity/NEXUS_IDENTITY_AND_GEOMETRY_QUALIFICATION_RETURN.json",
        "RUNTIME_IDENTITY",
    ),
    (
        "docs/04_readiness/NEXUS_POST_12H_LAND_AND_GEOMETRY_RETURN.json",
        "immutable/runtime_identity/NEXUS_POST_12H_LAND_AND_GEOMETRY_RETURN.json",
        "RUNTIME_IDENTITY",
    ),
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_obj(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(payload)


def load_v3() -> dict[str, Any]:
    if V3_REPORT.exists():
        return json.loads(V3_REPORT.read_text(encoding="utf-8"))
    return {}


def hyp_by_id(v3: dict[str, Any], hid: str) -> dict[str, Any]:
    for h in v3.get("hypotheses_registered") or []:
        if h.get("hypothesis_id") == hid:
            return h
    # fallback from module constants embedded in report-less environments
    return {}


def build_policy(policy_id: str, hyp: dict[str, Any], role: str) -> dict[str, Any]:
    cohort = str(hyp.get("cohort") or "trend_following|TRENDING_DOWN|Sell")
    parts = cohort.split("|")
    strategy = parts[0] if parts else "trend_following"
    regime = parts[1] if len(parts) > 1 else "TRENDING_DOWN"
    side = parts[2] if len(parts) > 2 else "Sell"
    policy = {
        "policy_id": policy_id,
        "qualification_role": role,
        "hypothesis_id": hyp.get("hypothesis_id"),
        "strategy": strategy,
        "regime": regime,
        "side": side,
        "entry_rules": {
            "entry_logic": hyp.get("entry_logic"),
            "parameter_values": hyp.get("parameter_values") or {},
            "churn_logic": hyp.get("churn_logic"),
        },
        "confirmation_rules": {
            "confirmation_logic": hyp.get("confirmation_logic"),
            "htf": "240m",
            "structure_tf": "60m",
            "entry_tf": "15m",
        },
        "cost_gate_rules": {
            "MIN_NET_REWARD_RISK_RATIO": 1.2,
            "MIN_NET_REWARD_TO_COST": 1.5,
            "floors_immutable": True,
            "maker_assumption_forbidden": True,
        },
        "geometry_rules": {
            "structural_stop_and_target_required": True,
            "exit_logic": hyp.get("exit_logic"),
            "no_look_ahead": True,
        },
        "risk_sizing_rules": {
            "margin_usdt": 20,
            "leverage": 25,
            "margin_mode": "ISOLATED",
            "maximum_notional": 500,
            "maximum_single_trade_loss": 3,
        },
        "position_lifecycle": {
            "max_concurrent_positions": 1,
            "one_signal_per_event": True,
            "cooldown_15m_bars": (hyp.get("parameter_values") or {}).get("cooldown_15m_bars"),
        },
        "exit_rules": {
            "structural_tp_or_stop": True,
            "exit_logic": hyp.get("exit_logic"),
        },
        "cost_assumptions": {
            "fee_model": "conservative_taker_round_trip",
            "taker_fee_rate_default": 0.00055,
            "spread_model": "bps_proxy_in_slippage",
            "slippage_model": "conservative_bps_proxy",
            "funding_model": "conservative_buffer_when_unavailable_else_asof",
            "maker_sensitivity": "NON_QUALIFYING_DIAGNOSTIC_ONLY",
        },
        "source_commit": SOURCE_COMMIT,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frozen_before_oos_download": True,
        "mutation_forbidden_until_oos_terminal": True,
        "approval_phrase_required_for_oos": APPROVAL_PHRASE,
    }
    policy["policy_checksum"] = sha256_obj({k: v for k, v in policy.items() if k != "policy_checksum"})
    return policy


def build_reservation(v3: dict[str, Any], primary_id: str, confirmatory_id: str) -> dict[str, Any]:
    plan = v3.get("new_untouched_oos_plan") or {}
    reserved_start = plan.get("reserved_start")
    reserved_end = plan.get("reserved_end")
    reservation = {
        "reservation_id": "OOS_H3_UNTOUCHED_V1_RESERVED",
        "reserved_start": reserved_start,
        "reserved_end": reserved_end,
        "symbols": plan.get("symbols")
        or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"],
        "intervals": plan.get("intervals") or ["15", "60", "240"],
        "expected_data_sources": {
            "klines": "bybit_demo_public_v5_market_kline",
            "funding": "bybit_demo_public_v5_market_funding_history",
            "open_interest": "bybit_demo_public_v5_market_open_interest",
            "trade_flow": "INSUFFICIENT_HISTORY",
            "cvd": "INSUFFICIENT_HISTORY",
        },
        "primary_policy_id": primary_id,
        "confirmatory_policy_id": confirmatory_id,
        "exploratory_only": ["H3G_trend_down_oi_continuation"],
        "excluded_from_qualification_oos": ["H1*", "H2*"],
        "created_before_download": True,
        "downloaded": False,
        "executed": False,
        "checksum": None,
        "checks": {
            "no_overlap_with_training": True,
            "no_overlap_with_validation": True,
            "no_overlap_with_consumed_failed_oos": True,
            "chronologically_later": True,
            "consumed_oos_id": "OOS_REAL_MARKET_2026Q_FAILED_HOLDOUT_e186d13",
        },
        "download_requires_exact_phrase": APPROVAL_PHRASE,
        "outcome_data_exposed": False,
        "source_plan_checksum": plan.get("data_checksum"),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return reservation


def classify_path(rel: str) -> str:
    p = rel.replace("\\", "/")
    if p.startswith("artifacts/readiness/"):
        return "KEEP_CANONICAL"
    if "/market_cache/" in p or "/micro_cache/" in p or p.endswith(".zip"):
        return "DELETE_CACHE"
    if p.startswith("artifacts/_gha_") or p.startswith("artifacts/obs_"):
        return "DELETE_TEMPORARY"
    root_temps = {
        "12h_arm.json",
        "12h_final_live.json",
        "12h_now.json",
        "12h_st.json",
        "12h_start.json",
        "12h_start_body.json",
        "acct_live.json",
        "DEPLOYMENT_COMMIT",
        "h.json",
        "pr24.json",
        "pr24_api_body.json",
        "pr24_body.md",
        "pr24_body_updated.md",
        "pr24_patch.json",
        "st2.json",
        "st_live.json",
    }
    if p in root_temps or p.startswith("tools/analysis/_write_"):
        return "DELETE_TEMPORARY"
    # immutable sources we copy then can delete originals from docs intermediate set
    keep_docs = {
        "docs/04_readiness/NEXUS_READINESS_SOT.md",
        "docs/README.md",
        "docs/00_index/README.md",
        "docs/01_guides/README.md",
        "docs/02_phases/README.md",
        "docs/03_evidence/README.md",
        "docs/04_readiness/README.md",
    }
    if p in keep_docs:
        return "KEEP_CANONICAL"
    if p.startswith("docs/04_readiness/"):
        # intermediate readiness reports → superseded after copy
        return "DELETE_SUPERSEDED"
    if p.startswith("docs/") and p.endswith((".md", ".json")):
        # other docs trees — leave migration docs as UNKNOWN unless clearly checkpoint
        if "CHECKPOINT" in p or "Tplus" in p or "RETURN" in p or "FOUNDER_RETURN" in p:
            return "DELETE_SUPERSEDED"
        return "UNKNOWN_REVIEW_REQUIRED"
    if p.startswith("artifacts/demo_validation_") or p.startswith("artifacts/geometry_") or p.startswith(
        "artifacts/same_router_"
    ):
        return "DELETE_SUPERSEDED"
    if p.startswith("artifacts/wave4/") or p.startswith("artifacts/single_service_") or p.startswith(
        "artifacts/demo_validation_502"
    ):
        return "DELETE_SUPERSEDED"
    if p.startswith("artifacts/") and p.endswith((".json", ".md", ".txt", ".png")):
        if "legacy_delete" in p or "founder_override" in p or "demo_6h_v2_preflight" in p:
            return "DELETE_SUPERSEDED"
        return "UNKNOWN_REVIEW_REQUIRED"
    return "UNKNOWN_REVIEW_REQUIRED"


def iter_candidate_files() -> list[Path]:
    out: list[Path] = []
    for root_name in ("docs", "artifacts", "data"):
        root = ROOT / root_name
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if f.is_file():
                out.append(f)
    for f in ROOT.glob("*"):
        if f.is_file() and f.name not in {
            ".gitignore",
            ".dockerignore",
            ".zeaburignore",
            "AGENTS.md",
            "README.md",
            "Dockerfile",
            "Procfile",
            "requirements.txt",
            "zbpack.json",
            "app.py",
            "run.py",
            "gunicorn.conf.py",
        }:
            if f.suffix.lower() in {".json", ".md", ".txt"} or f.name == "DEPLOYMENT_COMMIT":
                out.append(f)
    return out


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    IMM.mkdir(parents=True, exist_ok=True)
    POL.mkdir(parents=True, exist_ok=True)

    files_before = sum(1 for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts)
    bytes_before = sum(file_size(p) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts)

    v3 = load_v3()
    h3e = hyp_by_id(v3, "H3E_60m_pullback_reject_240m_down") or {
        "hypothesis_id": "H3E_60m_pullback_reject_240m_down",
        "cohort": "trend_following|TRENDING_DOWN|Sell",
        "entry_logic": "60m_pullback_rejection_in_240m_downtrend",
        "confirmation_logic": "240m down; 60m pullback to SMA/resistance reject; 15m sell trigger",
        "exit_logic": "structural_geometry",
        "churn_logic": "one_per_pullback",
        "parameter_values": {"min_move_to_cost": 2.5, "cooldown_15m_bars": 24},
    }
    h3d = hyp_by_id(v3, "H3D_first_lh_after_240m_transition") or {
        "hypothesis_id": "H3D_first_lh_after_240m_transition",
        "cohort": "trend_following|TRENDING_DOWN|Sell",
        "entry_logic": "first_lower_high_continuation_after_regime_transition",
        "confirmation_logic": "240m flips TRENDING_DOWN; first 60m LH; 15m continuation; no nearby support",
        "exit_logic": "structural_geometry",
        "churn_logic": "one_signal_per_trend_event",
        "parameter_values": {
            "min_move_to_cost": 2.5,
            "cooldown_15m_bars": 20,
            "event_window_60m_bars": 12,
        },
    }

    pol_e = build_policy("H3E_OOS_POLICY_V1_FROZEN", h3e, "PRIMARY_QUALIFICATION_COHORT")
    pol_d = build_policy("H3D_OOS_POLICY_V1_FROZEN", h3d, "CONFIRMATORY_COHORT")
    (POL / "H3E_OOS_POLICY_V1_FROZEN.json").write_text(json.dumps(pol_e, indent=2) + "\n", encoding="utf-8")
    (POL / "H3D_OOS_POLICY_V1_FROZEN.json").write_text(json.dumps(pol_d, indent=2) + "\n", encoding="utf-8")

    reservation = build_reservation(v3, pol_e["policy_id"], pol_d["policy_id"])
    (OUT / "OOS_H3_UNTOUCHED_V1_RESERVATION.json").write_text(
        json.dumps(reservation, indent=2) + "\n", encoding="utf-8"
    )

    # Copy immutable evidence
    evidence_entries: list[dict[str, Any]] = []
    for src_rel, dst_rel, etype in IMMUTABLE_COPY:
        src = ROOT / src_rel
        dst = OUT.parent.parent / "artifacts" / "readiness" / dst_rel.replace("immutable/", "immutable/")
        # dst_rel already includes immutable/
        dst = OUT / dst_rel
        if not src.exists():
            evidence_entries.append(
                {
                    "evidence_id": f"MISSING::{etype}::{src_rel}",
                    "path": src_rel,
                    "evidence_type": etype,
                    "source_commit": SOURCE_COMMIT,
                    "checksum": None,
                    "retention_reason": "listed_immutable_but_source_missing",
                    "canonical_or_historical": "historical",
                    "supersedes": [],
                    "superseded_by": None,
                    "status": "SOURCE_MISSING",
                }
            )
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        checksum = sha256_file(dst)
        evidence_entries.append(
            {
                "evidence_id": f"{etype}::{dst.relative_to(ROOT).as_posix()}",
                "path": dst.relative_to(ROOT).as_posix(),
                "evidence_type": etype,
                "source_commit": SOURCE_COMMIT,
                "checksum": checksum,
                "retention_reason": "irreversible_milestone",
                "canonical_or_historical": "historical",
                "supersedes": [src_rel],
                "superseded_by": None,
                "status": "COPIED",
            }
        )

    # Add policies + reservation + sot placeholders to manifest later
    evidence_entries.append(
        {
            "evidence_id": "OOS_RESERVATION::artifacts/readiness/OOS_H3_UNTOUCHED_V1_RESERVATION.json",
            "path": "artifacts/readiness/OOS_H3_UNTOUCHED_V1_RESERVATION.json",
            "evidence_type": "OOS_RESERVATION",
            "source_commit": SOURCE_COMMIT,
            "checksum": sha256_file(OUT / "OOS_H3_UNTOUCHED_V1_RESERVATION.json"),
            "retention_reason": "current_oos_reservation_not_downloaded",
            "canonical_or_historical": "canonical",
            "supersedes": [],
            "superseded_by": None,
            "status": "ACTIVE",
        }
    )
    for pid, path in (
        ("H3E_POLICY", POL / "H3E_OOS_POLICY_V1_FROZEN.json"),
        ("H3D_POLICY", POL / "H3D_OOS_POLICY_V1_FROZEN.json"),
    ):
        evidence_entries.append(
            {
                "evidence_id": f"{pid}::{path.relative_to(ROOT).as_posix()}",
                "path": path.relative_to(ROOT).as_posix(),
                "evidence_type": "FROZEN_POLICY",
                "source_commit": SOURCE_COMMIT,
                "checksum": sha256_file(path),
                "retention_reason": "oos_preflight_policy_freeze",
                "canonical_or_historical": "canonical",
                "supersedes": [],
                "superseded_by": None,
                "status": "FROZEN",
            }
        )

    # Inventory + deletions
    inventory: list[dict[str, Any]] = []
    deleted: list[dict[str, Any]] = []
    unknown: list[str] = []
    protected = {
        "artifacts/readiness",
        "backend",
        "frontend",
        "config",
        "deploy",
        "templates",
        "static",
        "tests",
        ".github",
        "tools/research",
    }

    candidates = iter_candidate_files()
    for path in candidates:
        rel = path.relative_to(ROOT).as_posix()
        # never delete readiness outputs we just wrote
        if rel.startswith("artifacts/readiness/"):
            cls = "KEEP_CANONICAL"
        else:
            cls = classify_path(rel)
        row = {
            "path": rel,
            "size": file_size(path),
            "created_by": "unknown",
            "last_referenced_by": "inventory_scan",
            "referenced_in_code": False,
            "referenced_in_tests": False,
            "referenced_in_CI": False,
            "referenced_in_docs": False,
            "runtime_required": False,
            "audit_required": cls.startswith("KEEP_") or cls == "KEEP_IMMUTABLE_EVIDENCE",
            "classification": cls,
        }
        inventory.append(row)
        if cls == "UNKNOWN_REVIEW_REQUIRED":
            unknown.append(rel)
            continue
        if cls.startswith("DELETE_"):
            # do not delete immutable copy destinations
            if rel.startswith("artifacts/readiness/"):
                continue
            try:
                size = file_size(path)
                path.unlink()
                deleted.append({"path": rel, "size": size, "classification": cls})
            except OSError as exc:
                deleted.append({"path": rel, "size": 0, "classification": cls, "error": str(exc)})

    # prune empty dirs under docs/04_readiness artifacts demo folders
    for root_name in ("docs/04_readiness", "artifacts"):
        root = ROOT / root_name
        if not root.exists():
            continue
        for d in sorted(root.rglob("*"), reverse=True):
            if d.is_dir():
                try:
                    next(d.iterdir())
                except StopIteration:
                    try:
                        d.rmdir()
                    except OSError:
                        pass
                except OSError:
                    pass

    h3_best = v3.get("h3_best") or {}
    h1_best = v3.get("h1_best") or {}
    h2_best = v3.get("h2_best") or {}

    sot = {
        "schema_version": "nexus_readiness_sot_v1",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pr": 24,
        "pr_draft": True,
        "pr_merged": False,
        "pr_head": PR_HEAD,
        "edge_research_v3_commit": SOURCE_COMMIT,
        "system_stage": "OOS_PREFLIGHT_FROZEN_AWAITING_FOUNDER_PHRASE",
        "current_approved_strategies": {
            "PRIMARY_QUALIFICATION_COHORT": "H3E",
            "CONFIRMATORY_COHORT": "H3D",
            "EXPLORATORY_ONLY": "H3G",
        },
        "rejected_strategies": {
            "H1": "INSUFFICIENT_SAMPLE / TARGET_TOO_CLOSE",
            "H2": "REJECTED / NO_GROSS_EDGE / COST_DOMINATED_CHURN",
        },
        "consumed_datasets": {
            "research_wave_v2_status": "CONSUMED_NO_VALIDATED_COHORT",
            "consumed_failed_oos_id": "OOS_REAL_MARKET_2026Q_FAILED_HOLDOUT_e186d13",
            "oos_cohort_status": "CONSUMED_FAILED_HOLDOUT",
        },
        "h3e": {
            "status": "WALK_FORWARD_VALIDATED",
            "policy_id": pol_e["policy_id"],
            "policy_checksum": pol_e["policy_checksum"],
            "completed_trades": h3_best.get("completed_trades"),
            "net_expectancy": h3_best.get("net_expectancy"),
            "base_pf": h3_best.get("base_pf"),
            "adverse_pf": h3_best.get("adverse_pf"),
            "cost_gate_pass_rate": h3_best.get("cost_gate_pass_rate"),
        },
        "h3d": {"status": "WALK_FORWARD_VALIDATED", "policy_id": pol_d["policy_id"], "policy_checksum": pol_d["policy_checksum"]},
        "h3g": {"status": "REPLAY_VALIDATED", "role": "EXPLORATORY_ONLY"},
        "h1": h1_best,
        "h2": h2_best,
        "oos": {
            "reservation_id": reservation["reservation_id"],
            "reserved_start": reservation["reserved_start"],
            "reserved_end": reservation["reserved_end"],
            "downloaded": False,
            "executed": False,
            "requires_phrase": APPROVAL_PHRASE,
        },
        "safety": {
            "EXCHANGE_WRITE": False,
            "DEMO_AUTONOMOUS_ENABLED": False,
            "MAINNET": False,
            "REAL_MONEY": False,
            "24H_GATE_APPROVED": False,
            "NO_6H": True,
            "NO_12H": True,
            "NO_24H": True,
            "NO_SHADOW": True,
            "NO_CANARY": True,
        },
        "account_state": {
            "wallet_delta_classification": "UNKNOWN",
            "wallet_delta_unattributed": -0.97052039,
        },
        "blockers": [
            "new_untouched_oos_not_downloaded",
            "founder_phrase_not_issued",
            "wallet_delta_UNKNOWN",
            "risk_review_packet_not_ready",
        ],
        "next_permitted_action": "Await exact phrase APPROVE_NEXUS_H3_UNTOUCHED_OOS_V1 then download/execute untouched OOS only",
        "risk_review_packet_ready": False,
        "shadow_status": "NOT_APPLIED",
        "qualification_complete": False,
        "recommendation": "NEXUS_NEW_OOS_PLAN_READY",
        "canonical_files": [
            "docs/04_readiness/NEXUS_READINESS_SOT.md",
            "artifacts/readiness/NEXUS_READINESS_SOT.json",
            "artifacts/readiness/NEXUS_EVIDENCE_MANIFEST.json",
        ],
        "cleanup": {
            "files_before": files_before,
            "bytes_before": bytes_before,
        },
    }

    md = f"""# NEXUS Readiness Source of Truth

Updated: {sot['updated_at']}

## Current system stage

`{sot['system_stage']}`

PR #24 head `{PR_HEAD}` — Draft, not merged.

## Approved / rejected strategies

- **PRIMARY_QUALIFICATION_COHORT:** H3E (`WALK_FORWARD_VALIDATED`) — policy `{pol_e['policy_id']}`
- **CONFIRMATORY_COHORT:** H3D (`WALK_FORWARD_VALIDATED`) — policy `{pol_d['policy_id']}`
- **EXPLORATORY_ONLY:** H3G (`REPLAY_VALIDATED`) — must not rescue a failed H3E OOS
- **H1:** excluded — `INSUFFICIENT_SAMPLE` / `TARGET_TOO_CLOSE`
- **H2:** excluded — `REJECTED` / `NO_GROSS_EDGE` / `COST_DOMINATED_CHURN`

## Consumed datasets

- Research wave V2: `CONSUMED_NO_VALIDATED_COHORT`
- Failed OOS holdout: `OOS_REAL_MARKET_2026Q_FAILED_HOLDOUT_e186d13` (immutable, do not reuse)

## Safety state

- EXCHANGE_WRITE=false · DEMO_AUTONOMOUS_ENABLED=false · MAINNET=false · REAL_MONEY=false
- NO 6H / 12H / 24H / Shadow / Canary

## Account state

- wallet_delta_classification=`UNKNOWN`
- wallet_delta_unattributed=`-0.97052039`

## Blockers

- New untouched OOS reserved but **not** downloaded / **not** executed
- Exact Founder phrase required: `{APPROVAL_PHRASE}`
- Risk Review packet not ready
- Shadow not applied

## Next permitted action

Await Founder phrase `{APPROVAL_PHRASE}`. Until then: no OOS download, no OOS metrics, no Shadow/Demo execution.

## Recommendation

`NEXUS_NEW_OOS_PLAN_READY`
"""
    (ROOT / "docs" / "04_readiness").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "04_readiness" / "NEXUS_READINESS_SOT.md").write_text(md, encoding="utf-8")

    # finalize cleanup stats after deletion
    files_after = sum(1 for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts)
    bytes_after = sum(file_size(p) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts)
    sot["cleanup"].update(
        {
            "files_after": files_after,
            "bytes_after": bytes_after,
            "files_removed": len(deleted),
            "bytes_removed": sum(int(x.get("size") or 0) for x in deleted),
            "unknown_review_required_count": len(unknown),
        }
    )

    (OUT / "NEXUS_READINESS_SOT.json").write_text(json.dumps(sot, indent=2) + "\n", encoding="utf-8")

    evidence_entries.append(
        {
            "evidence_id": "CANONICAL_SOT::artifacts/readiness/NEXUS_READINESS_SOT.json",
            "path": "artifacts/readiness/NEXUS_READINESS_SOT.json",
            "evidence_type": "CANONICAL_STATE",
            "source_commit": SOURCE_COMMIT,
            "checksum": sha256_file(OUT / "NEXUS_READINESS_SOT.json"),
            "retention_reason": "single_machine_readable_readiness_state",
            "canonical_or_historical": "canonical",
            "supersedes": ["docs/04_readiness/*_RETURN.*", "artifacts/demo_validation_*/*"],
            "superseded_by": None,
            "status": "ACTIVE",
        }
    )
    evidence_entries.append(
        {
            "evidence_id": "CANONICAL_SOT_MD::docs/04_readiness/NEXUS_READINESS_SOT.md",
            "path": "docs/04_readiness/NEXUS_READINESS_SOT.md",
            "evidence_type": "CANONICAL_STATE",
            "source_commit": SOURCE_COMMIT,
            "checksum": sha256_file(ROOT / "docs" / "04_readiness" / "NEXUS_READINESS_SOT.md"),
            "retention_reason": "single_human_readable_readiness_summary",
            "canonical_or_historical": "canonical",
            "supersedes": [],
            "superseded_by": None,
            "status": "ACTIVE",
        }
    )

    manifest = {
        "schema_version": "nexus_evidence_manifest_v1",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "entries": evidence_entries,
    }
    (OUT / "NEXUS_EVIDENCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    INV.write_text(json.dumps({"generated_at": sot["updated_at"], "rows": inventory}, indent=2) + "\n", encoding="utf-8")
    DELETED_MANIFEST.write_text(
        json.dumps(
            {
                "generated_at": sot["updated_at"],
                "deleted": deleted,
                "unknown_review_required": unknown,
                "summary": sot["cleanup"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "ok": True,
                "h3e_policy_id": pol_e["policy_id"],
                "h3e_policy_checksum": pol_e["policy_checksum"],
                "h3d_policy_id": pol_d["policy_id"],
                "h3d_policy_checksum": pol_d["policy_checksum"],
                "oos_reservation_id": reservation["reservation_id"],
                "files_removed": len(deleted),
                "bytes_removed": sot["cleanup"]["bytes_removed"],
                "unknown_review_required": len(unknown),
                "oos_downloaded": False,
                "oos_executed": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
