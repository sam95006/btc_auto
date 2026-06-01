"""Make nested payloads safe for JSON responses (strip illegal control chars)."""

from __future__ import annotations

import re
from typing import Any

# JSON cannot contain raw U+0000–U+001F except tab/LF/CR.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, str):
        return _CONTROL_RE.sub("", value)
    if isinstance(value, bytes):
        try:
            return _CONTROL_RE.sub("", value.decode("utf-8", errors="replace"))
        except Exception:
            return ""
    return value
