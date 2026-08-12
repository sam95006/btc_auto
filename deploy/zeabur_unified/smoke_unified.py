#!/usr/bin/env python3
"""Focused smoke for unified Zeabur migration (no long while-True)."""

from __future__ import annotations

import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    # py_compile critical modules
    files = [
        ROOT / "backend/nexus_research_ai_autonomy/research_autonomy_service.py",
        ROOT / "backend/nexus_research_ai_autonomy/research_autonomy_scheduler.py",
        ROOT / "backend/nexus_research_ai_autonomy/cloud_paths_v301.py",
        ROOT / "backend/nexus_founder_demo_monitor/constants.py",
        ROOT / "run.py",
        ROOT / "backend/worker/runner.py",
    ]
    for f in files:
        py_compile.compile(str(f), doraise=True)

    assert (ROOT / "deploy/zeabur_unified/start.sh").is_file()
    df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "deploy/zeabur_unified/start.sh" in df
    assert "gunicorn" not in df.split("CMD", 1)[-1].lower() or "start.sh" in df

    # ZEABUR feed candidates must not include D:\
    os.environ["NEXUS_RUNTIME_LOCATION"] = "ZEABUR"
    os.environ["NEXUS_DATA_ROOT"] = "/data"
    os.environ["NEXUS_EVIDENCE_COORDINATOR"] = "/data/evidence_coordinator"
    from backend.nexus_founder_demo_monitor.constants import _runtime_live_candidates

    cands = _runtime_live_candidates()
    assert any("/data/" in c.replace("\\", "/") for c in cands)
    assert not any(c.startswith("D:") for c in cands)

    # Legacy embedded worker must stay off
    os.environ["NEXUS_LEGACY_WORKER_DISABLED"] = "true"
    os.environ["NEXUS_WEB_ONLY"] = "true"
    import run as runmod

    assert runmod._should_start_embedded_nexus_worker() is False

    # Autonomy multi-cycle mechanical
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["NEXUS_CAMPAIGN_ROOT"] = td
        env["MAINNET"] = "false"
        env["REAL_MONEY"] = "false"
        code = f"""
from pathlib import Path
from backend.nexus_research_ai_autonomy.research_autonomy_service import ResearchAutonomyService
from backend.nexus_research_ai_autonomy.research_autonomy_scheduler import SchedulerConfig
n={{'i':0}}
def cycle(_c):
    n['i']+=1
    return {{'ok':True,'WAIT':True,'executed':False,'market_scan_complete':True,'cycle_ai_ready':True,'reason':'SMOKE'}}
svc=ResearchAutonomyService(
  config=SchedulerConfig(campaign_root=Path({td!r}), cycle_sleep_sec=0.05),
  bindings={{'cycle_fn':cycle,'manage_fn':lambda c:{{'ok':True}},'reconcile_fn':lambda:{{'ok':True,'open':False}}}},
  max_cycles=3,max_seconds=10,skip_boot=True,skip_lock=True,
)
out=svc.run_forever()
assert out['cycles_run']==3
print('autonomy_smoke_ok', out['cycles_run'])
"""
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            return proc.returncode
        print(proc.stdout.strip())

    print("UNIFIED_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
