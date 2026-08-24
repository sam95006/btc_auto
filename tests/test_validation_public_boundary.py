from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

from backend.security.validation_public_guard import (
    CONTROL_TOKEN_ENV,
    GUARD_ENV,
    PUBLIC_GET_ALLOWLIST,
    install_validation_public_guard,
)


ROOT = Path(__file__).resolve().parents[1]
CONTROL_TOKEN = "test-validation-control-token-12345"
STATE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

RUN_REGISTERED_ROUTE_FILES = [
    "run.py",
    "backend/api/server.py",
    "backend/api/market_public_routes.py",
    "backend/api/market_scanner_routes.py",
    "backend/api/market_sector_routes.py",
    "backend/api/market_chart_routes.py",
    "backend/api/market_intelligence_routes.py",
    "backend/api/public_radar_routes.py",
    "backend/nexus_research/api_routes.py",
    "backend/nexus_public_decision_cloud/routes.py",
    "backend/nexus_public_decision_product/routes.py",
    "backend/nexus_public_member_intel/routes.py",
    "backend/nexus_pub17_market_pulse/routes.py",
    "backend/nexus_pub18_live_funnel/routes.py",
    "backend/nexus_runtime_snapshot_v18_1/routes.py",
    "backend/nexus_public_entitlements_v18_2/routes.py",
    "backend/nexus_paid_beta_retention/routes.py",
    "backend/nexus_product_analytics/routes.py",
    "backend/nexus_public_auth/routes.py",
    "backend/nexus_closed_beta/routes.py",
    "backend/nexus_customer_validation_concierge/routes.py",
    "backend/nexus_research/sim_routes.py",
    "backend/nexus_research/paper_routes.py",
    "backend/api/nexus_market_data_routes.py",
    "backend/api/founder_private_routes.py",
    "backend/api/operator_ui_routes.py",
    "backend/nexus_research/demo_autonomous/api_routes.py",
    "backend/nexus_global_shadow/api_routes.py",
    "backend/nexus_adaptive_policy/api_routes.py",
    "backend/nexus_real_shadow/api_routes.py",
    "backend/nexus_demo_execution/api_routes.py",
    "backend/nexus_demo_execution/internal_market_routes.py",
    "backend/nexus_control_plane/api_routes.py",
]


