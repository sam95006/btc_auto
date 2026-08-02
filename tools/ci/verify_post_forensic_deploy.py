#!/usr/bin/env python3
"""Post-deploy read-only forensic verification (T+0 / T+60 / T+180). No writes / no session start."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("DEMO_VAL_URL", "https://nexus-bybit-demo-val.zeabur.app").rstrip("/")
EXPECTED_COMMIT = os.environ.get("EXPECTED_DEPLOYMENT_COMMIT", "").strip()
OUT = Path(os.environ.get("VERIFY_OUT", "artifacts/demo_validation_12h_v3_forensic/post_deploy_verify"))


def _get(path: str) -> tuple[dict, int]:
    url = f"{BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=45) as resp:
            return json.loads(resp.read().decode()), int(resp.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        try:
            payload = json.loads(body)
        except Exception:
            payload = {"raw": body}
        return payload, int(exc.code)
    except Exception as exc:  # noqa: BLE001
        return {"_error": type(exc).__name__, "detail": str(exc)[:200]}, 0


def snapshot(label: str) -> dict:
    health, hcode = _get("/health")
    status, scode_status = _get("/api/nexus/demo-execution/status")
    identity, icode = _get("/api/nexus/demo-execution/runtime-identity")
    acct, acode = _get("/api/nexus/demo-execution/account?fresh=true")
    b12, bcode = _get("/api/nexus/demo-execution/bounded-12h/status")
    forensic, fcode = _get(
        "/api/nexus/demo-execution/account/forensic?starting_wallet=5024.24829280&paginate=true&max_pages=10"
    )
    stream_status, scode = _get("/api/nexus/demo-execution/persistence/stream/status")
    stream_events, ecode = _get("/api/nexus/demo-execution/persistence/stream/events?limit=5")

    bb = b12.get("bounded_12h") if isinstance(b12, dict) else {}
    if isinstance(bb, dict) and isinstance(bb.get("bounded_12h"), dict):
        bb = bb["bounded_12h"]
    ri = (identity if isinstance(identity, dict) and identity.get("runtime_current_code_commit") else None) or (
        (status.get("runtime_identity") if isinstance(status, dict) else {}) or {}
    )
    pos = acct.get("open_positions") if isinstance(acct, dict) else None
    ord_ = acct.get("open_orders") if isinstance(acct, dict) else None
    code = str(ri.get("runtime_current_code_commit") or ri.get("deployment_commit") or "")
    baked = str(ri.get("container_baked_commit") or status.get("baked_deployment_commit") or "")
    iclass = str(ri.get("identity_class") or ri.get("runtime_identity_classification") or "")
    identity_confirmed = (
        iclass == "RUNTIME_IDENTITY_CONFIRMED"
        and bool(EXPECTED_COMMIT)
        and code.startswith(EXPECTED_COMMIT[:12])
        and baked.startswith(EXPECTED_COMMIT[:12])
    )
    out = {
        "label": label,
        "health_http": hcode,
        "status_http": scode_status,
        "runtime_identity_http": icode,
        "account_http": acode,
        "bounded_12h_http": bcode,
        "forensic_routes_http": fcode,
        "persistence_stream_status_http": scode,
        "persistence_stream_events_http": ecode,
        "runtime_identity_classification": iclass,
        "runtime_current_code_commit": code,
        "container_baked_commit": baked,
        "persistent_state_origin_commit": ri.get("persistent_state_origin_commit"),
        "persistent_state_last_writer_commit": ri.get("persistent_state_last_writer_commit"),
        "deployment_commit": code,
        "deployment_commit_match": (not EXPECTED_COMMIT) or code.startswith(EXPECTED_COMMIT[:12]),
        "runtime_identity_confirmed": identity_confirmed,
        "position_count": pos,
        "open_order_count": ord_,
        "reconciliation": (
            "MATCH" if pos == 0 and ord_ == 0 else ("UNKNOWN" if pos is None or ord_ is None else "MISMATCH")
        ),
        "bounded_12h_status": (bb or {}).get("status") if isinstance(bb, dict) else None,
        "thread_alive": (bb or {}).get("thread_alive") if isinstance(bb, dict) else None,
        "write_window_open": bool(
            (bb or {}).get("session_write_enabled")
            or (bb or {}).get("smoke_write_window_open")
            or (bb or {}).get("session_write_window_open")
        )
        if isinstance(bb, dict)
        else None,
        "negative_count_sentinel_present": pos == -1 or ord_ == -1,
        "forensic_account_classification": forensic.get("account_classification") if isinstance(forensic, dict) else None,
        "wallet_delta_reconcile": forensic.get("wallet_delta_reconcile") if isinstance(forensic, dict) else None,
        "stream_status_ok": bool(isinstance(stream_status, dict) and stream_status.get("ok") is not False and scode == 200),
        "stream_events_ok": bool(isinstance(stream_events, dict) and ecode == 200),
        "mainnet": bool((status or {}).get("mainnet")) if isinstance(status, dict) else None,
        "real_money": bool((status or {}).get("real_money")) if isinstance(status, dict) else None,
        "health_payload_ok": hcode == 200,
    }
    return out


def _checkpoint_ok(snap: dict) -> bool:
    return (
        snap.get("health_http") == 200
        and snap.get("status_http") == 200
        and snap.get("forensic_routes_http") == 200
        and snap.get("persistence_stream_status_http") == 200
        and snap.get("persistence_stream_events_http") == 200
        and snap.get("position_count") == 0
        and snap.get("open_order_count") == 0
        and snap.get("reconciliation") == "MATCH"
        and snap.get("negative_count_sentinel_present") is False
        and snap.get("mainnet") is False
        and snap.get("real_money") is False
        and (not EXPECTED_COMMIT or snap.get("runtime_identity_confirmed") is True)
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    for label, delay in (("Tplus0", 0), ("Tplus60", 60), ("Tplus180", 180)):
        if delay:
            print(f"sleep {delay}s for {label}", flush=True)
            time.sleep(delay)
        snap = snapshot(label)
        results[label] = snap
        (OUT / f"{label}.json").write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(snap, indent=2), flush=True)
        if not _checkpoint_ok(snap):
            print(f"checkpoint_failed={label}", flush=True)
            (OUT / "verify_summary.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
            return 2
    (OUT / "verify_summary.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("verify_ok_t0_t60_t180", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
