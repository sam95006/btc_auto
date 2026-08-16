"""Minimal SPA-only preview server. It has no backend or runtime binding."""

from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DIST = Path("/app/dist")


class PreviewHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        candidate = (DIST / path.lstrip("/")).resolve()
        if candidate.is_file() and DIST in candidate.parents:
            return str(candidate)
        return str(DIST / "index.html")

    def end_headers(self) -> None:
        self.send_header(
            "Cache-Control",
            "no-cache" if self.path in {"/", "/index.html"} else "public, max-age=604800, immutable",
        )
        super().end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), PreviewHandler).serve_forever()
