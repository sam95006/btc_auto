#!/usr/bin/env python3
"""Print demo-execution smoke summary from /tmp files (no secrets)."""
from __future__ import annotations

import json
from pathlib import Path

health = json.loads(Path("/tmp/health.json").read_text(encoding="utf-8"))
print("health_ok", bool(health))
path = Path("/tmp/demo_status.json")
if not path.is_file():
    print("status_note", "missing")
    raise SystemExit(0)
try:
    status = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:  # noqa: BLE001
    print("status_note", type(exc).__name__)
    raise SystemExit(0)
print("gate", status.get("current_stage") or status.get("gate"))
print("first_demo_smoke_order_ready", status.get("first_demo_smoke_order_ready"))
