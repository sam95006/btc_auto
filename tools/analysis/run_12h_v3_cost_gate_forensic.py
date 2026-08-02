#!/usr/bin/env python3
"""Run Cost Gate forensic replay for 12H V3 (2407 geometry-complete candidates).

Prefers live persistence stream export; falls back to engine-equivalent synthesis.
Does not lower MIN_NET_REWARD_RISK_RATIO / MIN_NET_REWARD_TO_COST.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.nexus_demo_execution.cost_gate_forensic_replay import (  # noqa: E402
    replay_cost_gates,
    synthesize_fixed_geometry_rows,
)

BASE = os.environ.get("DEMO_VAL_URL", "https://nexus-bybit-demo-val.zeabur.app").rstrip("/")
OUT = Path(os.environ.get("FORENSIC_OUT", "artifacts/demo_validation_12h_v3_forensic"))
EXPECTED = 2407


def _fetch_cost_gates() -> list[dict]:
    rows: list[dict] = []
    offset = 0
    limit = 500
    while len(rows) < EXPECTED:
        url = f"{BASE}/api/nexus/demo-execution/persistence/stream/cost_gates?limit={limit}&offset={offset}"
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                payload = json.loads(resp.read().decode())
        except Exception as exc:  # noqa: BLE001
            print(f"stream_fetch_failed: {type(exc).__name__}: {exc}", flush=True)
            break
        batch = payload.get("rows") or (payload.get("data") or {}).get("rows") or []
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
        if len(batch) < limit:
            break
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    live = _fetch_cost_gates()
    source = "LIVE_PERSISTENCE_STREAM" if len(live) >= EXPECTED else "SYNTHETIC_FIXED_GEOMETRY"
    if source == "LIVE_PERSISTENCE_STREAM":
        rows = live[:EXPECTED]
    else:
        print(f"using synthetic rows live_count={len(live)}", flush=True)
        rows = synthesize_fixed_geometry_rows(EXPECTED)
    report = replay_cost_gates(rows)
    report["source"] = source
    report["session_id"] = "NEXUS-DEMO-12H-V3-20260801T181517Z-12hv3c01"
    (OUT / "cost_gate_forensic_replay.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md = [
        "# 12H V3 Cost Gate Forensic Replay",
        "",
        f"- source: `{source}`",
        f"- candidates_replayed: `{report['candidates_replayed']}`",
        f"- pass: `{report['cost_gate_pass_total']}` · block: `{report['cost_gate_block_total']}`",
        f"- primary_root_cause: `{report['primary_root_cause']}` — {report['primary_root_cause_text']}",
        f"- root_cause_codes: `{report['root_cause_codes']}`",
        f"- floors: `{report['floors_unchanged']}`",
        f"- threshold_change_allowed: `{report['threshold_change_allowed']}`",
        "",
        "## Distributions",
        "",
        "```json",
        json.dumps(report["distributions"], indent=2),
        "```",
        "",
    ]
    (OUT / "cost_gate_forensic_replay.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("source", "candidates_replayed", "cost_gate_pass_total", "primary_root_cause", "root_cause_codes")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
