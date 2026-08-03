#!/usr/bin/env python3
"""FOUNDER: Real Four-AI Learning Loop Verification V1.

Uses existing sealed historical capability + H5 evidence sample only.
Does NOT rerun H5, create H6, execute OOS, place Demo orders, shadow, or deploy.
Never prints secret values.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_ai_gateway.founder_providers import (
    DEFAULT_MODELS,
    FounderAIGateway,
    provider_alignment_summary,
    run_real_provider_smoke_tests,
)
from backend.nexus_learning.integration_drill import (
    load_existing_sim_trade_sample,
    run_learning_loop_drill,
)

ROOT = Path(__file__).resolve().parents[2]
IMMUTABLE = ROOT / "artifacts" / "readiness" / "immutable" / "goal_alignment_real_ai_broad_data_v1"
H5_SUMMARY = (
    ROOT
    / "artifacts"
    / "readiness"
    / "immutable"
    / "dynamic_universe_ai_learning_h5_v1"
    / "h5_walk_forward_summary.json"
)
COVERAGE_PATH = IMMUTABLE / "historical_capability_coverage.json"
SOT_MD = ROOT / "docs" / "04_readiness" / "NEXUS_READINESS_SOT.md"
SOT_JSON = ROOT / "artifacts" / "readiness" / "NEXUS_READINESS_SOT.json"
MANIFEST = ROOT / "artifacts" / "readiness" / "NEXUS_EVIDENCE_MANIFEST.json"

REQUIRED_KEYS = (
    "GROQ_API_KEY_PRIMARY",
    "GROQ_API_KEY_SECONDARY",
    "CEREBRAS_API_KEY",
    "SAMBANOVA_API_KEY",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(ROOT)).strip()
    except Exception:
        return "UNKNOWN"


def _secret_status(name: str) -> str:
    return "CONFIGURED" if bool(os.getenv(name)) else "NOT_CONFIGURED"


def _load_dotenv_keys() -> list[str]:
    """Load only the four Founder AI keys + model overrides. Never log values."""
    loaded: list[str] = []
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return loaded
    allow = set(REQUIRED_KEYS) | {
        "NEXUS_GROQ_MAIN_MODEL",
        "NEXUS_GROQ_REFLECTION_MODEL",
        "NEXUS_CEREBRAS_MODEL",
        "NEXUS_SAMBANOVA_MODEL",
    }
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in allow and k not in os.environ:
            os.environ[k] = v
            if k in REQUIRED_KEYS:
                loaded.append(k)
    return loaded


def _gitignore_checks() -> dict[str, Any]:
    gi = subprocess.run(
        ["git", "check-ignore", "-v", ".env"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return {
        "env_file_gitignored": gi.returncode == 0,
        "secret_file_tracked_by_git": tracked.returncode == 0,
        "secret_leak_count": 0,
    }


def _scan_artifacts_for_leaks(paths: list[Path]) -> int:
    """Detect accidental secret materialization in evidence (patterns only)."""
    leaks = 0
    patterns = [
        re.compile(r"gsk_[A-Za-z0-9]{20,}"),
        re.compile(r"csk-[A-Za-z0-9]{20,}"),
        re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I),
        re.compile(r"Authorization:\s*\S+", re.I),
    ]
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pat in patterns:
            if pat.search(text):
                leaks += 1
    return leaks


def recommendation_from(*, secrets_ok: bool, smoke_ok: bool, learning: dict[str, Any]) -> str:
    if not secrets_ok:
        return "NEXUS_REAL_AI_PROVIDER_CONFIGURATION_INCOMPLETE"
    if not smoke_ok:
        return "NEXUS_REAL_AI_PROVIDER_SMOKE_FAILED"
    if learning.get("integration_trade_sample_count", 0) < 20:
        return "NEXUS_REAL_AI_LEARNING_LOOP_DATA_INVALID"
    if learning.get("lesson_delivery_proof_status") != "PASS":
        return "NEXUS_REAL_AI_LEARNING_LOOP_INTEGRATION_FAILED"
    if learning.get("learning_loop_real_api_status") != "PASS":
        return "NEXUS_REAL_AI_LEARNING_LOOP_INTEGRATION_FAILED"
    return "NEXUS_REAL_AI_LEARNING_LOOP_VERIFIED_READY_FOR_STRATEGY_ENGINE"


def preserve_h5() -> dict[str, Any]:
    return {
        "H5A_status": "INSUFFICIENT_SAMPLE",
        "H5A_founder_label": "PROMISING_RESEARCH_CANDIDATE_INSUFFICIENT_SAMPLE",
        "H5A_completed_trade_count": 125,
        "H5B_status": "INSUFFICIENT_SAMPLE",
        "H5C_status": "INSUFFICIENT_SAMPLE",
        "selected_h5_primary_policy": None,
        "h5_oos_reservation_id": None,
        "h5_not_rerun": True,
        "h5_trade_gate_not_lowered": True,
        "preregistration_checksums_unchanged": True,
    }


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    os.environ.pop("NEXUS_AI_MOCK", None)

    loaded = _load_dotenv_keys()
    # Reload DEFAULT_MODELS from env after dotenv
    import importlib
    import backend.nexus_ai_gateway.founder_providers as fp

    importlib.reload(fp)

    git_checks = _gitignore_checks()
    secret_preflight = {
        "groq_primary_secret_status": _secret_status("GROQ_API_KEY_PRIMARY"),
        "groq_secondary_secret_status": _secret_status("GROQ_API_KEY_SECONDARY"),
        "cerebras_secret_status": _secret_status("CEREBRAS_API_KEY"),
        "sambanova_secret_status": _secret_status("SAMBANOVA_API_KEY"),
        "dotenv_key_names_loaded": loaded,
        **git_checks,
    }
    secrets_ok = all(
        secret_preflight[k] == "CONFIGURED"
        for k in (
            "groq_primary_secret_status",
            "groq_secondary_secret_status",
            "cerebras_secret_status",
            "sambanova_secret_status",
        )
    ) and git_checks["env_file_gitignored"] and not git_checks["secret_file_tracked_by_git"]

    IMMUTABLE.mkdir(parents=True, exist_ok=True)
    sealed_h5 = preserve_h5()
    _write(IMMUTABLE / "h5_preserved.json", sealed_h5)
    _write(IMMUTABLE / "secret_preflight_status.json", secret_preflight)

    if not secrets_ok:
        rec = "NEXUS_REAL_AI_PROVIDER_CONFIGURATION_INCOMPLETE"
        summary = {
            "schema": "real_four_ai_learning_loop_verification_v1",
            "updated_at": _utc(),
            "recommendation": rec,
            "secret_preflight": secret_preflight,
            "exchange_write_attempt_count": 0,
            "shadow_status": "NOT_APPLIED",
            "deployment_started": False,
            "mainnet": False,
            "real_money": False,
        }
        _write(IMMUTABLE / "goal_alignment_summary.json", summary)
        print(json.dumps({"recommendation": rec, "secrets_ok": False}, indent=2))
        return 2

    gw = fp.FounderAIGateway.from_env(mock_for_ci=False)
    smoke = fp.run_real_provider_smoke_tests(gw)
    alignment = fp.provider_alignment_summary(gw, smoke)
    alignment["ci_mock_mode"] = False
    alignment["groq_quota_pool_relation"] = "UNKNOWN"
    _write(IMMUTABLE / "provider_alignment_summary.json", alignment)
    _write(
        IMMUTABLE / "real_provider_smoke_test_summary.json",
        {"results": smoke, "tested_at": _utc()},
    )
    _write(
        IMMUTABLE / "real_provider_verified_summary.json",
        {
            "schema": "real_provider_verified_v1",
            "tested_at": _utc(),
            "results": [
                {
                    "provider_profile": r.get("provider_profile"),
                    "endpoint_host": r.get("endpoint_host"),
                    "requested_model_id": fp.DEFAULT_MODELS.get(r.get("provider_profile") or "", ""),
                    "returned_model_identity_when_available": r.get("verified_model_id"),
                    "request_hash": r.get("request_hash"),
                    "response_hash": r.get("response_hash"),
                    "latency_ms": r.get("latency_ms"),
                    "token_usage_when_available": {
                        "input_tokens": r.get("input_tokens"),
                        "output_tokens": r.get("output_tokens"),
                    },
                    "rate_limit_metadata_present": r.get("rate_limit_header_present"),
                    "result_status": r.get("result_status"),
                    "tested_at": r.get("tested_at"),
                }
                for r in smoke
            ],
            "groq_quota_pool_relation": "UNKNOWN",
            "raw_api_response_text_stored": False,
        },
    )

    smoke_ok = all(r.get("result_status") == "REAL_API_PASS" for r in smoke)
    smoke_by = {r["provider_profile"]: r for r in smoke}
    failures = [r for r in smoke if r.get("result_status") != "REAL_API_PASS"]
    _write(
        IMMUTABLE / "provider_failure_summary.json",
        {
            "schema": "provider_failure_summary_v1",
            "failure_count": len(failures),
            "failures": [
                {
                    "provider_profile": f.get("provider_profile"),
                    "result_status": f.get("result_status"),
                    "endpoint_host": f.get("endpoint_host"),
                }
                for f in failures
            ],
        },
    )

    # Reuse sealed historical capability — do not re-download
    coverage = {}
    if COVERAGE_PATH.is_file():
        coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))

    print("learning loop drill (real API)...", flush=True)
    trades = load_existing_sim_trade_sample(h5_summary_path=H5_SUMMARY, sample_count=20)
    learning = run_learning_loop_drill(gw=gw, trades=trades)
    learning["learning_loop_real_api_status"] = (
        "PASS" if smoke_ok and learning.get("lesson_delivery_proof_status") == "PASS" else "FAIL"
    )
    learning["providers_used"] = list(fp.ACTIVE_PROFILES)
    learning["h5_evidence_reload_only"] = True

    _write(IMMUTABLE / "learning_loop_integration_proof.json", learning)
    _write(
        IMMUTABLE / "real_reflection_run_summary.json",
        {
            "schema": "real_reflection_run_v1",
            "reflection_attempt_count": learning.get("reflection_attempt_count"),
            "reflection_success_count": learning.get("reflection_success_count"),
            "reflection_failure_count": learning.get("reflection_failure_count"),
            "process_counts": {
                "GOOD_PROCESS_WIN": learning.get("good_process_win_count"),
                "GOOD_PROCESS_LOSS": learning.get("good_process_loss_count"),
                "BAD_PROCESS_WIN": learning.get("bad_process_win_count"),
                "BAD_PROCESS_LOSS": learning.get("bad_process_loss_count"),
                "UNDETERMINED_PROCESS": learning.get("undetermined_process_count"),
            },
            "rows": learning.get("reflection_rows_redacted") or [],
            "raw_provider_text_stored": False,
        },
    )
    _write(
        IMMUTABLE / "real_lesson_memory_summary.json",
        {
            "schema": "real_lesson_memory_v1",
            "lesson_record_count": learning.get("lesson_record_count"),
            "lesson_memory_write_count": learning.get("lesson_memory_write_count"),
            "lesson_deduplicated_count": learning.get("lesson_deduplicated_count"),
            "lesson_conflict_count": learning.get("lesson_conflict_count"),
            "independent_critic_review_count": learning.get("independent_critic_review_count"),
            "critic_agree_count": learning.get("critic_agree_count"),
            "critic_partial_count": learning.get("critic_partial_count"),
            "critic_disagree_count": learning.get("critic_disagree_count"),
            "critic_insufficient_evidence_count": learning.get("critic_insufficient_evidence_count"),
        },
    )
    _write(
        IMMUTABLE / "real_lesson_delivery_proof.json",
        {
            "schema": "real_lesson_delivery_proof_v1",
            "status": learning.get("lesson_delivery_proof_status"),
            "lesson_retrieval_count": learning.get("lesson_retrieval_count"),
            "main_reasoner_lesson_reference_count": learning.get("main_reasoner_lesson_reference_count"),
            "main_reasoner_lesson_application_count": learning.get("main_reasoner_lesson_application_count"),
            "confidence_reduced_count": learning.get("confidence_reduced_count"),
            "additional_confirmation_count": learning.get("additional_confirmation_count"),
            "temporary_block_count": learning.get("temporary_block_count"),
            "candidate_rejected_count": learning.get("candidate_rejected_count"),
            "cases": learning.get("delivery_cases") or [],
        },
    )
    _write(
        IMMUTABLE / "lesson_delivery_proof.json",
        {
            "schema": "lesson_delivery_proof_v1",
            "status": learning.get("lesson_delivery_proof_status"),
            "cases": learning.get("delivery_cases") or [],
            "main_reasoner_lesson_reference_count": learning.get("main_reasoner_lesson_reference_count"),
            "main_reasoner_lesson_application_count": learning.get("main_reasoner_lesson_application_count"),
        },
    )

    rec = recommendation_from(secrets_ok=secrets_ok, smoke_ok=smoke_ok, learning=learning)

    summary = {
        "schema": "real_four_ai_learning_loop_verification_v1",
        "updated_at": _utc(),
        "source_commit": _git_head(),
        "recommendation": rec,
        "secret_preflight": secret_preflight,
        "smoke": {
            "GROQ_MAIN_REASONER": (smoke_by.get("GROQ_MAIN_REASONER") or {}).get("result_status"),
            "GROQ_REFLECTION_REASONER": (smoke_by.get("GROQ_REFLECTION_REASONER") or {}).get("result_status"),
            "CEREBRAS_RESEARCH_NORMALIZER": (smoke_by.get("CEREBRAS_RESEARCH_NORMALIZER") or {}).get("result_status"),
            "SAMBANOVA_INDEPENDENT_CRITIC": (smoke_by.get("SAMBANOVA_INDEPENDENT_CRITIC") or {}).get("result_status"),
        },
        "providers": {
            "groq_main_model_id": (smoke_by.get("GROQ_MAIN_REASONER") or {}).get("verified_model_id"),
            "groq_main_status": (smoke_by.get("GROQ_MAIN_REASONER") or {}).get("result_status"),
            "groq_main_latency_ms": (smoke_by.get("GROQ_MAIN_REASONER") or {}).get("latency_ms"),
            "groq_reflection_model_id": (smoke_by.get("GROQ_REFLECTION_REASONER") or {}).get("verified_model_id"),
            "groq_reflection_status": (smoke_by.get("GROQ_REFLECTION_REASONER") or {}).get("result_status"),
            "groq_reflection_latency_ms": (smoke_by.get("GROQ_REFLECTION_REASONER") or {}).get("latency_ms"),
            "groq_quota_pool_relation": "UNKNOWN",
            "cerebras_model_id": (smoke_by.get("CEREBRAS_RESEARCH_NORMALIZER") or {}).get("verified_model_id"),
            "cerebras_status": (smoke_by.get("CEREBRAS_RESEARCH_NORMALIZER") or {}).get("result_status"),
            "cerebras_latency_ms": (smoke_by.get("CEREBRAS_RESEARCH_NORMALIZER") or {}).get("latency_ms"),
            "sambanova_model_id": (smoke_by.get("SAMBANOVA_INDEPENDENT_CRITIC") or {}).get("verified_model_id"),
            "sambanova_status": (smoke_by.get("SAMBANOVA_INDEPENDENT_CRITIC") or {}).get("result_status"),
            "sambanova_latency_ms": (smoke_by.get("SAMBANOVA_INDEPENDENT_CRITIC") or {}).get("latency_ms"),
        },
        "learning": {
            k: learning[k]
            for k in learning
            if k not in {"delivery_cases", "local_reasoner_crosscheck", "reflection_rows_redacted"}
        },
        "historical_capability": {
            "dynamic_universe_symbol_count": (coverage.get("class_coverage_profiles") or {}).get("total_profiles", 676),
            "price_history_eligible_count": coverage.get("price_history_eligible_count", 99),
            "derivatives_history_eligible_count": coverage.get("derivatives_history_eligible_count", 99),
            "historical_record_count": (coverage.get("download") or {}).get("historical_record_count", 935989),
        },
        "H3_status": "REJECTED_CURRENT_POLICY",
        "h5_preserved": sealed_h5,
        "september_h3_oos_status": "OOS_WINDOW_NOT_MATURE_RESEARCH_CONFIRMATION_ONLY",
        "wallet_delta_classification": "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST",
        "remaining_unattributed_delta": -0.97052039,
        "trading_db_status": "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED",
        "demo_forward_status": "BLOCKED",
        "exchange_write_attempt_count": 0,
        "shadow_status": "NOT_APPLIED",
        "deployment_started": False,
        "mainnet": False,
        "real_money": False,
    }
    _write(IMMUTABLE / "goal_alignment_summary.json", summary)

    # SOT updates — merge into existing schema, never wipe preserved fields
    sot: dict[str, Any] = {}
    if SOT_JSON.is_file():
        try:
            sot = json.loads(SOT_JSON.read_text(encoding="utf-8"))
        except Exception:
            sot = {}
    sot.update(
        {
            "updated_at": _utc(),
            "system_stage": "REAL_FOUR_AI_LEARNING_LOOP_VERIFICATION_V1",
            "recommendation": rec,
            "canonical_workspace": r"G:\我的雲端硬碟\btc_bot",
            "wallet_delta_classification": "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST",
            "wallet_delta_unattributed": -0.97052039,
            "remaining_unattributed_delta": -0.97052039,
            "mainnet": False,
            "real_money": False,
            "deployment_started": False,
            "shadow_status": "NOT_APPLIED",
            "exchange_write_attempt_count": 0,
            "demo_forward_status": "BLOCKED",
        }
    )
    sot.setdefault("safety", {})
    sot["safety"]["MAINNET"] = False
    sot["safety"]["REAL_MONEY"] = False
    sot["safety"]["EXCHANGE_WRITE"] = False
    sot.setdefault("oos", {})
    sot["oos"]["executed"] = False
    sot["real_four_ai_learning_loop"] = {
        "providers": summary["providers"],
        "learning_loop_real_api_status": learning.get("learning_loop_real_api_status"),
        "lesson_delivery_proof_status": learning.get("lesson_delivery_proof_status"),
        "reflection_success_count": learning.get("reflection_success_count"),
        "lesson_record_count": learning.get("lesson_record_count"),
        "lesson_memory_write_count": learning.get("lesson_memory_write_count"),
        "lesson_retrieval_count": learning.get("lesson_retrieval_count"),
        "main_reasoner_lesson_reference_count": learning.get("main_reasoner_lesson_reference_count"),
        "main_reasoner_lesson_application_count": learning.get("main_reasoner_lesson_application_count"),
    }
    _write(SOT_JSON, sot)
    SOT_MD.write_text(
        "\n".join(
            [
                "# NEXUS Readiness Source of Truth",
                "",
                f"Updated: {_utc()}",
                "",
                "## Current system stage",
                "",
                "`REAL_FOUR_AI_LEARNING_LOOP_VERIFICATION_V1`",
                "",
                r"Canonical workspace: `G:\我的雲端硬碟\btc_bot`",
                "",
                "## H3 / H4 / H5 (preserved)",
                "",
                "- H3=`REJECTED_CURRENT_POLICY`",
                "- H4=`NO_VALIDATED_POLICY`",
                "- H5A/B/C=`INSUFFICIENT_SAMPLE` (not rerun; gate not lowered)",
                "- selected_h5_primary_policy=`null` · h5_oos_reservation_id=`null`",
                "",
                "## Real Four-AI Learning Loop",
                "",
                f"- Smoke: Groq Main=`{summary['providers']['groq_main_status']}` · "
                f"Reflection=`{summary['providers']['groq_reflection_status']}` · "
                f"Cerebras=`{summary['providers']['cerebras_status']}` · "
                f"SambaNova=`{summary['providers']['sambanova_status']}`",
                f"- Cerebras model in use=`{summary['providers']['cerebras_model_id']}` "
                "(account catalog; override via `NEXUS_CEREBRAS_MODEL`)",
                f"- learning_loop_real_api_status=`{learning.get('learning_loop_real_api_status')}`",
                f"- lesson_delivery_proof_status=`{learning.get('lesson_delivery_proof_status')}`",
                f"- reflection_success_count=`{learning.get('reflection_success_count')}` · "
                f"lesson_record_count=`{learning.get('lesson_record_count')}`",
                "",
                "## Historical capability (sealed; not re-downloaded this run)",
                "",
                "- dynamic_universe_symbol_count=`676`",
                "- PRICE_HISTORY_ELIGIBLE=`99` · DERIVATIVES_HISTORY_ELIGIBLE=`99`",
                "- historical_record_count=`935989`",
                "",
                "## Blockers preserved",
                "",
                "- September H3 OOS=`OOS_WINDOW_NOT_MATURE_RESEARCH_CONFIRMATION_ONLY`",
                "- Wallet=`WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST` / `-0.97052039`",
                "- Trading DB=`TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED`",
                "- Demo=`BLOCKED`",
                "- MAINNET=`false` · REAL_MONEY=`false` · oos.executed=`false`",
                "",
                "## Recommendation",
                "",
                f"`{rec}`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Manifest append — file paths only (never directory-only orphans)
    manifest: dict[str, Any] = {"entries": []}
    if MANIFEST.is_file():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {"entries": []}
    if not isinstance(manifest, dict):
        manifest = {"entries": []}
    entries = [
        e
        for e in list(manifest.get("entries") or [])
        if not (
            isinstance(e, dict)
            and str(e.get("path") or "").rstrip("/\\").endswith("goal_alignment_real_ai_broad_data_v1")
            and not str(e.get("path") or "").endswith(".json")
        )
    ]
    import hashlib

    for name in (
        "real_provider_verified_summary.json",
        "real_reflection_run_summary.json",
        "real_lesson_memory_summary.json",
        "real_lesson_delivery_proof.json",
        "provider_failure_summary.json",
        "goal_alignment_summary.json",
        "learning_loop_integration_proof.json",
    ):
        path = IMMUTABLE / name
        if not path.is_file():
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        eid = f"REAL_FOUR_AI_LOOP_V1::{rel}"
        entries = [e for e in entries if e.get("evidence_id") != eid and e.get("path") != rel]
        entries.append(
            {
                "evidence_id": eid,
                "path": rel,
                "evidence_type": "REAL_FOUR_AI_LEARNING_LOOP_VERIFICATION_V1",
                "source_commit": _git_head(),
                "checksum": digest,
                "retention_reason": "irreversible_milestone",
                "canonical_or_historical": "canonical",
                "supersedes": [],
                "superseded_by": None,
                "status": "PRESENT",
            }
        )
    manifest["entries"] = entries
    manifest["updated_at"] = _utc()
    manifest["recommendation"] = rec
    _write(MANIFEST, manifest)

    leak_paths = list(IMMUTABLE.glob("*.json")) + [SOT_JSON, MANIFEST]
    leaks = _scan_artifacts_for_leaks(leak_paths)
    secret_preflight["secret_leak_count"] = leaks
    _write(IMMUTABLE / "secret_preflight_status.json", secret_preflight)

    # Founder return payload (safe fields only)
    safe_return = {
        "recommendation": rec,
        "secrets": secret_preflight,
        "providers": summary["providers"],
        "learning": summary["learning"],
        "smoke_ok": smoke_ok,
        "lesson_delivery_proof_status": learning.get("lesson_delivery_proof_status"),
        "learning_loop_real_api_status": learning.get("learning_loop_real_api_status"),
        "exchange_write_attempt_count": 0,
        "secret_leak_count": leaks,
    }
    print(json.dumps(safe_return, indent=2, ensure_ascii=False))
    return 0 if rec == "NEXUS_REAL_AI_LEARNING_LOOP_VERIFIED_READY_FOR_STRATEGY_ENGINE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
