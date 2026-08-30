"""Personal deploy artifact + SPA static-server smoke tests (PERSONAL-2).

Proves the Personal frontend artifact contract and the static server behavior
that fixes the root-404: serve the artifact ROOT (dist/personal) with SPA
fallback. The HTTP behavior is proven hermetically against a synthetic artifact
(no build needed); the real built artifact is additionally validated when
present.
"""
from __future__ import annotations

import importlib.util
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SERVER_PY = REPO / "deploy" / "zeabur_personal_v1" / "server.py"
REAL_ARTIFACT = REPO / "frontend" / "dist" / "personal"


def _load_server():
    spec = importlib.util.spec_from_file_location("personal_spa_server", SERVER_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _synthetic_artifact(tmp_path: Path) -> Path:
    root = tmp_path / "personal"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>Personal</title><div id=root></div>", encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log('personal');", encoding="utf-8")
    return root


def _serve(root: Path):
    mod = _load_server()
    mod.PersonalSpaHandler.root = root.resolve()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), mod.PersonalSpaHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, httpd.server_address[1]


def _get(port: int, path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


# --------------------------------------------------------------------------
# Static-server behavior (hermetic)
# --------------------------------------------------------------------------

def test_artifact_root_serves_index_and_assets(tmp_path) -> None:
    root = _synthetic_artifact(tmp_path)
    httpd, port = _serve(root)
    try:
        status, body = _get(port, "/")
        assert status == 200 and "Personal" in body            # GET / success
        assert _get(port, "/assets/app.js")[0] == 200           # asset success
    finally:
        httpd.shutdown()


def test_spa_direct_route_falls_back_to_index(tmp_path) -> None:
    root = _synthetic_artifact(tmp_path)
    httpd, port = _serve(root)
    try:
        for route in ("/app", "/app/intelligence", "/app/membership"):
            status, body = _get(port, route)
            assert status == 200 and "id=root" in body          # SPA fallback, not 404
    finally:
        httpd.shutdown()


def test_parent_dist_wrong_root_reproduces_missing_index(tmp_path) -> None:
    # Reproduce the failure: point the server at the PARENT dist (no index.html).
    parent = tmp_path / "dist"
    (parent / "personal").mkdir(parents=True)
    (parent / "personal" / "index.html").write_text("<title>Personal</title>", encoding="utf-8")
    mod = _load_server()
    with pytest.raises(SystemExit):
        mod.assert_valid_artifact_root(parent)  # parent has no index.html -> fail closed
    # The correct artifact root passes.
    mod.assert_valid_artifact_root(parent / "personal")


# --------------------------------------------------------------------------
# Real built artifact (validated when present)
# --------------------------------------------------------------------------

def test_real_personal_artifact_has_index() -> None:
    if not (REAL_ARTIFACT / "index.html").is_file():
        pytest.skip("dist/personal not built in this environment")
    assert (REAL_ARTIFACT / "assets").is_dir()


def test_real_personal_artifact_excludes_founder_and_trading() -> None:
    index = REAL_ARTIFACT / "index.html"
    if not index.is_file():
        pytest.skip("dist/personal not built in this environment")
    blob = ""
    for js in (REAL_ARTIFACT / "assets").glob("*.js"):
        blob += js.read_text(encoding="utf-8", errors="ignore").lower()
    for banned in (
        "founderoperator",
        "founderruntime",
        "founderdiagnostics",
        "orderexecutor",
        "/routing-edit",
        "arm-control",
    ):
        assert banned not in blob, banned
