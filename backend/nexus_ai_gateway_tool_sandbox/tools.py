"""Tool allow-list / ban sandbox for V18-E AI Gateway."""
from __future__ import annotations

from typing import Any

from backend.nexus_ai_gateway_tool_sandbox.constants import (
    ALLOWED_TOOLS,
    BANNED_TOOLS,
    TOOL_ALIASES,
)
from backend.nexus_ai_gateway_tool_sandbox.contracts import ToolCallRequest


def canonicalize_tool_id(raw: str) -> str:
    text = (raw or "").strip()
    if text in TOOL_ALIASES:
        return TOOL_ALIASES[text]
    lowered = text.lower().replace("-", "_").replace(" ", "_")
    if lowered in TOOL_ALIASES:
        return TOOL_ALIASES[lowered]
    # Direct canonical ids
    if text in ALLOWED_TOOLS or text in BANNED_TOOLS:
        return text
    if lowered in ALLOWED_TOOLS or lowered in BANNED_TOOLS:
        return lowered
    return lowered or text


def is_tool_allowed(tool_id: str) -> bool:
    return canonicalize_tool_id(tool_id) in ALLOWED_TOOLS


def is_tool_banned(tool_id: str) -> bool:
    return canonicalize_tool_id(tool_id) in BANNED_TOOLS


class ToolSandbox:
    """Allow-list only. Banned tools always denied. Unknown tools denied."""

    def __init__(
        self,
        *,
        allowed: frozenset[str] | None = None,
        banned: frozenset[str] | None = None,
    ) -> None:
        self.allowed = allowed or ALLOWED_TOOLS
        self.banned = banned or BANNED_TOOLS
        self._denials: list[dict[str, str]] = []

    @property
    def denials(self) -> list[dict[str, str]]:
        return list(self._denials)

    def authorize(self, tool_id: str) -> tuple[bool, str]:
        canonical = canonicalize_tool_id(tool_id)
        if canonical in self.banned:
            self._denials.append(
                {"tool_id": canonical, "reason": "BANNED_TOOL"}
            )
            return False, "BANNED_TOOL"
        if canonical not in self.allowed:
            self._denials.append(
                {"tool_id": canonical, "reason": "NOT_ON_ALLOW_LIST"}
            )
            return False, "NOT_ON_ALLOW_LIST"
        return True, "ALLOWED"

    def filter_tool_calls(
        self, calls: list[ToolCallRequest] | tuple[ToolCallRequest, ...]
    ) -> tuple[list[ToolCallRequest], list[str]]:
        accepted: list[ToolCallRequest] = []
        denied: list[str] = []
        for call in calls:
            ok, reason = self.authorize(call.tool_id)
            if ok:
                accepted.append(
                    ToolCallRequest(
                        tool_id=canonicalize_tool_id(call.tool_id),
                        args=dict(call.args),
                    )
                )
            else:
                denied.append(f"{canonicalize_tool_id(call.tool_id)}:{reason}")
        return accepted, denied

    def execute_readonly(self, tool_id: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute only allow-listed read tools against provided args (fixture-safe)."""
        ok, reason = self.authorize(tool_id)
        canonical = canonicalize_tool_id(tool_id)
        if not ok:
            return {
                "ok": False,
                "tool_id": canonical,
                "denied": True,
                "reason": reason,
            }
        payload = dict(args or {})
        # Sandbox never reaches exchange/account/wallet — returns echo of inputs only.
        return {
            "ok": True,
            "tool_id": canonical,
            "denied": False,
            "reason": "ALLOWED",
            "data": payload,
            "mode": "READ_ONLY",
        }
