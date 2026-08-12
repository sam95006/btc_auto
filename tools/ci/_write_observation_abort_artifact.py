from datetime import datetime
from pathlib import Path
import hashlib
import json
import shutil

started = datetime.fromisoformat("2026-07-31T05:11:30+00:00")
aborted = datetime.fromisoformat("2026-07-31T10:05:06+00:00")
hours = (aborted - started).total_seconds() / 3600.0

src = Path(r"C:\Temp\BTC_BOT_NEXUS_SINGLE_SERVICE\artifacts\single_service_observation")
dst = Path("artifacts/single_service_observation")
dst.mkdir(parents=True, exist_ok=True)
for name in [
    "checkpoint_ABORT_FINAL_20260731T100509Z.json",
    "checkpoint_TplusEARLY_20260731T055242Z.json",
    "checkpoint_Tplus1H_20260731T061155Z.json",
    "checkpoint_Tplus3H_20260731T081207Z.json",
    "checkpoint_latest.json",
]:
    p = src / name
    if p.exists():
        shutil.copy2(p, dst / name)

abort_cp = json.loads((dst / "checkpoint_ABORT_FINAL_20260731T100509Z.json").read_text(encoding="utf-8"))
early = json.loads((dst / "checkpoint_TplusEARLY_20260731T055242Z.json").read_text(encoding="utf-8"))

payload = {
    "observation_status": "ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION",
    "operational_observation_pass": False,
    "observation_completed_full_24h": False,
    "operational_observation_status": "ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION",
    "reason": "FOUNDER_PRIORITIZED_BOUNDED_DEMO_EXECUTION_VALIDATION",
    "founder_override_id": "FO-20260731-ABORT24H-DEMO6H12H",
    "founder_override_reason": "FOUNDER_PRIORITIZED_BOUNDED_DEMO_EXECUTION_VALIDATION",
    "approved_at": "2026-07-31T10:05:06Z",
    "approved_scope": [
        "abort_incomplete_operational_24h",
        "demo_autonomous_6h_v2",
        "demo_autonomous_12h_v3_via_machine_gate",
    ],
    "FOUNDER_OVERRIDE_ABORT_OPERATIONAL_24H": True,
    "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2": True,
    "FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3": True,
    "observation_started_at": "2026-07-31T05:11:30Z",
    "observation_aborted_at": "2026-07-31T10:05:06Z",
    "actual_duration_hours": round(hours, 4),
    "completed_checkpoints": ["T+EARLY", "T+1H", "T+3H", "ABORT_FINAL"],
    "missing_checkpoints": ["T+6H", "T+12H", "T+18H", "T+24H"],
    "runtime_health": {
        "health_status": abort_cp.get("health_status"),
        "market_worker_health": abort_cp.get("market_worker_health"),
        "position_supervisor_health": abort_cp.get("position_supervisor_health"),
        "persistence_health": abort_cp.get("persistence_health"),
        "soft_flags": abort_cp.get("soft_flags"),
    },
    "market_cycles_delta": None,
    "market_cycles_note": "market_cycle_count field non-incremental/timestamp-like; delta not claimed",
    "candidate_delta": int(abort_cp.get("candidate_count") or 0) - int(early.get("candidate_count") or 0),
    "geometry_complete": abort_cp.get("geometry_complete_count"),
    "geometry_missing": abort_cp.get("geometry_missing_count"),
    "cost_gate_delta": None,
    "position_count_at_abort": abort_cp.get("position_count"),
    "open_order_count_at_abort": abort_cp.get("open_order_count"),
    "exchange_write_call_count_at_abort": abort_cp.get("exchange_write_call_count"),
    "hidden_dependency_count_at_abort": abort_cp.get("hidden_dependency_count"),
    "active_http_200_service_count": abort_cp.get("active_http_200_service_count"),
    "execution_owner_count": abort_cp.get("execution_owner_count"),
    "legacy_stage3_http_status": abort_cp.get("stage3_http_status"),
    "legacy_control_plane_http_status": abort_cp.get("old_control_plane_http_status"),
    "legacy_stage3": "SUSPENDED",
    "legacy_control_plane": "SUSPENDED",
    "deployment_commit_at_abort": "598a5e11985f613007c8d65e61fa1dd9c7cbdf67",
    "deploy_run_at_abort": "30605493505",
    "abort_checkpoint_path": "artifacts/single_service_observation/checkpoint_ABORT_FINAL_20260731T100509Z.json",
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
}
out_json = Path("artifacts/single_service_observation/observation_aborted.json")
text = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
out_json.write_text(text, encoding="utf-8")
print("checksum", hashlib.sha256(text.encode("utf-8")).hexdigest())
print("duration_h", payload["actual_duration_hours"])
print("wrote", out_json)
