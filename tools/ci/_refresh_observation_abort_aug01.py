"""Refresh abort export with Founder-directive GET reconfirm (Aug 1)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

started = datetime.fromisoformat("2026-07-31T05:11:30+00:00")
aborted = datetime.fromisoformat("2026-08-01T08:34:44+00:00")
hours = round((aborted - started).total_seconds() / 3600.0, 4)

cp = json.loads(
    Path(
        "artifacts/single_service_observation/checkpoint_ABORT_FINAL_RECONFIRM_20260801T083449Z.json"
    ).read_text(encoding="utf-8")
)
early_path = Path("artifacts/single_service_observation/checkpoint_TplusEARLY_20260731T055242Z.json")
early = json.loads(early_path.read_text(encoding="utf-8")) if early_path.exists() else {}
cand_delta = int(cp.get("candidate_count") or 0) - int(early.get("candidate_count") or 0)
fee = cp.get("fee_policy") or {}

md = f"""# NEXUS Single-Service Operational Observation — ABORTED

**Not a 24H PASS.** Founder prioritized bounded Demo execution validation.

| Field | Value |
|-------|-------|
| observation_status | `ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION` |
| operational_observation_status | `ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION` |
| operational_observation_pass | `false` |
| observation_completed_full_24h | `false` |
| reason | `FOUNDER_PRIORITIZED_BOUNDED_DEMO_EXECUTION_VALIDATION` |

**Forbidden claim:** `NEXUS_SINGLE_SERVICE_OPERATIONAL_24H_PASS` — **not** recorded.

## Founder Override

| Field | Value |
|-------|-------|
| founder_override_id | `FO-20260801-ABORT24H-DEMO6H12H` |
| founder_override_reason | `FOUNDER_PRIORITIZED_BOUNDED_DEMO_EXECUTION_VALIDATION` |
| approved_at | `2026-08-01T08:34:44Z` |
| first_abort_artifact_at | `2026-07-31T10:05:06Z` (`FO-20260731-ABORT24H-DEMO6H12H`) |
| approved_scope | abort incomplete 24H observation; Demo 6H V2; Demo 12H V3 **only via 6H machine gate** |
| FOUNDER_OVERRIDE_ABORT_OPERATIONAL_24H | `true` |
| FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2 | `true` |
| FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3 | `true` |
| source_observation_report | `docs/04_readiness/NEXUS_SINGLE_SERVICE_OPERATIONAL_OBSERVATION_ABORTED_REPORT.md` |
| override record | `artifacts/founder_override_record.json` |
| observation_aborted.json | `artifacts/single_service_observation/observation_aborted.json` |

Override **cannot**: enable mainnet, enable real money, disable risk controls, lower Net R:R (1.2), bypass 6H→12H machine gate, or auto-start 24H.

## Window (actual)

| Field | Value |
|-------|-------|
| observation_started_at | `2026-07-31T05:11:30Z` |
| observation_aborted_at | `2026-08-01T08:34:44Z` |
| planned_ends_at | `2026-08-01T05:11:30Z` |
| actual_duration_hours | **{hours}** |
| note | Wall clock exceeded planned end; formal T+6/12/18/24 checkpoints **missing** → ABORTED, not PASS |
| sole_url | https://nexus-bybit-demo-val.zeabur.app |
| deployment_commit_at_abort | `598a5e11985f613007c8d65e61fa1dd9c7cbdf67` |
| deploy_run_at_abort | `30605493505` |

## Checkpoints (honest — no fabrication)

| Checkpoint | Status |
|------------|--------|
| T+EARLY | completed (`2026-07-31T05:52:40Z`) |
| T+1H | completed (`2026-07-31T06:11:53Z`) |
| T+3H | completed (`2026-07-31T08:12:05Z`) |
| ABORT_FINAL | completed GET-only (`2026-07-31T10:05:06Z`) |
| ABORT_FINAL_RECONFIRM | completed GET-only (`2026-08-01T08:34:44Z`) |
| T+6H | **missing** |
| T+12H | **missing** |
| T+18H | **missing** |
| T+24H | **missing** |

