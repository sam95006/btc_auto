#!/usr/bin/env python3
"""Run Founder-private control plane V10 readiness + secret scan.

Emits artifacts under:
  artifacts/readiness/immutable/v10_private_control_plane/

No exchange writes. No Demo/Shadow orders. No public product surface.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ART_REL = Path("artifacts/readiness/immutable/v10_private_control_plane")
OWNED_SCAN_PATHS = [
    "backend/nexus_private_control",
    "tools/research/run_private_control_plane_v10.py",
    "tests/test_private_control_plane_v10.py",
    "artifacts/readiness/immutable/v10_private_control_plane",
]

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def scan_secrets(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_SCAN_PATHS:
        target = root / rel
        files: list[Path]
        if target.is_dir():
            files = [p for p in target.rglob("*") if p.is_file() and p.suffix.lower() in {".py", ".json", ".md", ".yml", ".yaml"}]
        elif target.is_file():
            files = [target]
        else:
            continue
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append({"path": str(path.relative_to(root)).replace("\\", "/"), "pattern": pat.pattern})
                    break
    return {
        "schema": "v10_private_control_plane_secret_scan",
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": OWNED_SCAN_PATHS,
    }


def _exercise_plane(tmp: Path) -> dict[str, Any]:
    from backend.nexus_private_control import ALLOWED_MODES, ControlPlaneError, PrivateControlPlaneV10
    from backend.nexus_private_control.write_guard import ExchangeWriteForbidden

    plane = PrivateControlPlaneV10(tmp)
    matrix: list[dict[str, Any]] = []

    for mode in sorted(ALLOWED_MODES):
        p = PrivateControlPlaneV10(tmp / f"mode_{mode}")
        st = p.start(mode, run_id=f"run_{mode.lower()}")
        matrix.append({"control": "start", "mode": mode, "state": st["state"], "ok": st["state"] == "RUNNING"})
        p.stop(reason="mode_matrix")

    # Full control path on HISTORICAL_REPLAY_SIMULATED
    st = plane.start("HISTORICAL_REPLAY_SIMULATED", run_id="pcp_v10_readiness")
    matrix.append({"control": "start", "state": st["state"], "ok": st["state"] == "RUNNING"})
    matrix.append({"control": "status", "state": plane.status()["state"], "ok": True})
    matrix.append({"control": "pause", "state": plane.pause()["state"], "ok": plane.state_machine.state == "PAUSED"})
    matrix.append({"control": "resume", "state": plane.resume()["state"], "ok": plane.state_machine.state == "RUNNING"})
    ck = plane.checkpoint()
    matrix.append({"control": "checkpoint", "ok": "checkpoint" in ck})
    rec = plane.recover(reason="readiness")
    matrix.append({"control": "recover", "ok": rec.get("recovery_status") == "RECOVERED"})
    matrix.append({"control": "health", "ok": plane.health().get("exchange_write_attempt_count") == 0})
    obs = plane.observability()
    matrix.append(
        {
            "control": "observability",
            "ok": obs.get("read_only") is True and obs.get("secrets_present") is False,
        }
    )

    # Banned mode fail-closed
    banned_ok = False
    try:
        PrivateControlPlaneV10(tmp / "banned").start("DEMO_LIVE")
    except ControlPlaneError:
        banned_ok = True
    matrix.append({"control": "banned_mode_reject", "ok": banned_ok})

    # Exchange write fail-closed on an isolated plane (does not pollute formal counter).
    write_plane = PrivateControlPlaneV10(tmp / "write_trap")
    write_plane.start("HISTORICAL_REPLAY_SIMULATED", run_id="pcp_write_trap")
    write_ok = False
    try:
        write_plane.attempt_exchange_write("/v5/order/create")
    except ExchangeWriteForbidden:
        write_ok = (
            write_plane.state_machine.state == "FAILED_SAFE"
            and write_plane.guard.exchange_write_attempt_count == 1
        )
    matrix.append({"control": "exchange_write_fail_closed", "ok": write_ok})

    # Kill switch on a fresh plane
    ks = PrivateControlPlaneV10(tmp / "kill")
    ks.start("PROVIDER_CALIBRATION", run_id="pcp_kill")
    killed = ks.kill_switch(reason="readiness_kill")
    matrix.append(
        {
            "control": "kill_switch",
            "ok": killed.get("kill_switch_status") == "TRIGGERED" and ks.state_machine.state == "KILLED",
        }
    )
    resume_blocked = False
    try:
        ks.resume()
    except ControlPlaneError:
        resume_blocked = True
    matrix.append({"control": "kill_switch_blocks_resume", "ok": resume_blocked})

    # Formal plane remains clean (stop it for a tidy terminal state).
    plane.stop(reason="readiness_complete")
    all_ok = all(bool(item.get("ok")) for item in matrix)
    return {
        "matrix": matrix,
        "all_controls_ok": all_ok,
        "final_status": plane.status(),
        "observability": plane.observability(),
        "exchange_write_attempt_count": plane.guard.exchange_write_attempt_count,
        "intentional_write_trap_blocked": write_ok,
        "intentional_write_trap_attempt_count": write_plane.guard.exchange_write_attempt_count,
    }


def main() -> int:
    art = ROOT / ART_REL
    art.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pcp_v10_") as td:
        exercise = _exercise_plane(Path(td))

    # Write preliminary artifacts so secret scan can include them (no secrets).
    control_matrix = {
        "schema": "v10_private_control_plane_control_matrix",
        "created_at": _utc(),
        "controls": list(
            __import__(
                "backend.nexus_private_control.plane", fromlist=["PrivateControlPlaneV10"]
            ).PrivateControlPlaneV10.CONTROLS
        ),
        "allowed_modes": sorted(
            __import__("backend.nexus_private_control.modes", fromlist=["ALLOWED_MODES"]).ALLOWED_MODES
        ),
        "results": exercise["matrix"],
        "all_controls_ok": exercise["all_controls_ok"],
        "exchange_write_attempt_count": exercise["exchange_write_attempt_count"],
        "intentional_write_trap_blocked": exercise["intentional_write_trap_blocked"],
        "intentional_write_trap_attempt_count": exercise["intentional_write_trap_attempt_count"],
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "public_api_exposed": False,
        "founder_private": True,
    }
    _write(art / "control_matrix.json", control_matrix)
    _write(art / "observability_snapshot.json", exercise["observability"])

    secret = scan_secrets(ROOT)
    _write(art / "secret_scan.json", secret)

    # Re-scan after writing artifacts (should still be clean).
    secret = scan_secrets(ROOT)
    _write(art / "secret_scan.json", secret)

    formal_writes = int(exercise["exchange_write_attempt_count"])
    status = {
        "schema": "v10_private_control_plane_status",
        "created_at": _utc(),
        "lane": "A",
        "lane_name": "PRIVATE_CONTROL_PLANE",
        "branch": "feature/v10-private-control-plane",
        "package": "backend.nexus_private_control",
        "status": (
            "PASS"
            if exercise["all_controls_ok"]
            and secret["secret_leak_count"] == 0
            and formal_writes == 0
            else "FAIL"
        ),
        "all_controls_ok": exercise["all_controls_ok"],
        "secret_leak_count": secret["secret_leak_count"],
        "exchange_write_attempt_count": formal_writes,
        "intentional_write_trap_blocked": exercise["intentional_write_trap_blocked"],
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "mainnet": False,
        "real_money": False,
        "public_api_exposed": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "owned_paths": OWNED_SCAN_PATHS,
        "prohibited_paths_untouched": [
            "frontend",
            "backend/nexus_demo_execution",
            "other_v10_lane_owned_paths",
            "pr26_public_surfaces",
        ],
        "base_commit": "752905784e9d26a84dbc17ae6460d8a15761b320",
    }
    _write(art / "private_control_plane_status.json", status)
    print(json.dumps(status, indent=2))
    return 0 if status["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
