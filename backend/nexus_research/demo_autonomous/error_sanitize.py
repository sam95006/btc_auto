"""Sanitize controller/observer exceptions for API + bounded logs (no secrets)."""
from __future__ import annotations

import re
import traceback
import uuid
from typing import Any

_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|api[_-]?secret|secret|password|token|authorization|bearer|"
    r"private[_-]?key|access[_-]?token|refresh[_-]?token|mnemonic|seed)\s*[:=]\s*\S+"
)
_HEX_LONG = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_MAX_MSG = 240
_MAX_TB_CHARS = 1800
_MAX_TB_FRAMES = 8


def sanitize_text(text: str, *, max_len: int = _MAX_MSG) -> str:
    cleaned = _SECRET_RE.sub(r"\1=***", str(text or ""))
    cleaned = _HEX_LONG.sub("***", cleaned)
    cleaned = cleaned.replace("\n", " ").strip()
    if len(cleaned) > max_len:
        return cleaned[: max_len - 3] + "..."
    return cleaned


def build_structured_error(
    exc: BaseException,
    *,
    stage: str,
    cycle_id: str,
    started_at_ms: int,
    failed_at_ms: int,
    last_successful_stage: str | None,
    consecutive_failure_count: int,
    retryable: bool = True,
) -> dict[str, Any]:
    try:
        frames = traceback.format_exception(exc)  # py3.10+
    except Exception:
        tb = getattr(exc, "__traceback__", None)
        frames = traceback.format_exception(type(exc), exc, tb)
    tb_raw = "".join(frames[-_MAX_TB_FRAMES:])
    tb_san = sanitize_text(tb_raw, max_len=_MAX_TB_CHARS)
    return {
        "error_id": str(uuid.uuid4()),
        "error_type": type(exc).__name__,
        "error_message_sanitized": sanitize_text(str(exc)),
        "traceback_sanitized": tb_san,
        "stage": stage,
        "cycle_id": cycle_id,
        "correlation_id": cycle_id,
        "started_at": started_at_ms,
        "failed_at": failed_at_ms,
        "elapsed_ms": max(0, failed_at_ms - started_at_ms),
        "last_successful_stage": last_successful_stage,
        "retryable": retryable,
        "consecutive_failure_count": consecutive_failure_count,
        # Backward-compatible short field (never type-only alone in new code paths).
        "error": type(exc).__name__,
    }