def _unparse(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else repr(node.value)
    return ast.unparse(node)


def _methods(call: ast.Call, attr: str) -> list[str]:
    if attr in {"get", "post", "put", "patch", "delete"}:
        return [attr.upper()]
    for kw in call.keywords:
        if kw.arg == "methods":
            val = kw.value
            if isinstance(val, (ast.List, ast.Tuple, ast.Set)):
                return [
                    str(elt.value).upper() if isinstance(elt, ast.Constant) else _unparse(elt)
                    for elt in val.elts
                ]
            if isinstance(val, ast.Constant):
                return [str(val.value).upper()]
            return [_unparse(val)]
    return ["GET"]


def _discover_routes() -> list[dict[str, Any]]:
    route_attrs = {"route", "get", "post", "put", "patch", "delete"}
    rows: list[dict[str, Any]] = []
    for rel in RUN_REGISTERED_ROUTE_FILES:
        path = ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for deco in node.decorator_list:
                    if (
                        isinstance(deco, ast.Call)
                        and isinstance(deco.func, ast.Attribute)
                        and deco.func.attr in route_attrs
                    ):
                        rows.append(
                            {
                                "file": rel,
                                "line": node.lineno,
                                "route": _unparse(deco.args[0]) if deco.args else "<no-path>",
                                "methods": _methods(deco, deco.func.attr),
                            }
                        )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_url_rule":
                rows.append(
                    {
                        "file": rel,
                        "line": node.lineno,
                        "route": _unparse(node.args[0]) if node.args else "<no-path>",
                        "methods": _methods(node, "route"),
                    }
                )
    unique: list[dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = (row["file"], row["line"], row["route"], tuple(row["methods"]))
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def _testable_route(route: str, index: int) -> str:
    if route.startswith("/"):
        return route.replace("<notification_id>", "notification_id").replace("<product_id>", "product_id")
    return f"/__dynamic_validation_route_{index}"


def _app_with_inventory_routes() -> Flask:
    app = Flask(__name__)
    install_validation_public_guard(app)

    def ok():
        return jsonify({"ok": True})

    for idx, row in enumerate(_discover_routes()):
        app.add_url_rule(
            _testable_route(str(row["route"]), idx),
            endpoint=f"inventory_{idx}",
            view_func=ok,
            methods=list(row["methods"]),
        )
    return app


def _enable_guard(monkeypatch):
    monkeypatch.setenv(GUARD_ENV, "true")
    monkeypatch.setenv(CONTROL_TOKEN_ENV, CONTROL_TOKEN)


def _auth_header(token: str = CONTROL_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_route_inventory_all_state_changing_routes_require_control_auth(monkeypatch):
    _enable_guard(monkeypatch)
    app = _app_with_inventory_routes()
    client = app.test_client()
    state_rules = [
        rule
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static" and rule.methods and rule.methods.intersection(STATE_METHODS)
    ]
    state_method_count = sum(len(rule.methods.intersection(STATE_METHODS)) for rule in state_rules)
    assert state_method_count == 91

    for rule in state_rules:
        path = str(rule.rule)
        for method in sorted(rule.methods.intersection(STATE_METHODS)):
            resp = client.open(path, method=method)
            assert resp.status_code == 403, f"{method} {path} was not guarded"
            body = resp.get_json()
            assert body["error"] == "VALIDATION_PUBLIC_GUARD_DENIED"


def test_public_get_allowlist_is_exact_and_unknown_get_denies(monkeypatch):
    _enable_guard(monkeypatch)
    app = _app_with_inventory_routes()
    client = app.test_client()

    for path in PUBLIC_GET_ALLOWLIST:
        resp = client.get(path)
        assert resp.status_code == 200, path
        head = client.head(path)
        assert head.status_code == 200, path

    denied = client.get("/api/nexus/not-on-public-allowlist")
    assert denied.status_code == 403
    assert denied.get_json()["reason"] == "malformed_authorization"


def test_control_auth_rejects_missing_wrong_malformed_and_query_token(monkeypatch, caplog):
    _enable_guard(monkeypatch)
    app = Flask(__name__)
    install_validation_public_guard(app)

    @app.post("/protected")
    def protected():
        return jsonify({"ok": True})

    client = app.test_client()
    caplog.set_level(logging.WARNING, logger="backend.security.validation_public_guard")

    assert client.post("/protected").status_code == 403
    assert client.post("/protected", headers=_auth_header("wrong-token")).status_code == 403
    assert client.post("/protected", headers={"Authorization": CONTROL_TOKEN}).status_code == 403
    assert client.post("/protected?token=not-allowed", headers=_auth_header()).status_code == 403

    allowed = client.post("/protected", headers=_auth_header())
    assert allowed.status_code == 200
    assert CONTROL_TOKEN not in "\n".join(record.getMessage() for record in caplog.records)
    for resp in (
        client.post("/protected"),
        client.post("/protected", headers=_auth_header("wrong-token")),
        client.post("/protected", headers={"Authorization": CONTROL_TOKEN}),
    ):
        assert CONTROL_TOKEN not in resp.get_data(as_text=True)


def test_missing_server_control_token_fails_closed(monkeypatch):
    monkeypatch.setenv(GUARD_ENV, "true")
    monkeypatch.delenv(CONTROL_TOKEN_ENV, raising=False)
    app = Flask(__name__)
    install_validation_public_guard(app)

    @app.post("/protected")
    def protected():
        return jsonify({"ok": True})

    resp = app.test_client().post("/protected", headers=_auth_header())
    assert resp.status_code == 403
    assert resp.get_json()["reason"] == "control_token_not_configured"


def test_valid_control_auth_does_not_replace_founder_gate(monkeypatch, tmp_path):
    _enable_guard(monkeypatch)
    monkeypatch.setenv("NEXUS_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
    for key in (
        "FOUNDER_GATE",
        "FOUNDER_6H_APPROVED",
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2",
        "DEMO_AUTONOMOUS_ENABLED",
        "EXCHANGE_WRITE",
        "MAINNET",
        "REAL_MONEY",
    ):
        monkeypatch.setenv(key, "false")

    app = Flask(__name__)
    install_validation_public_guard(app)
    from backend.nexus_demo_execution.api_routes import register_demo_execution_routes

    register_demo_execution_routes(app)
    resp = app.test_client().post("/api/nexus/demo-execution/bounded-6h/start", headers=_auth_header())
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert CONTROL_TOKEN not in text
    body = resp.get_json()
    start = body["bounded_6h_start"]
    assert start["ok"] is False
    assert start["reason"] in {"founder_gate_mismatch", "founder_not_approved"}
    assert body["exchange_write"] is False
    assert body["mainnet"] is False
    assert body["real_money"] is False
    assert os.environ["EXCHANGE_WRITE"] == "false"
    assert os.environ["MAINNET"] == "false"
    assert os.environ["REAL_MONEY"] == "false"


def test_non_validation_mode_is_not_affected_without_guard_flag(monkeypatch):
    monkeypatch.delenv(GUARD_ENV, raising=False)
    monkeypatch.delenv(CONTROL_TOKEN_ENV, raising=False)
    monkeypatch.setenv("SERVICE_NAME", "nexus-member-preview-v18-2-1")
    app = Flask(__name__)
    install_validation_public_guard(app)

    @app.post("/member-preview-mutation")
    def member_preview_mutation():
        return jsonify({"ok": True, "service": "member-preview"})

    resp = app.test_client().post("/member-preview-mutation")
    assert resp.status_code == 200
