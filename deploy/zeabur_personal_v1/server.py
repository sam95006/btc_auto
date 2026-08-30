"""Personal Market Intelligence — static SPA server (PERSONAL-2).

This serves ONLY the Personal frontend build artifact (a React Router SPA).
It has NO backend, NO trading runtime, NO ResearchAutonomyService, NO Bybit
runner, and NO Founder runtime. The Personal web surface and the private
trading runtime are different products served by different processes.

Artifact contract:
- The served root is the Personal artifact ROOT itself — the directory that
  DIRECTLY contains `index.html` and `assets/` (i.e. `frontend/dist/personal`),
  NOT the parent `dist/`. Pointing this at the parent `dist/` is the known
  root-404 failure and is rejected loudly at startup.
- SPA fallback: any path that is not a real file resolves to `index.html`, so a
  direct browser refresh of `/app`, `/app/intelligence`, `/app/membership`,
  etc. returns the SPA (200), never a 404.

Configuration (env):
- NEXUS_PERSONAL_DIST : artifact root directory (default: /app/dist/personal)
- PORT                : listen port (default: 8080)
"""

from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def artifact_root() -> Path:
    return Path(os.environ.get("NEXUS_PERSONAL_DIST", "/app/dist/personal")).resolve()


def assert_valid_artifact_root(root: Path) -> None:
    """Fail closed if the configured root is not a real Personal artifact root."""
    index = root / "index.html"
    if not index.is_file():
        raise SystemExit(
            f"PERSONAL_ARTIFACT_INVALID: {index} missing. "
            "NEXUS_PERSONAL_DIST must point at the Personal artifact ROOT "
            "(the directory containing index.html), e.g. frontend/dist/personal, "
            "not the parent dist/."
        )


class PersonalSpaHandler(SimpleHTTPRequestHandler):
    root: Path = artifact_root()

    def translate_path(self, path: str) -> str:
        # Strip query/fragment and normalize, then confine to the artifact root.
        raw = path.split("?", 1)[0].split("#", 1)[0]
        candidate = (self.root / raw.lstrip("/")).resolve()
        if candidate.is_file() and (self.root == candidate or self.root in candidate.parents):
            return str(candidate)
        # SPA fallback — unknown route resolves to the app shell.
        return str(self.root / "index.html")

    def end_headers(self) -> None:
        cache = "no-cache" if self.path in {"/", "/index.html"} else "public, max-age=604800, immutable"
        self.send_header("Cache-Control", cache)
        super().end_headers()

    def log_message(self, *args) -> None:  # keep container logs quiet
        pass


def main() -> None:
    root = artifact_root()
    assert_valid_artifact_root(root)
    PersonalSpaHandler.root = root
    port = int(os.environ.get("PORT", "8080"))
    print(f"PERSONAL_SPA_SERVING root={root} port={port}")
    ThreadingHTTPServer(("0.0.0.0", port), PersonalSpaHandler).serve_forever()


if __name__ == "__main__":
    main()
