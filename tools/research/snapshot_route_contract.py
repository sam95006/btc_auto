#!/usr/bin/env python3
"""Route contract snapshot using production entrypoint run.app.

Classification of prior IMPORT_ERROR:
SCANNER_USED_WRONG_APP_ENTRYPOINT

backend.api.server does not export Flask app; production entrypoints are:
- run.app
- app.app (re-export for Zeabur/Gunicorn)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "readiness" / "route_contract_snapshot.json"


def main() -> int:
    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")
    sys.path.insert(0, str(ROOT))

    from run import app

    routes = sorted({rule.rule for rule in app.url_map.iter_rules()})
    optional = sorted(r for r in routes if r.startswith("/ws/"))
    core = sorted(set(routes) - set(optional))
    payload = {
        "route_snapshot_status": "PASS",
        "entrypoint": "run.app",
        "alternate_entrypoint": "app.app",
        "route_import_discrepancy_classification": "SCANNER_USED_WRONG_APP_ENTRYPOINT",
        "wrong_entrypoint_note": "backend.api.server has no app attribute; do not import app from it",
        "route_count": len(routes),
        "route_count_core": len(core),
        "optional_routes": optional,
        "routes": routes,
        "routes_core": core,
        "runtime_import_error_count": 0,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: payload[k] for k in payload if k not in {"routes", "routes_core"}},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
