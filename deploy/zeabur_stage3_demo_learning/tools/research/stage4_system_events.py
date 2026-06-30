"""Stage 4 system event log (rate limits, skipped ticks — no secrets)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from tools.research.bybit_demo_learning_common import utc_now_iso

ROOT = Path(__file__).resolve().parents[2]


def resolve_system_events_path() -> Path:
    custom = os.environ.get("STAGE4_OUTPUT_DIR", "").strip()
    if custom:
        out = Path(custom)
    else:
        nexus = os.environ.get("NEXUS_DATA_DIR", "").strip()
        if nexus:
            out = Path(nexus) / "stage4_ai_decisions"
        else:
            out = ROOT / "data" / "external_alpha" / "stage4_ai_decisions"
    out.mkdir(parents=True, exist_ok=True)
    return out / "stage4_system_events.jsonl"


def append_system_event(event: Dict[str, Any]) -> None:
    row = {"created_at_utc": utc_now_iso(), **event}
    path = resolve_system_events_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_system_events(output_dir: Path | None = None) -> list[Dict[str, Any]]:
    if output_dir is not None:
        path = output_dir / "stage4_system_events.jsonl"
    else:
        path = resolve_system_events_path()
    if not path.is_file():
        return []
    rows: list[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows
