"""Corporate Market Intelligence — static SPA server (CORPORATE-1).

Serves ONLY the Corporate frontend build artifact (frontend/dist/corporate).
It has NO backend, NO trading runtime, NO Founder runtime, and NO secrets. The
Corporate site talks to the public Core/Corporate API over HTTPS; only a public
API origin (VITE_NEXUS_API_ORIGIN) is baked into the static build.

Artifact ROOT = dist/corporate (contains index.html + assets/). SPA fallback:
any non-file path resolves to index.html.
Config: NEXUS_CORPORATE_DIST (default /app/dist/corporate), PORT (default 8080).
"""
from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def artifact_root() -> Path:
    return Path(os.environ.get("NEXUS_CORPORATE_DIST", "/app/dist/corporate")).resolve()


def assert_valid_artifact_root(root: Path) -> None:
    if not (root / "index.html").is_file():
        raise SystemExit(
            f"CORPORATE_ARTIFACT_INVALID: {root/'index.html'} missing. NEXUS_CORPORATE_DIST must "
            "point at the Corporate artifact ROOT (dist/corporate), not the parent dist/."
        )


class CorporateSpaHandler(SimpleHTTPRequestHandler):
    root: Path = artifact_root()

    def translate_path(self, path: str) -> str:
        raw = path.split("?", 1)[0].split("#", 1)[0]
        candidate = (self.root / raw.lstrip("/")).resolve()
        if candidate.is_file() and (self.root == candidate or self.root in candidate.parents):
            return str(candidate)
        return str(self.root / "index.html")

    def end_headers(self) -> None:
        cache = "no-cache" if self.path in {"/", "/index.html"} else "public, max-age=604800, immutable"
        self.send_header("Cache-Control", cache)
        super().end_headers()

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    root = artifact_root()
    assert_valid_artifact_root(root)
    CorporateSpaHandler.root = root
    port = int(os.environ.get("PORT", "8080"))
    print(f"CORPORATE_SPA_SERVING root={root} port={port}")
    ThreadingHTTPServer(("0.0.0.0", port), CorporateSpaHandler).serve_forever()


if __name__ == "__main__":
    main()
