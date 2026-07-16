"""Cache-Control policy for operator UI HTML shell vs hashed Vite assets."""
from __future__ import annotations

import re

from flask import Response

_HASHED_ASSET_RE = re.compile(r"^/assets/index-[^/]+\.(?:js|css)$", re.I)


def is_operator_ui_html_path(path: str, spa_prefixes: tuple[str, ...]) -> bool:
    if path in {"/", "/index.html"}:
        return True
    return any(path == f"/{prefix}" or path.startswith(f"/{prefix}/") for prefix in spa_prefixes)


def apply_operator_ui_cache_headers(
    response: Response,
    path: str,
    *,
    spa_prefixes: tuple[str, ...],
) -> Response:
    if _HASHED_ASSET_RE.match(path):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
    if is_operator_ui_html_path(path, spa_prefixes):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response
