#!/usr/bin/env python3
"""Run V10 Execution Session Scale campaign → immutable readiness package.

Full targets (default):
  * 100,000 execution fuzz scenarios
  * 30-day + 90-day accelerated Session with injection matrix

Smoke / CI overrides:
  NEXUS_V10_SMOKE=1
  NEXUS_V10_FUZZ_SCENARIOS=<int>
  NEXUS_V10_SESSION_CANDIDATES=<int>
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/readiness/immutable/v10_execution_session_scale"

OWNED_SCAN_PATHS = (
    "backend/nexus_execution/scale_v10.py",
    "backend/nexus_execution/scale_",
    "backend/nexus_autonomy/session_scale_v10.py",
    "tools/research/run_execution_session_scale_v10.py",
    "tests/test_execution_session_scale_v10.py",
)

SECRET_PATTERNS = (
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_secret_scan() -> dict:
    hits: list[str] = []
    files_scanned = 0
    for rel in OWNED_SCAN_PATHS:
        path = ROOT / rel
        targets: list[Path]
        if path.is_dir():
            targets = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".md"})
        elif path.is_file():
            targets = [path]
        else:
            continue
        for fp in targets:
            files_scanned += 1
            text = fp.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(str(fp.relative_to(ROOT)).replace("\\", "/"))
                    break
    return {
        "schema": "v10_execution_session_scale_secret_scan",
        "secret_leak_count": len(hits),
        "hits": hits,
        "files_scanned": files_scanned,
        "owned_paths": list(OWNED_SCAN_PATHS),
        "created_at": _utc(),
    }


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from backend.nexus_execution.scale_.config import load_scale_config
    from backend.nexus_execution.scale_v10 import (
        PASS_STATUS,
        run_scale_fuzz,
        write_scale_artifacts,
    )
    from backend.nexus_autonomy.session_scale_v10 import run_session_scale_campaign

    cfg = load_scale_config()
    print(
        f"v10 scale mode={cfg.mode} fuzz={cfg.fuzz_scenarios} "
        f"c30={cfg.session_candidate_count_30d} c90={cfg.session_candidate_count_90d}",
        flush=True,
    )

    fuzz = run_scale_fuzz(config=cfg)
    print(
        f"fuzz done count={fuzz.get('generated_execution_scenario_count')} "
        f"pass={fuzz.get('pass')}",
        flush=True,
    )

    run_root = ROOT / ".nexus_runtime" / "tmp" / "v10_execution_session_scale"
    run_root.mkdir(parents=True, exist_ok=True)
    session = run_session_scale_campaign(run_root, config=cfg)
    print(
        f"session scale status={session.get('Session_Scale_status')} "
        f"pass={session.get('session_scale_pass')}",
        flush=True,
    )

    secret_scan = run_secret_scan()
    print(f"secret_scan leaks={secret_scan['secret_leak_count']}", flush=True)

    paths = write_scale_artifacts(
        OUT,
        fuzz=fuzz,
        session=session,
        secret_scan=secret_scan,
    )
    # Also write per-session summaries at top level for quick inspection.
    _write(OUT / "session_30d_report.json", (session.get("sessions") or {}).get("SESSION_30D") or {})
    _write(OUT / "session_90d_report.json", (session.get("sessions") or {}).get("SESSION_90D") or {})
    _write(OUT / "focused_probes.json", session.get("focused_probes") or {})

    status_path = paths.get("scale_status.json")
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path else {}
    summary = {
        "status": status.get("status"),
        "fuzz_scenarios_achieved": status.get("fuzz_scenarios_achieved"),
        "fuzz_pass": status.get("fuzz_pass"),
        "session_scale_pass": status.get("session_scale_pass"),
        "secret_scan_pass": status.get("secret_scan_pass"),
        "out": str(OUT),
    }
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if status.get("status") == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
