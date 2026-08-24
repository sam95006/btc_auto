from __future__ import annotations

import ast
import importlib
import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
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
PRODUCTION_IMPORT_MODULES = ("app", "run")
PRODUCTION_SAFE_ENV = {
    "NEXUS_WEB_ONLY": "true",
    "NEXUS_EMBEDDED_WORKER": "false",
    "NEXUS_LEGACY_WORKER_DISABLED": "true",
    "MAINNET": "false",
    "REAL_MONEY": "false",
    "EXCHANGE_WRITE": "false",
    "DEMO_AUTONOMOUS_ENABLED": "false",
    "NEXUS_AUTONOMOUS_DEMO_SCANNER": "false",
    "NEXUS_ZEABUR_CLEAN_OBSERVER": "false",
    "NEXUS_VALIDATION_PUBLIC_GUARD": "true",
    "NEXUS_ACCOUNT_FRESH": "false",
}
PRODUCTION_SECRET_ENV_KEYS = (
    "BYBIT_DEMO_API_KEY",
    "BYBIT_DEMO_API_SECRET",
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "BYBIT_M0_API_KEY",
    "BYBIT_M0_API_SECRET",
    "NEXUS_BYBIT_API_KEY",
    "NEXUS_BYBIT_API_SECRET",
)

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


def _production_route_test_path(rule: Any) -> str:
    def repl(match: re.Match[str]) -> str:
        spec = match.group(1)
        converter, _, name = spec.partition(":")
        if not name:
            name = converter
            converter = ""
        name = name.lower()
        converter = converter.lower()
        if converter.startswith("int") or name.endswith("_id") or name == "id":
            return "1"
        if converter.startswith("float"):
            return "1.0"
        if converter.startswith("uuid"):
            return "00000000-0000-0000-0000-000000000001"
        if converter.startswith("path") or name in {"filename", "path"}:
            return "sample.txt"
        if "symbol" in name:
            return "BTCUSDT"
        if "stream" in name:
            return "cost_gates"
        if "product" in name:
            return "product_id"
        if "notification" in name:
            return "notification_id"
        return "value"

    return re.sub(r"<([^<>]+)>", repl, str(rule.rule))


def _state_method_pairs(app: Flask) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        for method in sorted((rule.methods or set()).intersection(STATE_METHODS)):
            pairs.append((method, _production_route_test_path(rule)))
    return pairs


def _actual_public_get_paths(app: Flask) -> set[str]:
    return {
        str(rule.rule)
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static" and "GET" in (rule.methods or set()) and str(rule.rule) in PUBLIC_GET_ALLOWLIST
    }


