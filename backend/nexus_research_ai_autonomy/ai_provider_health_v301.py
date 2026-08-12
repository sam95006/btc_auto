"""V18.2.30.1 AI provider health / quota observability for Research Autonomy.

Never persists secret tokens. Does not manufacture trading decisions.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AI_STATES = frozenset(
    {
        "AI_READY",
        "AI_RATE_LIMITED",
        "AI_QUOTA_EXHAUSTED",
        "AI_AUTH_FAILED",
        "AI_TIMEOUT",
        "AI_PROVIDER_DEGRADED",
        "AI_NOT_CONFIGURED",
    }
)

# Profiles actually relevant to Founder AI stack (probe for observability).
# Current V30 entry cycle is deterministic unless NEXUS_LLM_ENABLE + llm_fn wired.
PROBE_PROFILES = (
    ("GROQ_MAIN_REASONER", "GROQ_API_KEY_PRIMARY", "groq", "https://api.groq.com/openai/v1/models"),
    ("GROQ_REFLECTION_REASONER", "GROQ_API_KEY_SECONDARY", "groq", "https://api.groq.com/openai/v1/models"),
    ("CEREBRAS_RESEARCH_NORMALIZER", "CEREBRAS_API_KEY", "cerebras", "https://api.cerebras.ai/v1/models"),
    ("SAMBANOVA_INDEPENDENT_CRITIC", "SAMBANOVA_API_KEY", "sambanova", "https://api.sambanova.ai/v1/models"),
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> float:
    return time.time()


@dataclass
class ProviderHealth:
    provider: str
    profile: str
    model: str | None
    configured: bool
    credential_present: bool
    last_request_at: str | None = None
    last_success_at: str | None = None
    last_status: str | None = None
    requests_1h: int = 0
    requests_24h: int = 0
    successes_24h: int = 0
    rate_limits_24h: int = 0
    auth_failures_24h: int = 0
    timeouts_24h: int = 0
    provider_errors_24h: int = 0
    quota_errors_24h: int = 0
    last_error_code: str | None = None
    last_error_class: str | None = None
    quota_status: str | None = None
    usage_remaining: float | None = None
    fallback_used: bool = False
    ai_state: str = "AI_NOT_CONFIGURED"
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("events", None)
        # Never include secrets
        return d


class AIProviderHealthRegistry:
    """Rolling counters for autonomy AI observability."""

    SCHEMA = "v18_2_30_1_ai_provider_health_v1"

    def __init__(self, *, store_path: Path | None = None) -> None:
        self.store_path = store_path
        self.providers: dict[str, ProviderHealth] = {}
        self._load()

    def _load(self) -> None:
        if not self.store_path or not self.store_path.is_file():
            return
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
            for row in raw.get("providers") or []:
                if not isinstance(row, dict):
                    continue
                ph = ProviderHealth(
                    provider=str(row.get("provider") or ""),
                    profile=str(row.get("profile") or ""),
                    model=row.get("model"),
                    configured=bool(row.get("configured")),
                    credential_present=bool(row.get("credential_present")),
                    last_request_at=row.get("last_request_at"),
                    last_success_at=row.get("last_success_at"),
                    last_status=row.get("last_status"),
                    requests_1h=int(row.get("requests_1h") or 0),
                    requests_24h=int(row.get("requests_24h") or 0),
                    successes_24h=int(row.get("successes_24h") or 0),
                    rate_limits_24h=int(row.get("rate_limits_24h") or 0),
                    auth_failures_24h=int(row.get("auth_failures_24h") or 0),
                    timeouts_24h=int(row.get("timeouts_24h") or 0),
                    provider_errors_24h=int(row.get("provider_errors_24h") or 0),
                    quota_errors_24h=int(row.get("quota_errors_24h") or 0),
                    last_error_code=row.get("last_error_code"),
                    last_error_class=row.get("last_error_class"),
                    quota_status=row.get("quota_status"),
                    usage_remaining=row.get("usage_remaining"),
                    fallback_used=bool(row.get("fallback_used")),
                    ai_state=str(row.get("ai_state") or "AI_NOT_CONFIGURED"),
                    events=list(row.get("events") or []),
                )
                self.providers[ph.profile] = ph
        except Exception:  # noqa: BLE001
            return

    def save(self) -> None:
        if not self.store_path:
            return
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": self.SCHEMA,
            "updated_at": _utc(),
            "providers": [p.to_public_dict() | {"events": p.events[-50:]} for p in self.providers.values()],
            "aggregate": self.aggregate(),
        }
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        tmp.replace(self.store_path)

    def _prune_events(self, ph: ProviderHealth) -> None:
        cutoff = _now() - 86400.0
        ph.events = [e for e in ph.events if float(e.get("ts") or 0) >= cutoff]
        hour = _now() - 3600.0
        ph.requests_1h = sum(1 for e in ph.events if float(e.get("ts") or 0) >= hour)
        ph.requests_24h = len(ph.events)
        ph.successes_24h = sum(1 for e in ph.events if e.get("ok"))
        ph.rate_limits_24h = sum(1 for e in ph.events if e.get("class") == "RATE_LIMIT")
        ph.auth_failures_24h = sum(1 for e in ph.events if e.get("class") == "AUTH")
        ph.timeouts_24h = sum(1 for e in ph.events if e.get("class") == "TIMEOUT")
        ph.provider_errors_24h = sum(1 for e in ph.events if e.get("class") == "PROVIDER")
        ph.quota_errors_24h = sum(1 for e in ph.events if e.get("class") == "QUOTA")

    def record(
        self,
        *,
        profile: str,
        provider: str,
        model: str | None,
        ok: bool,
        status: str | None,
        error_class: str | None = None,
        error_code: str | None = None,
        quota_status: str | None = None,
        usage_remaining: float | None = None,
        fallback_used: bool = False,
    ) -> ProviderHealth:
        ph = self.providers.get(profile) or ProviderHealth(
            provider=provider,
            profile=profile,
            model=model,
            configured=True,
            credential_present=True,
        )
        ph.provider = provider
        ph.model = model or ph.model
        ph.configured = True
        ph.credential_present = True
        ph.last_request_at = _utc()
        ph.last_status = status
        ph.fallback_used = fallback_used
        if ok:
            ph.last_success_at = _utc()
            ph.ai_state = "AI_READY"
            ph.last_error_code = None
            ph.last_error_class = None
        else:
            ph.last_error_code = error_code
            ph.last_error_class = error_class
            ph.ai_state = self._state_from_error(error_class)
        if quota_status is not None:
            ph.quota_status = quota_status
        if usage_remaining is not None:
            ph.usage_remaining = usage_remaining
        ph.events.append(
            {
                "ts": _now(),
                "ok": ok,
                "status": status,
                "class": error_class,
                "code": error_code,
            }
        )
        self._prune_events(ph)
        self.providers[profile] = ph
        self.save()
        return ph

    @staticmethod
    def _state_from_error(error_class: str | None) -> str:
        m = {
            "RATE_LIMIT": "AI_RATE_LIMITED",
            "QUOTA": "AI_QUOTA_EXHAUSTED",
            "AUTH": "AI_AUTH_FAILED",
            "TIMEOUT": "AI_TIMEOUT",
            "PROVIDER": "AI_PROVIDER_DEGRADED",
        }
        return m.get(str(error_class or "").upper(), "AI_PROVIDER_DEGRADED")

    def classify_http_error(self, code: int, body: str) -> tuple[str, str]:
        low = (body or "").lower()
        if code == 401 or code == 403:
            return "AUTH", str(code)
        if code == 429:
            if any(x in low for x in ("quota", "insufficient_quota", "billing", "exceeded your")):
                return "QUOTA", "429_quota"
            return "RATE_LIMIT", "429"
        if any(x in low for x in ("insufficient_quota", "quota_exceeded", "billing_hard_limit")):
            return "QUOTA", str(code)
        return "PROVIDER", str(code)

    def probe_all(self, *, timeout_sec: float = 8.0) -> dict[str, Any]:
        """Lightweight connectivity probe — does not invent trading decisions."""
        results: list[dict[str, Any]] = []
        for profile, env_key, provider, url in PROBE_PROFILES:
            key = (os.environ.get(env_key) or "").strip()
            model = os.environ.get(
                {
                    "GROQ_MAIN_REASONER": "NEXUS_GROQ_MAIN_MODEL",
                    "GROQ_REFLECTION_REASONER": "NEXUS_GROQ_REFLECTION_MODEL",
                    "CEREBRAS_RESEARCH_NORMALIZER": "NEXUS_CEREBRAS_MODEL",
                    "SAMBANOVA_INDEPENDENT_CRITIC": "NEXUS_SAMBANOVA_MODEL",
                }.get(profile, ""),
                "",
            ) or None
            if not key:
                ph = ProviderHealth(
                    provider=provider,
                    profile=profile,
                    model=model,
                    configured=False,
                    credential_present=False,
                    ai_state="AI_NOT_CONFIGURED",
                    last_status="NO_CREDENTIAL",
                )
                self.providers[profile] = ph
                results.append(ph.to_public_dict())
                continue

            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "User-Agent": "NEXUS-Autonomy-AI-Health/18.2.30.1",
                    },
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    _ = resp.read(2048)
                    status = f"HTTP_{resp.status}"
                    ph = self.record(
                        profile=profile,
                        provider=provider,
                        model=model,
                        ok=True,
                        status=status,
                    )
                    results.append(ph.to_public_dict())
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")[:500]
                except Exception:  # noqa: BLE001
                    body = ""
                err_class, err_code = self.classify_http_error(int(exc.code), body)
                # Never store body (may contain sensitive fragments) — class/code only.
                ph = self.record(
                    profile=profile,
                    provider=provider,
                    model=model,
                    ok=False,
                    status=f"HTTP_{exc.code}",
                    error_class=err_class,
                    error_code=err_code,
                    quota_status="EXHAUSTED" if err_class == "QUOTA" else None,
                )
                results.append(ph.to_public_dict())
            except TimeoutError:
                ph = self.record(
                    profile=profile,
                    provider=provider,
                    model=model,
                    ok=False,
                    status="TIMEOUT",
                    error_class="TIMEOUT",
                    error_code="timeout",
                )
                results.append(ph.to_public_dict())
            except Exception as exc:  # noqa: BLE001
                name = type(exc).__name__
                err_class = "TIMEOUT" if "timeout" in name.lower() else "PROVIDER"
                ph = self.record(
                    profile=profile,
                    provider=provider,
                    model=model,
                    ok=False,
                    status=name,
                    error_class=err_class,
                    error_code=name,
                )
                results.append(ph.to_public_dict())

        self.save()
        return {"schema": self.SCHEMA, "probed_at": _utc(), "providers": results, "aggregate": self.aggregate()}

    def aggregate(self) -> dict[str, Any]:
        rows = list(self.providers.values())
        if not rows:
            return {
                "ai_state": "AI_NOT_CONFIGURED",
                "configured": False,
                "credential_present": False,
                "quota_exhausted": "UNKNOWN",
                "rate_limited": False,
                "ai_auth_failed": False,
                "ai_calls_working": False,
                "last_successful_ai_call": None,
                "ai_required_for_v30_entry": False,
                "fallback_used": False,
            }

        configured = any(r.configured and r.credential_present for r in rows)
        working = any(r.ai_state == "AI_READY" and r.last_success_at for r in rows)
        quota = any(r.ai_state == "AI_QUOTA_EXHAUSTED" or r.quota_errors_24h > 0 for r in rows)
        rate = any(r.ai_state == "AI_RATE_LIMITED" or r.rate_limits_24h > 0 for r in rows)
        auth = any(r.ai_state == "AI_AUTH_FAILED" or r.auth_failures_24h > 0 for r in rows)
        last_success = None
        for r in rows:
            if r.last_success_at and (last_success is None or r.last_success_at > last_success):
                last_success = r.last_success_at

        # Priority state for Founder banner
        if not configured:
            state = "AI_NOT_CONFIGURED"
        elif quota and not working:
            state = "AI_QUOTA_EXHAUSTED"
        elif rate and not working:
            state = "AI_RATE_LIMITED"
        elif auth and not working:
            state = "AI_AUTH_FAILED"
        elif working:
            state = "AI_READY"
        else:
            state = "AI_PROVIDER_DEGRADED"

        primary = next((r for r in rows if r.credential_present), rows[0])
        return {
            "provider": primary.provider,
            "model": primary.model,
            "profile": primary.profile,
            "configured": configured,
            "credential_present": configured,
            "ai_state": state,
            "last_request": primary.last_request_at,
            "last_success": last_success,
            "requests_24h": sum(r.requests_24h for r in rows),
            "successes_24h": sum(r.successes_24h for r in rows),
            "rate_limits_24h": sum(r.rate_limits_24h for r in rows),
            "quota_errors_24h": sum(r.quota_errors_24h for r in rows),
            "auth_errors_24h": sum(r.auth_failures_24h for r in rows),
            "timeouts_24h": sum(r.timeouts_24h for r in rows),
            "last_error": primary.last_error_code,
            "quota_exhausted": True if quota else (False if configured else "UNKNOWN"),
            "rate_limited": bool(rate),
            "ai_auth_failed": bool(auth),
            "ai_calls_working": bool(working),
            "last_successful_ai_call": last_success,
            # Honest: V30 entry path does not require LLM unless explicitly wired.
            "ai_required_for_v30_entry": (
                os.environ.get("NEXUS_LLM_ENABLE", "false").lower() in {"1", "true", "yes"}
                and os.environ.get("NEXUS_AUTONOMY_REQUIRE_AI_ENTRY", "false").lower()
                in {"1", "true", "yes"}
            ),
            "fallback_used": any(r.fallback_used for r in rows),
        }
