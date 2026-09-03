"""Corporate Market Intelligence — static SPA server (CORPORATE-1 / hardened in CORPORATE-2).

Serves ONLY the Corporate frontend build artifact (frontend/dist/corporate).
It has NO backend, NO trading runtime, NO Founder runtime, and NO secrets. The
Corporate site talks to the public Core/Corporate API over HTTPS; only a public
API origin (VITE_NEXUS_API_ORIGIN) is baked into the static build.

CORPORATE-2 adds a strict security-header layer (CSP, frame-ancestors, nosniff,
Referrer-Policy, Permissions-Policy, HSTS) and serves robots.txt + sitemap.xml.
The CSP is XSS-defence-in-depth; it does NOT claim to replace the HttpOnly
session cookie boundary — that remains the primary session-secret boundary.

Artifact ROOT = dist/corporate (contains index.html + assets/). SPA fallback:
any non-file path resolves to index.html.
Config: NEXUS_CORPORATE_DIST (default /app/dist/corporate), PORT (default 8080),
NEXUS_CORPORATE_API_ORIGIN (connect-src allow-list; default staging API).
"""
from __future__ import annotations

import json
import os
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API_ORIGIN = os.environ.get("NEXUS_CORPORATE_API_ORIGIN", "https://nexus-api-staging.zeabur.app").rstrip("/")
SITE_ORIGIN = os.environ.get("NEXUS_CORPORATE_SITE_ORIGIN", "https://nexus-corporate-staging.zeabur.app").rstrip("/")

# Strict, self-contained CSP. No external hosts except the public API for fetch.
# 'unsafe-inline' is required for style only (React inline styles + CSS custom
# properties that drive the cinematic animation); scripts stay 'self' with no
# inline execution. Trusted Types is intentionally NOT enforced here — enforcing
# it would break React/DOM rendering; it is a documented CORPORATE-3 follow-up.
CSP = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    f"connect-src 'self' {API_ORIGIN}; "
    "worker-src 'self'; "
    "manifest-src 'self'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

ROBOTS = "User-agent: *\nAllow: /\nSitemap: {site}/sitemap.xml\n"
SITEMAP_PATHS = ["/", "/products", "/personal", "/enterprise", "/pricing", "/security", "/about", "/contact"]


def artifact_root() -> Path:
    return Path(os.environ.get("NEXUS_CORPORATE_DIST", "/app/dist/corporate")).resolve()


def assert_valid_artifact_root(root: Path) -> None:
    if not (root / "index.html").is_file():
        raise SystemExit(
            f"CORPORATE_ARTIFACT_INVALID: {root/'index.html'} missing. NEXUS_CORPORATE_DIST must "
            "point at the Corporate artifact ROOT (dist/corporate), not the parent dist/."
        )


def _build_info(root: Path) -> str:
    """Build-identity marker (a JSON endpoint, NOT shown on any customer page):
    the content-hashed asset filenames the deployed index.html references, proving
    the served HTML and the loaded JS/CSS bundle belong to ONE build, plus an
    optional source SHA. No secrets."""
    try:
        html = (root / "index.html").read_text(encoding="utf-8", errors="replace")
    except Exception:
        html = ""
    assets = sorted(set(re.findall(r"/assets/[A-Za-z0-9_.-]+\.(?:js|css)", html)))
    return json.dumps({
        "service": "nexus-corporate-staging",
        "index_assets": assets,
        "build_sha": os.environ.get("NEXUS_CORPORATE_BUILD_SHA", "unset"),
    })


def _sitemap() -> str:
    urls = "".join(f"  <url><loc>{SITE_ORIGIN}{p}</loc></url>\n" for p in SITEMAP_PATHS)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}</urlset>\n")


class CorporateSpaHandler(SimpleHTTPRequestHandler):
    root: Path = artifact_root()

    def _send_text(self, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()  # security headers + Cache-Control are added here
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        # Default every response to revalidate; only real content-hashed asset
        # files opt into immutable caching (set in translate_path).
        self._cache_immutable = False
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path == "/robots.txt":
            return self._send_text(ROBOTS.format(site=SITE_ORIGIN), "text/plain; charset=utf-8")
        if path == "/sitemap.xml":
            return self._send_text(_sitemap(), "application/xml; charset=utf-8")
        if path == "/build-info":
            return self._send_text(_build_info(self.root), "application/json; charset=utf-8")
        return super().do_GET()

    def translate_path(self, path: str) -> str:
        raw = path.split("?", 1)[0].split("#", 1)[0]
        candidate = (self.root / raw.lstrip("/")).resolve()
        if candidate.is_file() and (self.root == candidate or self.root in candidate.parents):
            # Only real files under /assets/ are content-hashed by Vite, so only
            # they are safe to cache immutably. Everything else (index.html,
            # favicon, etc.) must revalidate.
            assets_dir = (self.root / "assets").resolve()
            if assets_dir == candidate.parent or assets_dir in candidate.parents:
                self._cache_immutable = True
            return str(candidate)
        # SPA fallback for ANY unmatched route -> index.html, which stays no-cache
        # so a deep-link navigation can never pin a stale build in the browser.
        return str(self.root / "index.html")

    def end_headers(self) -> None:
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        # Content-hashed assets: long immutable. index.html / SPA fallback / robots
        # / sitemap / build-info: never cached stale (revalidate every deploy).
        cache = (
            "public, max-age=31536000, immutable"
            if getattr(self, "_cache_immutable", False)
            else "no-cache"
        )
        self.send_header("Cache-Control", cache)
        super().end_headers()

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    root = artifact_root()
    assert_valid_artifact_root(root)
    CorporateSpaHandler.root = root
    port = int(os.environ.get("PORT", "8080"))
    print(f"CORPORATE_SPA_SERVING root={root} port={port} csp=on")
    ThreadingHTTPServer(("0.0.0.0", port), CorporateSpaHandler).serve_forever()


if __name__ == "__main__":
    main()