completed_checkpoints=`T+EARLY,T+1H,T+3H,ABORT_FINAL,ABORT_FINAL_RECONFIRM`  
missing_checkpoints=`T+6H,T+12H,T+18H,T+24H`

## Abort RECONFIRM snapshot (GET-only, Founder directive)

| Metric | Value |
|--------|------:|
| runtime_health (HTTP) | {cp.get("health_status")} |
| market_worker_health | {cp.get("market_worker_health")} |
| position_supervisor_health | {cp.get("position_supervisor_health")} |
| persistence_health | {cp.get("persistence_health")} |
| geometry_complete | {cp.get("geometry_complete_count")} |
| geometry_missing | {cp.get("geometry_missing_count")} |
| candidate_count | {cp.get("candidate_count")} |
| candidate_delta (vs T+EARLY) | {cand_delta} |
| market_cycles_delta | not claimed |
| cost_gate_delta | not claimed |
| position_count_at_abort | **{cp.get("position_count")}** |
| open_order_count_at_abort | **{cp.get("open_order_count")}** |
| exchange_write_call_count_at_abort | **{cp.get("exchange_write_call_count")}** |
| hidden_dependency_count_at_abort | **{cp.get("hidden_dependency_count")}** |
| active_http_200_service_count | **{cp.get("active_http_200_service_count")}** |
| execution_owner_count | **{cp.get("execution_owner_count")}** |
| legacy_stage3_http_status | {cp.get("stage3_http_status")} (SUSPENDED) |
| legacy_control_plane_http_status | {cp.get("old_control_plane_http_status")} (SUSPENDED) |
| fee_rate_status | {fee.get("fee_rate_status")} |
| mainnet | false |
| real_money | false |
| exchange_write | false |

Soft flags at abort (not elevated to PASS): identity label mismatch vs SoT; component health UNKNOWN; geometry_complete=0 at reconfirm.

## Legacy services (this wave)

| Service | State |
|---------|-------|
| nexus-stage3-bybit-demo-learning | **SUSPENDED** (do not resume / do not delete this wave) |
| nexus-unified-control-plane | **SUSPENDED** (do not resume / do not delete this wave) |
| nexus-bybit-demo-learning-validation | **KEEP** — sole HTTP 200 / execution owner |

## Next (approved sequence)

1. Explicit Founder override gate in CI/workflows  
2. Deploy PR #24 package to **existing Validation only** (write OFF initially)  
3. T+0 / T+60 / T+180 health  
4. Preflight → start **6H V2**  
5. Finalize / flatten / reconcile / export  
6. Machine gate → **12H V3** only if 6H hard safety PASS  
7. Stop before 24H (`DEMO_AUTONOMOUS_24H_BOUNDED_VALIDATION` APPROVED=false)

## Recommendation at abort

