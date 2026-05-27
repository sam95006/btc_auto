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

_RESUME_ZH = (
    "恢復交易",
    "繼續交易",
    "解除暫停",
    "取消暫停",
    "開始交易",
    "恢復運行",
)

_RESUME_EN = (
    "resume trading",
    "resume trade",
    "unpause",
    "start trading",
)

_RESET_SANDBOX_ZH = (
    "清除冷卻",
    "清除標的冷卻",
    "重置測試",
    "測試模式",
    "重置沙盒",
    "清除學習冷卻",
)

_RESET_SANDBOX_EN = (
    "reset sandbox",
    "clear cooldown",
    "clear cooldowns",
    "testnet reset",
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

    for phrase in _RESUME_ZH:
        if compact == phrase or phrase in compact:
            return "resume_trading"

    for phrase in _RESUME_EN:
        if lower == phrase or lower.startswith(phrase):
            return "resume_trading"

    for phrase in _RESET_SANDBOX_ZH:
        if compact == phrase or phrase in compact:
            return "reset_testnet_sandbox"

    for phrase in _RESET_SANDBOX_EN:
        if lower == phrase or lower.startswith(phrase):
            return "reset_testnet_sandbox"

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


def format_reset_sandbox_reply(result: dict) -> str:
    removed = int(result.get("removed_loss_trades") or 0)
    sandbox = "開啟" if result.get("sandbox_enabled") else "關閉"
    return (
        f"已重置測試網沙盒：清除虧損紀錄 {removed} 筆、驗證阻擋已精簡，沙盒模式{sandbox}。"
        " 標的冷卻／歷史劣勢／連虧／強平冷卻在 testnet 將放寬（信心≥0.42）。"
    )
