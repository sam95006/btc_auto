"""Operator GO gate for Stage 3 C+1 demo-order."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from tools.research.bybit_demo_learning_common import ROOT

OPERATOR_GO_ENV = "OPERATOR_GO_STAGE3_C1_DEMO_ORDER"
OPERATOR_GO_24H_ENV = "OPERATOR_GO_STAGE3_24H_RUNNER"
OPERATOR_GO_FILE = ROOT / "data/external_alpha/reports/stage3_c1_operator_go.json"


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def operator_go_24h_present() -> bool:
    return _truthy(os.environ.get(OPERATOR_GO_24H_ENV))


def operator_go_present() -> bool:
    if _truthy(os.environ.get(OPERATOR_GO_ENV)):
        return True
    if OPERATOR_GO_FILE.is_file():
        try:
            data = json.loads(OPERATOR_GO_FILE.read_text(encoding="utf-8"))
            return bool(data.get("operator_go_stage3_c1_demo_order"))
        except json.JSONDecodeError:
            return False
    return False


def operator_go_metadata() -> Dict[str, Any]:
    meta: Dict[str, Any] = {"env_var": OPERATOR_GO_ENV, "env_present": _truthy(os.environ.get(OPERATOR_GO_ENV))}
    if OPERATOR_GO_FILE.is_file():
        try:
            meta["file"] = json.loads(OPERATOR_GO_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta["file_parse_error"] = True
    return meta


def operator_go_24h_metadata() -> Dict[str, Any]:
    return {
        "env_var": OPERATOR_GO_24H_ENV,
        "env_present": operator_go_24h_present(),
        "c1_demo_order_env": OPERATOR_GO_ENV,
        "c1_demo_order_present": _truthy(os.environ.get(OPERATOR_GO_ENV)),
    }


def demo_order_operator_go_present() -> bool:
    return operator_go_present() or operator_go_24h_present()