`NEXUS_OPERATIONAL_24H_ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION` — proceed under explicit override; **not** an operational 24H PASS.
"""

report_md = Path("docs/04_readiness/NEXUS_SINGLE_SERVICE_OPERATIONAL_OBSERVATION_ABORTED_REPORT.md")
report_md.write_text(md, encoding="utf-8")
checksum = hashlib.sha256(md.encode("utf-8")).hexdigest()

payload = {
    "observation_status": "ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION",
    "operational_observation_pass": False,
    "observation_completed_full_24h": False,
    "operational_observation_status": "ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION",
    "reason": "FOUNDER_PRIORITIZED_BOUNDED_DEMO_EXECUTION_VALIDATION",
    "founder_override_id": "FO-20260801-ABORT24H-DEMO6H12H",
    "founder_override_reason": "FOUNDER_PRIORITIZED_BOUNDED_DEMO_EXECUTION_VALIDATION",
    "approved_at": "2026-08-01T08:34:44Z",
    "prior_abort_artifact_id": "FO-20260731-ABORT24H-DEMO6H12H",
    "approved_scope": [
        "abort_incomplete_operational_24h",
        "demo_autonomous_6h_v2",
        "demo_autonomous_12h_v3_via_machine_gate",
    ],
    "FOUNDER_OVERRIDE_ABORT_OPERATIONAL_24H": True,
    "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2": True,
    "FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3": True,
    "observation_started_at": "2026-07-31T05:11:30Z",
    "observation_aborted_at": "2026-08-01T08:34:44Z",
    "actual_duration_hours": hours,
    "completed_checkpoints": [
        "T+EARLY",
        "T+1H",
        "T+3H",
        "ABORT_FINAL",
        "ABORT_FINAL_RECONFIRM",
    ],
    "missing_checkpoints": ["T+6H", "T+12H", "T+18H", "T+24H"],
    "runtime_health": {
        "health_status": cp.get("health_status"),
        "market_worker_health": cp.get("market_worker_health"),
        "position_supervisor_health": cp.get("position_supervisor_health"),
        "persistence_health": cp.get("persistence_health"),
        "soft_flags": cp.get("soft_flags"),
    },
    "market_cycles_delta": None,
    "candidate_delta": cand_delta,
    "geometry_complete": cp.get("geometry_complete_count"),
    "geometry_missing": cp.get("geometry_missing_count"),
    "cost_gate_delta": None,
    "position_count_at_abort": cp.get("position_count"),
    "open_order_count_at_abort": cp.get("open_order_count"),
    "exchange_write_call_count_at_abort": cp.get("exchange_write_call_count"),
    "hidden_dependency_count_at_abort": cp.get("hidden_dependency_count"),
    "active_http_200_service_count": cp.get("active_http_200_service_count"),
    "execution_owner_count": cp.get("execution_owner_count"),
    "legacy_stage3_http_status": cp.get("stage3_http_status"),
    "legacy_control_plane_http_status": cp.get("old_control_plane_http_status"),
    "legacy_stage3": "SUSPENDED",
    "legacy_control_plane": "SUSPENDED",
    "deployment_commit_at_abort": "598a5e11985f613007c8d65e61fa1dd9c7cbdf67",
    "deploy_run_at_abort": "30605493505",
    "abort_checkpoint_path": (
        "artifacts/single_service_observation/"
        "checkpoint_ABORT_FINAL_RECONFIRM_20260801T083449Z.json"
    ),
    "prior_abort_checkpoint_path": (
        "artifacts/single_service_observation/checkpoint_ABORT_FINAL_20260731T100509Z.json"
    ),
    "must_not_claim": [
        "NEXUS_SINGLE_SERVICE_OPERATIONAL_24H_PASS",
        "fabricated_T+12",
        "fabricated_T+18",
        "fabricated_T+24",
        "completed_full_24h",
    ],
    "mainnet": False,
    "real_money": False,
    "exchange_write": False,
    "source_observation_report": (
        "docs/04_readiness/NEXUS_SINGLE_SERVICE_OPERATIONAL_OBSERVATION_ABORTED_REPORT.md"
    ),
    "source_observation_checksum": checksum,
}
text = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
Path("artifacts/single_service_observation/observation_aborted.json").write_text(
    text, encoding="utf-8"
)
ov = {
    "founder_override_id": "FO-20260801-ABORT24H-DEMO6H12H",
    "founder_override_reason": "FOUNDER_PRIORITIZED_BOUNDED_DEMO_EXECUTION_VALIDATION",
    "approved_at": "2026-08-01T08:34:44Z",
    "approved_scope": [
        "abort_incomplete_operational_24h",
        "demo_autonomous_6h_v2",
        "demo_autonomous_12h_v3_via_machine_gate",
    ],
    "source_observation_report": (
        "docs/04_readiness/NEXUS_SINGLE_SERVICE_OPERATIONAL_OBSERVATION_ABORTED_REPORT.md"
    ),
    "source_observation_checksum": checksum,
}
Path("artifacts/founder_override_record.json").write_text(
    json.dumps(ov, indent=2) + "\n", encoding="utf-8"
)
print("hours", hours)
print("checksum", checksum)
print(
    "positions",
    payload["position_count_at_abort"],
    "orders",
    payload["open_order_count_at_abort"],
    "writes",
    payload["exchange_write_call_count_at_abort"],
)
