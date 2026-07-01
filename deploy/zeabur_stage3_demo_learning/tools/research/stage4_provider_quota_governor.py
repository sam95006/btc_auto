"""Groq TPM cooldown governor — skip Groq during token quota cooldown."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

_GROQ_TOKEN_429 = frozenset({"rate_limit", "tokens", "provider_http_429", "provider_rate_limited"})


class Stage4ProviderQuotaGovernor:
    """Shared Groq TPM cooldown state for provider chain + summary metrics."""

    _shared: Optional["Stage4ProviderQuotaGovernor"] = None

    def __init__(self) -> None:
        self._cooldown_until = 0.0
        self._first_429_tick: int | None = None
        self._last_429_tick: int | None = None
        self._tokens_429_count = 0
        self._cooldown_skip_count = 0
        self._last_error_type = ""

    @classmethod
    def shared(cls) -> "Stage4ProviderQuotaGovernor":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    @classmethod
    def reset_shared(cls) -> None:
        cls._shared = None

    @staticmethod
    def cooldown_minutes() -> float:
        raw = os.environ.get("STAGE4_GROQ_TPM_COOLDOWN_MINUTES", "45").strip()
        try:
            return max(1.0, float(raw))
        except (TypeError, ValueError):
            return 45.0

    @staticmethod
    def enabled() -> bool:
        return os.environ.get("STAGE4_GROQ_TPM_GOVERNOR_ENABLED", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def record_groq_429(
        self,
        *,
        tick: int | None = None,
        error_type: str = "rate_limit",
        http_status: int | None = None,
    ) -> None:
        if not self.enabled():
            return
        err = str(error_type or "")
        if http_status != 429 and err not in _GROQ_TOKEN_429 and "token" not in err.lower():
            return
        self._tokens_429_count += 1
        if tick is not None:
            if self._first_429_tick is None:
                self._first_429_tick = tick
            self._last_429_tick = tick
        self._last_error_type = err or "rate_limit"
        cooldown_sec = self.cooldown_minutes() * 60.0
        self._cooldown_until = max(self._cooldown_until, time.monotonic() + cooldown_sec)

    def should_skip_groq(self) -> bool:
        if not self.enabled():
            return False
        return time.monotonic() < self._cooldown_until

    def record_cooldown_skip(self) -> None:
        self._cooldown_skip_count += 1

    def summary_fields(self) -> Dict[str, Any]:
        active = self.should_skip_groq()
        return {
            "provider_governor_active": self.enabled(),
            "groq_tpm_cooldown_triggered": active or self._tokens_429_count > 0,
            "groq_cooldown_skip_count": self._cooldown_skip_count,
            "groq_tokens_429_count": self._tokens_429_count,
            "groq_first_429_tick": self._first_429_tick or 0,
            "groq_last_429_tick": self._last_429_tick or 0,
            "groq_cooldown_minutes": self.cooldown_minutes(),
            "groq_cooldown_active": active,
        }
