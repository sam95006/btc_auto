"""Corporate static-server single-build consistency.

Regression for the two-builds bug: SPA-fallback deep-link routes used to be served
`index.html` with the immutable asset cache policy, which pinned a stale build in
the browser after a redeploy. index.html (root AND any SPA fallback) must be
no-cache; only content-hashed /assets/ files may be immutable.
"""
from __future__ import annotations

import importlib.util
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

SERVER = Path("deploy/zeabur_corporate_v1/server.py")


def _load_server():
    spec = importlib.util.spec_from_file_location("corp_server", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(
        '<!doctype html><html><head>'
        '<script src="/assets/corporate-ABC123.js"></script>'
        '<link href="/assets/corporate-XYZ.css" rel="stylesheet"></head>'
        '<body>NEXUS</body></html>',
        encoding="utf-8",
    )
    (root / "assets" / "corporate-ABC123.js").write_text("console.log(1)", encoding="utf-8")
    return root


def _serve(mod, root: Path):
    mod.CorporateSpaHandler.root = root
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), mod.CorporateSpaHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _cache_control(port: int, path: str) -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as resp:
        return resp.headers.get("Cache-Control", "")


def test_index_and_spa_fallback_are_no_cache_assets_immutable(tmp_path):
    mod = _load_server()
    root = _make_dist(tmp_path)
    httpd, port = _serve(mod, root)
    try:
        # index.html at root AND any SPA-fallback deep link must revalidate.
        assert _cache_control(port, "/") == "no-cache"
        assert _cache_control(port, "/index.html") == "no-cache"
        assert _cache_control(port, "/products") == "no-cache"        # the bug fix
        assert _cache_control(port, "/about") == "no-cache"
        assert _cache_control(port, "/build-info") == "no-cache"
        # Content-hashed assets may cache immutably.
        cc = _cache_control(port, "/assets/corporate-ABC123.js")
        assert "immutable" in cc and "max-age=" in cc
    finally:
        httpd.shutdown()


def test_build_info_reports_one_build_asset_identity(tmp_path):
    mod = _load_server()
    root = _make_dist(tmp_path)
    import json
    body = json.loads(mod._build_info(root))
    # The build marker ties the served index.html to its exact hashed assets.
    assert "/assets/corporate-ABC123.js" in body["index_assets"]
    assert "/assets/corporate-XYZ.css" in body["index_assets"]
    assert body["service"] == "nexus-corporate-staging"
