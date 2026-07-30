#!/usr/bin/env python3
"""End-of-session finalizer for Demo 6H — readonly by default; never redeploys.

Does NOT extend session, start 24H, change env, or mutate cost gates.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _get_json(url: str, timeout: float = 20.0) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _bounded(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("bounded_6h") if isinstance(payload.get("bounded_6h"), dict) else payload


def finalize(
    *,
    service_url: str,
    session_id: str,
    expected_code_sha: str | None,
    output: Path,
    strict: bool,
    readonly_finalize: bool,
    analyze_script: Path,
) -> dict[str, Any]:
    base = service_url.rstrip("/")
    now = time.time()
    report: dict[str, Any] = {
        "ok": False,
        "session_id": session_id,
        "readonly_finalize": readonly_finalize,
        "steps": [],
        "automatic_extension": False,
        "24h_started": False,
        "redeploy": False,
        "env_change": False,
    }

    def step(name: str, **kw: Any) -> None:
        report["steps"].append({"step": name, **kw})

    # 1) Status
    try:
        status_payload = _get_json(f"{base}/api/nexus/demo-execution/bounded-6h/status")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        report["error"] = f"status_fetch_failed:{type(exc).__name__}"
        return report

    b = _bounded(status_payload)
    sid = b.get("session_id")
    if sid and sid != session_id:
        report["error"] = "session_id_mismatch"
        report["observed_session_id"] = sid
        if strict:
            return report
    step("confirm_session", status=b.get("status"), write=b.get("session_write_enabled"))

    # 2) Deadline guard
    ends = b.get("ends_at") or b.get("deadline_at")
    started = b.get("started_at")
    deadline = None
    if ends is not None:
        deadline = float(ends)
    elif started is not None:
        deadline = float(started) + 6 * 3600
    if deadline is None:
        report["error"] = "deadline_unknown"
        if strict:
            return report
    elif now < deadline:
        report["error"] = "deadline_not_reached"
        report["deadline_at"] = deadline
        report["seconds_remaining"] = deadline - now
        step("deadline_guard", passed=False, seconds_remaining=deadline - now)
        if strict or readonly_finalize:
            return report
    else:
        step("deadline_guard", passed=True, deadline_at=deadline)

    # 3) Write window / new orders
    write_enabled = bool(b.get("session_write_enabled"))
    status = str(b.get("status") or "")
    step(
        "write_window",
        session_write_enabled=write_enabled,
        status=status,
        expect_closed=not write_enabled or status in {"COMPLETED", "DISABLED", "STOPPED"},
    )

    # 4) Positions / orders
    try:
        account = _get_json(f"{base}/api/nexus/demo-execution/account?fresh=true")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        account = {}
    pos = account.get("open_positions", b.get("open_position"))
    orders = account.get("open_orders", b.get("open_order_count"))
    step("positions_orders", open_positions=pos, open_orders=orders)

    # 5) Wait note — readonly finalizer does not close positions; only reports.
    if pos not in (0, False, None, "0") and pos:
        step(
            "flat_wait",
            action="WAIT_SAFE_EXIT_ONLY",
            note="Do not remove protection; reduce-only exit only; finalizer does not force close",
        )
        if strict:
            report["error"] = "positions_still_open"
            return report

    # 6) Reconcile snapshot (read-only)
    recon = b.get("reconciliation") or account.get("reconciliation")
    step("reconcile", reconciliation=recon)

    # 7) Expected code sha label check (informational)
    ident = b.get("runtime_identity") if isinstance(b.get("runtime_identity"), dict) else {}
    observed_sha = ident.get("deployment_commit")
    step(
        "code_sha_label",
        expected_code_sha=expected_code_sha,
        observed_deployment_commit=observed_sha,
        note="Labels must stay separate from PR branch head",
    )

    # 8) Export placeholder — readonly finalize records that export must be pulled via approved export API/tool
    export_dir = output / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_manifest = {
        "session_id": session_id,
        "exported_at": now,
        "source": "readonly_finalize_placeholder",
        "note": "Pull real export via Demo Validation export endpoint/tool after write window closed; do not mount Zeabur /data",
        "status_snapshot": b,
        "account_snapshot_keys": list(account.keys()) if isinstance(account, dict) else [],
    }
    (export_dir / "session_status.json").write_text(json.dumps(b, indent=2), encoding="utf-8")
    (export_dir / "export_manifest.json").write_text(json.dumps(export_manifest, indent=2), encoding="utf-8")
    step("export_validation", path=str(export_dir), manifest_ok=True)

    # 9) Invoke analyzer
    analysis_out = output / "analysis"
    cmd = [
        sys.executable,
        str(analyze_script),
        "--input",
        str(export_dir),
        "--session-id",
        session_id,
        "--output",
        str(analysis_out),
    ]
    if strict:
        cmd.append("--strict")
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    step(
        "analysis_invocation",
        returncode=proc.returncode,
        stdout_tail=(proc.stdout or "")[-500:],
        stderr_tail=(proc.stderr or "")[-500:],
    )
    if proc.returncode != 0 and strict:
        report["error"] = "analysis_failed"
        return report

    # 10) Final report stub
    final = {
        "session_id": session_id,
        "status": status,
        "entries_total": b.get("entries_total"),
        "trades_completed": b.get("trades_completed"),
        "candidates_total": b.get("candidates_total"),
        "cost_gate_blocks": b.get("cost_gate_blocks"),
        "session_write_enabled": write_enabled,
        "reconciliation": recon,
        "zero_trade": int(b.get("entries_total") or 0) == 0 and int(b.get("trades_completed") or 0) == 0,
        "automatic_extension": False,
        "next_gate_24h": "NOT_PROPOSED_UNTIL_ANALYSIS_REVIEW",
        "forbidden": {
            "redeploy": False,
            "env_change": False,
            "start_24h": False,
            "loosen_cost_gate": False,
        },
    }
    (output / "NEXUS_DEMO_6H_FINALIZATION_REPORT.json").write_text(
        json.dumps({"finalize": report, "final": final, "steps": report["steps"]}, indent=2),
        encoding="utf-8",
    )
    report["ok"] = report.get("error") is None
    report["final"] = final
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Readonly finalize Demo 6H session")
    ap.add_argument("--service-url", required=True)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--expected-code-sha", default="9b6f57c1bc3afe988f0fc3829f62dad2ee510156")
    ap.add_argument("--output", required=True)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--readonly-finalize", action="store_true", default=True)
    ap.add_argument(
        "--analyze-script",
        default=str(Path(__file__).with_name("analyze_nexus_demo_session.py")),
    )
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    result = finalize(
        service_url=args.service_url,
        session_id=args.session_id,
        expected_code_sha=args.expected_code_sha,
        output=out,
        strict=args.strict,
        readonly_finalize=bool(args.readonly_finalize),
        analyze_script=Path(args.analyze_script),
    )
    print(json.dumps({"ok": result.get("ok"), "error": result.get("error"), "session_id": args.session_id}, ensure_ascii=False))
    if args.strict and not result.get("ok"):
        return 2
    # Deadline not reached is expected during session — exit 0 for prep smoke unless --strict
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
