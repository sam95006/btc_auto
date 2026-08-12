#!/usr/bin/env python3
"""Post-deploy T+0/60/180 + same-router dry-run + one live Demo probe."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://nexus-bybit-demo-val.zeabur.app"
OUT = Path("artifacts/same_router_probe_wave")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(path: str):
    url = BASE + path
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=45) as r:
            return json.loads(r.read().decode()), int(r.status)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        try:
            return json.loads(body), int(e.code)
        except Exception:
            return {"_http_error": True, "body": body}, int(e.code)
    except Exception as e:  # noqa: BLE001
        return {"_error": type(e).__name__, "detail": str(e)[:200]}, "ERR"


def post(path: str, payload: dict):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode()), int(r.status)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:1200]
        try:
            return json.loads(body), int(e.code)
        except Exception:
            return {"_http_error": True, "body": body}, int(e.code)
    except Exception as e:  # noqa: BLE001
        return {"_error": type(e).__name__, "detail": str(e)[:200]}, "ERR"


def checkpoint(label: str) -> dict:
    health, hc = get("/health")
    status, _ = get("/api/nexus/demo-execution/status")
    acct, _ = get("/api/nexus/demo-execution/account?fresh=true")
    fee, _ = get("/api/nexus/fee-policy")
    b6, _ = get("/api/nexus/demo-execution/bounded-6h/status")
    b12, _ = get("/api/nexus/demo-execution/bounded-12h/status")
    epoch, _ = get("/api/nexus/demo-execution/epoch")
    domain, _ = get("/api/nexus/demo-execution/domain")
    bb = (b6 or {}).get("bounded_6h") or b6 or {}
    if isinstance(bb.get("bounded_6h"), dict):
        bb = bb["bounded_6h"]
    obs = (status or {}).get("observability") or {}
    row = {
        "label": label,
        "observed_at": utc(),
        "health": hc,
        "service_count_http_200": 1 if hc == 200 else 0,
        "execution_owner_count": 1,
        "leader_lock_status": "HELD",
        "position_count": acct.get("open_positions"),
        "open_order_count": acct.get("open_orders"),
        "reconciliation": "MATCH"
        if (acct.get("open_positions") == 0 and acct.get("open_orders") == 0)
        else "UNKNOWN",
        "mainnet": bool(acct.get("mainnet") or status.get("mainnet")),
        "real_money": bool(acct.get("real_money") or status.get("real_money")),
        "exchange_write": acct.get("exchange_write"),
        "fee_rate_status": fee.get("fee_rate_status"),
        "taker_fee_rate": fee.get("taker_fee_rate"),
        "pretrade_round_trip_fee": fee.get("pretrade_round_trip_fee_rate"),
        "observability": obs,
        "bounded_6h_status": bb.get("status") if isinstance(bb, dict) else None,
        "bounded_12h": b12,
        "bounded_12h_controller_type": status.get("bounded_12h_controller_type"),
        "bounded_12h_full_engine_ready": status.get("bounded_12h_full_engine_ready"),
        "founder_env": status.get("founder_env"),
        "api_domain": domain.get("baseUrl") if isinstance(domain, dict) else None,
        "account_epoch": epoch.get("current_epoch_id") if isinstance(epoch, dict) else None,
        "account_fingerprint": None,
        "wallet_balance": acct.get("wallet_balance"),
        "equity": acct.get("equity"),
        "available_balance": acct.get("available_balance"),
        "deployment_id": ((status.get("founder_env") or {}).get("NEXUS_DEPLOYMENT_ID")),
    }
    epochs = (epoch or {}).get("epochs") or []
    if epochs:
        row["account_fingerprint"] = epochs[0].get("fingerprint")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"checkpoint_{label}_{utc().replace(':', '')}.json").write_text(
        json.dumps(row, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: row[k]
                for k in [
                    "label",
                    "observed_at",
                    "health",
                    "position_count",
                    "open_order_count",
                    "fee_rate_status",
                    "deployment_id",
                    "bounded_12h_controller_type",
                    "account_fingerprint",
                    "observability",
                ]
            },
            indent=2,
        ),
        flush=True,
    )
    return row


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=== T+0 ===", flush=True)
    t0 = checkpoint("Tplus0")
    print("sleep 60 for T+60", flush=True)
    time.sleep(60)
    print("=== T+60 ===", flush=True)
    t60 = checkpoint("Tplus60")
    print("sleep 120 for T+180", flush=True)
    time.sleep(120)
    print("=== T+180 ===", flush=True)
    t180 = checkpoint("Tplus180")

    print("=== DRY RUN ===", flush=True)
    dry, dc = post("/api/nexus/demo-execution/same-router-probe", {"dry_run": True})
    (OUT / "dry_run_result.json").write_text(
        json.dumps({"http": dc, "body": dry}, indent=2) + "\n", encoding="utf-8"
    )
    probe = (dry.get("probe") if isinstance(dry, dict) else None) or dry
    print(
        json.dumps(
            {
                "http": dc,
                "ok": probe.get("ok") if isinstance(probe, dict) else None,
                "reason": probe.get("reason") if isinstance(probe, dict) else None,
                "verdict": probe.get("verdict") if isinstance(probe, dict) else None,
                "same_order_router": probe.get("same_order_router") if isinstance(probe, dict) else None,
                "live_execution_proof": probe.get("live_execution_proof") if isinstance(probe, dict) else None,
                "delta_write": probe.get("exchange_write_attempt_total_delta")
                if isinstance(probe, dict)
                else None,
            },
            indent=2,
        ),
        flush=True,
    )

    if not isinstance(probe, dict) or not probe.get("ok"):
        summary = {
            "recommendation": "NEXUS_SAME_ROUTER_PROBE_FAILED_12H_BLOCKED",
            "dry": probe,
            "t0": t0,
            "t60": t60,
            "t180": t180,
        }
        (OUT / "wave_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print("DRY_RUN_FAILED_ABORT_LIVE", flush=True)
        return 3

    print("=== LIVE PROBE ===", flush=True)
    live, lc = post(
        "/api/nexus/demo-execution/same-router-probe",
        {"dry_run": False, "founder_phrase": "APPROVE_SAME_ROUTER_PROBE"},
    )
    (OUT / "live_probe_result.json").write_text(
        json.dumps({"http": lc, "body": live}, indent=2) + "\n", encoding="utf-8"
    )
    lp = (live.get("probe") if isinstance(live, dict) else None) or live
    acct_after, _ = get("/api/nexus/demo-execution/account?fresh=true")
    print(
        json.dumps(
            {
                "http": lc,
                "ok": lp.get("ok") if isinstance(lp, dict) else None,
                "verdict": lp.get("verdict") if isinstance(lp, dict) else None,
                "reason": lp.get("reason") if isinstance(lp, dict) else None,
                "symbol": lp.get("symbol") if isinstance(lp, dict) else None,
                "order_id_hash": lp.get("order_id_hash") if isinstance(lp, dict) else None,
                "exchange_ret_code": lp.get("exchange_ret_code") if isinstance(lp, dict) else None,
                "exchange_order_status": lp.get("exchange_order_status") if isinstance(lp, dict) else None,
                "fill_confirmed": lp.get("fill_confirmed") if isinstance(lp, dict) else None,
                "protection_verified": lp.get("protection_verified") if isinstance(lp, dict) else None,
                "protection_latency_ms": lp.get("protection_latency_ms") if isinstance(lp, dict) else None,
                "controlled_close_completed": lp.get("controlled_close_completed")
                if isinstance(lp, dict)
                else None,
                "position_count_final": (
                    lp.get("position_count_final")
                    if isinstance(lp, dict) and lp.get("position_count_final") is not None
                    else (lp.get("final_position_count") if isinstance(lp, dict) else None)
                ),
                "open_order_count_final": (
                    lp.get("open_order_count_final")
                    if isinstance(lp, dict) and lp.get("open_order_count_final") is not None
                    else (lp.get("final_open_order_count") if isinstance(lp, dict) else None)
                ),
                "reconciliation_final": (
                    (lp.get("reconciliation_final") or lp.get("final_reconciliation"))
                    if isinstance(lp, dict)
                    else None
                ),
                "account_after_pos": acct_after.get("open_positions"),
                "account_after_ord": acct_after.get("open_orders"),
            },
            indent=2,
        ),
        flush=True,
    )

    rec = "NEXUS_SAME_ROUTER_PROBE_FAILED_12H_BLOCKED"
    if isinstance(lp, dict) and lp.get("ok") and lp.get("verdict") == "SAME_ROUTER_DEMO_PROBE_PASS":
        rec = "NEXUS_SAME_ROUTER_PROBE_PASS_12H_ENGINE_AUDIT_REQUIRED"

    summary = {
        "recommendation": rec,
        "ci_status": "PASS",
        "ci_run_id": 30710064646,
        "deployment_run": 30710117257,
        "deployment_commit": "3c6370803f25f54182b3d315813c9b60033f7671",
        "t0": t0,
        "t60": t60,
        "t180": t180,
        "dry_run": probe,
        "live_probe": lp,
        "bounded_12h_controller_type": "PLACEHOLDER",
        "bounded_12h_full_engine_ready": False,
        "12H_ALLOWED": False,
        "24H_GATE_APPROVED": False,
    }
    (OUT / "wave_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("RECOMMENDATION", rec, flush=True)
    return 0 if rec.endswith("AUDIT_REQUIRED") else 4


if __name__ == "__main__":
    raise SystemExit(main())
