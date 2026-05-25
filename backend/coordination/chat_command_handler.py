from __future__ import annotations

import re
from typing import Optional

# 繁中關鍵字（去空白後比對）
_FLATTEN_ZH = (
    "整體平倉",
    "全部平倉",
    "全平",
    "全部清倉",
    "一鍵平倉",
    "平掉所有倉位",
    "平倉所有",
    "清掉所有倉位",
)

_FLATTEN_EN = (
    "close all",
    "flatten all",
    "close all positions",
    "flatten all positions",
)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip())


def detect_chat_command(message: str) -> Optional[str]:
    """Return command id when player message is an operational chat command."""
    raw = str(message or "").strip()
    if not raw:
        return None

    compact = _compact(raw)
    lower = raw.lower().strip()

    for phrase in _FLATTEN_ZH:
        if compact == phrase or phrase in compact:
            return "flatten_all"

    for phrase in _FLATTEN_EN:
        if lower == phrase or lower.startswith(phrase):
            return "flatten_all"

    return None


def format_flatten_reply(result: dict) -> str:
    closed = list(result.get("closed") or [])
    failed = list(result.get("failed") or [])
    skipped = list(result.get("skipped") or [])

    if not closed and not failed and not skipped:
        return "已執行整體平倉指令：目前沒有偵測到 U 本位合約持倉。"

    parts = [f"整體平倉完成：成功 {len(closed)} 筆"]
    if closed:
        detail = "、".join(
            f"{item.get('symbol', '?')} {item.get('side', '')} pnl={float(item.get('pnl', 0) or 0):.2f}"
            for item in closed[:6]
        )
        parts.append(f"（{detail}）")
    if failed:
        parts.append(f"；失敗 {len(failed)} 筆")
        err = failed[0].get("error") or failed[0].get("symbol")
        if err:
            parts.append(f"（例：{err}）")
    if skipped:
        parts.append(f"；略過 {len(skipped)} 筆")
    sync_warning = result.get("sync_warning")
    if sync_warning:
        parts.append(f"；同步警告：{sync_warning}")
    return "".join(parts)