@pytest.fixture()
def production_app_security_harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "network_calls": 0,
        "exchange_write_calls": 0,
        "background_trading_threads": 0,
        "autonomous_started": False,
        "blocked_thread_names": [],
    }

    for key, value in PRODUCTION_SAFE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv(CONTROL_TOKEN_ENV, CONTROL_TOKEN)
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NEXUS_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("SERVICE_NAME", "nexus-bybit-demo-learning-validation")
    for key in PRODUCTION_SECRET_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    def blocked_network(*_args: Any, **_kwargs: Any) -> Any:
        stats["network_calls"] += 1
        raise AssertionError("external network disabled for production url_map test")

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", blocked_network)
    try:
        import requests

        monkeypatch.setattr(requests.sessions.Session, "request", blocked_network)
    except Exception:  # noqa: BLE001 - requests is optional for this route-map proof.
        pass

    def no_exchange_write(*_args: Any, **_kwargs: Any) -> Any:
        stats["exchange_write_calls"] += 1
        raise AssertionError("exchange write disabled for production url_map test")

    demo_write_client = importlib.import_module("backend.nexus_demo_execution.demo_write_client")
    monkeypatch.setattr(demo_write_client, "urlopen", blocked_network)
    monkeypatch.setattr(demo_write_client.DemoWriteClient, "_post", no_exchange_write)
    demo_transport = importlib.import_module("backend.nexus_research.demo_autonomous.write_transport")
    monkeypatch.setattr(demo_transport, "urlopen", blocked_network)
    monkeypatch.setattr(demo_transport.DemoWriteTransport, "post", no_exchange_write)
    monkeypatch.setattr(demo_transport.DemoWriteTransport, "_live_post", no_exchange_write)

    demo_api_routes = importlib.import_module("backend.nexus_demo_execution.api_routes")
    original_start_bounded_6h = demo_api_routes.DemoExecutionApiState.start_bounded_6h
    original_bounded_6h_status = demo_api_routes.DemoExecutionApiState.bounded_6h_status
    bounded_6h_session = importlib.import_module("backend.nexus_demo_execution.bounded_6h_session")
    original_bounded_6h_session_cls = bounded_6h_session.Bounded6HSession
    bounded_bootstrap = importlib.import_module("backend.nexus_bounded_runtime.bootstrap")
    original_certified_bounded_runtime_active = bounded_bootstrap.CERTIFIED_BOUNDED_RUNTIME_ACTIVE

    federation_client = importlib.import_module("backend.nexus_control_plane.federation_client")
    monkeypatch.setattr(federation_client, "urlopen", blocked_network)
    monkeypatch.setattr(
        federation_client.FederationClient,
        "get_json",
        lambda *_args, **_kwargs: {"ok": False, "data_status": "TEST_DISABLED", "payload": None},
    )

    runtime_bootstrap = importlib.import_module("backend.nexus_research.demo_autonomous.runtime_bootstrap")
    monkeypatch.setattr(
        runtime_bootstrap,
        "ensure_autonomous_runtime",
        lambda: {"bootstrapped": True, "scannerStarted": False, "scannerRunning": False},
    )
    validation_observer = importlib.import_module("backend.nexus_research.demo_autonomous.validation_observer")
    monkeypatch.setattr(
        validation_observer,
        "ensure_validation_observer",
        lambda *_, **__: {"enabled": False, "started": False, "running": False},
    )

    scanner_service = importlib.import_module("backend.market.scanner.scanner_service")

    class NoopMarketScanner:
        def status(self) -> dict[str, Any]:
            return {"ok": True, "running": False, "source": "test_noop"}

        def snapshot(self) -> dict[str, Any]:
            return {"ok": True, "candidates": [], "source": "test_noop"}

    monkeypatch.setattr(scanner_service, "get_market_scanner", lambda: NoopMarketScanner())
    monkeypatch.setattr(scanner_service.MarketScannerService, "start", lambda *_args, **_kwargs: None)

    try:
        demo_controller = importlib.import_module("backend.nexus_research.demo_autonomous.controller")

        def blocked_autonomous_start(*_args: Any, **_kwargs: Any) -> Any:
            stats["autonomous_started"] = True
            raise AssertionError("autonomous controller start disabled for production url_map test")

        monkeypatch.setattr(demo_controller.AutonomousDemoController, "start", blocked_autonomous_start)
    except Exception:  # noqa: BLE001
        pass

    original_thread_start = threading.Thread.start
    background_markers = (
        "nexus-research-bootstrap",
        "nexus-market-scanner",
        "autonomous-demo",
        "zeabur-clean-observer",
        "nexus-embedded-worker",
        "founder-smoke",
        "auto-cycle",
    )

    def guarded_thread_start(thread: threading.Thread, *args: Any, **kwargs: Any) -> Any:
        name = str(getattr(thread, "name", ""))
        if any(marker in name for marker in background_markers):
            stats["blocked_thread_names"].append(name)
            raise RuntimeError(f"blocked background thread start: {name}")
        return original_thread_start(thread, *args, **kwargs)

    monkeypatch.setattr(threading.Thread, "start", guarded_thread_start)

    monkeypatch.setattr(demo_api_routes, "_STATE", None, raising=False)
    for module_name in PRODUCTION_IMPORT_MODULES:
        sys.modules.pop(module_name, None)

    production_module = importlib.import_module("app")
    production_app = production_module.app
    stats["state_changing_route_count"] = len(_state_method_pairs(production_app))
    stats["public_get_allowlist_count"] = len(_actual_public_get_paths(production_app))
    try:
        yield {"app": production_app, "stats": stats}
    finally:
        demo_api_routes.DemoExecutionApiState.start_bounded_6h = original_start_bounded_6h
        demo_api_routes.DemoExecutionApiState.bounded_6h_status = original_bounded_6h_status
        demo_api_routes._STATE = None
        bounded_6h_session.Bounded6HSession = original_bounded_6h_session_cls
        bounded_bootstrap.CERTIFIED_BOUNDED_RUNTIME_ACTIVE = original_certified_bounded_runtime_active
        for module_name in PRODUCTION_IMPORT_MODULES:
            sys.modules.pop(module_name, None)


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


def test_actual_production_url_map_state_changing_routes_fail_closed(production_app_security_harness):
    app = production_app_security_harness["app"]
    stats = production_app_security_harness["stats"]
    client = app.test_client()
    pairs = _state_method_pairs(app)

    assert pairs
    assert len(pairs) == stats["state_changing_route_count"]

    for method, path in pairs:
        resp = client.open(path, method=method)
        assert resp.status_code == 403, f"{method} {path} was not guarded"
        body = resp.get_json()
        assert body["error"] == "VALIDATION_PUBLIC_GUARD_DENIED"

    assert stats["network_calls"] == 0
    assert stats["exchange_write_calls"] == 0
    assert stats["autonomous_started"] is False


def test_actual_production_url_map_public_get_allowlist_is_exact(production_app_security_harness):
    app = production_app_security_harness["app"]
    stats = production_app_security_harness["stats"]
    client = app.test_client()
    actual_allowlisted = _actual_public_get_paths(app)

    assert actual_allowlisted == PUBLIC_GET_ALLOWLIST
    assert stats["public_get_allowlist_count"] == 6

    for path in sorted(actual_allowlisted):
        resp = client.get(path)
        assert resp.status_code == 200, path
        head = client.head(path)
        assert head.status_code == 200, path

    account_fresh = client.get("/api/nexus/demo-execution/account?fresh=true")
    assert account_fresh.status_code == 200

    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static" or "GET" not in (rule.methods or set()):
            continue
        path = _production_route_test_path(rule)
        if path in PUBLIC_GET_ALLOWLIST:
            continue
        resp = client.get(path)
        assert resp.status_code == 403, f"GET {path} was unexpectedly public"
        body = resp.get_json()
        assert body["error"] == "VALIDATION_PUBLIC_GUARD_DENIED"

    assert stats["network_calls"] == 0
    assert stats["exchange_write_calls"] == 0
    assert stats["autonomous_started"] is False


def test_future_production_state_changing_route_defaults_to_deny(production_app_security_harness):
    app = production_app_security_harness["app"]
    client = app.test_client()

    @app.post("/api/nexus/future-state-changing-regression")
    def future_state_changing_regression():
        return jsonify({"ok": True})

    resp = client.post("/api/nexus/future-state-changing-regression")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "VALIDATION_PUBLIC_GUARD_DENIED"


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
