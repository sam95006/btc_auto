"""Groq API key health registry — fingerprints only, no secret logging."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from tools.research.stage4_provider_chain import GROQ_KEY_ENVS, dedupe_groq_api_keys, key_fingerprint

_STATUS_INVALID_401 = "invalid_401"
_STATUS_RATE_LIMITED_429 = "rate_limited_429"
_STATUS_QUOTA_EMPTY = "provider_quota_exhausted"
_STATUS_VALID = "valid"
_STATUS_UNKNOWN = "unknown"


class GroqKeyRegistry:
    """Track per-key health; disable invalid keys; skip disabled keys in chain."""

    _shared: Optional["GroqKeyRegistry"] = None

    def __init__(self) -> None:
        self._entries: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def shared(cls) -> "GroqKeyRegistry":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    @classmethod
    def reset_shared(cls) -> None:
        cls._shared = None

    def _ensure_entry(self, *, env_name: str, key_value: str) -> Dict[str, Any]:
        fp = key_fingerprint(key_value)
        if fp not in self._entries:
            self._entries[fp] = {
                "env": env_name,
                "fingerprint": fp,
                "status": _STATUS_UNKNOWN,
                "last_error_type": None,
                "disabled": False,
            }
        return self._entries[fp]

    def record_success(self, *, env_name: str, key_value: str) -> None:
        row = self._ensure_entry(env_name=env_name, key_value=key_value)
        row["status"] = _STATUS_VALID
        row["last_error_type"] = None
        row["disabled"] = False

    def record_error(
        self,
        *,
        env_name: str,
        key_value: str,
        error_type: str,
        http_status: int | None = None,
    ) -> None:
        row = self._ensure_entry(env_name=env_name, key_value=key_value)
        err = (error_type or "").strip()
        code = int(http_status or 0)
        row["last_error_type"] = err or None
        if err in {"http_unauthorized", "http_forbidden"} or code in {401, 403}:
            row["status"] = _STATUS_INVALID_401
            row["disabled"] = True
        elif err == "rate_limit" or code == 429:
            row["status"] = _STATUS_RATE_LIMITED_429
        elif err in {"content_empty", "empty_llm_response", "provider_quota_exhausted"}:
            row["status"] = _STATUS_QUOTA_EMPTY
        else:
            row["status"] = _STATUS_UNKNOWN

    def is_disabled(self, key_value: str) -> bool:
        fp = key_fingerprint(key_value)
        row = self._entries.get(fp)
        return bool(row and row.get("disabled"))

    def enabled_env_names(self) -> List[str]:
        _bridge()
        dedup = dedupe_groq_api_keys()
        out: List[str] = []
        for env_name in dedup.get("groq_key_envs_deduped") or []:
            val = (os.environ.get(env_name) or "").strip()
            if not val or self.is_disabled(val):
                continue
            out.append(env_name)
        return out

    def health_report(self) -> Dict[str, Any]:
        from tools.research.stage4_provider_chain import dedupe_groq_api_keys

        dedup = dedupe_groq_api_keys()
        keys: List[Dict[str, Any]] = []
        valid = invalid = rate_limited = 0
        _bridge()
        seen: set[str] = set()
        for env_name in GROQ_KEY_ENVS:
            val = (os.environ.get(env_name) or "").strip()
            if not val:
                continue
            fp = key_fingerprint(val)
            if fp in seen:
                continue
            seen.add(fp)
            row = self._entries.get(fp) or {
                "env": env_name,
                "fingerprint": fp,
                "status": _STATUS_UNKNOWN,
                "last_error_type": None,
                "disabled": False,
            }
            keys.append(
                {
                    "env": row.get("env") or env_name,
                    "fingerprint": fp,
                    "status": row.get("status"),
                    "last_error_type": row.get("last_error_type"),
                    "disabled": bool(row.get("disabled")),
                }
            )
            st = str(row.get("status") or _STATUS_UNKNOWN)
            if st == _STATUS_VALID:
                valid += 1
            elif st == _STATUS_INVALID_401:
                invalid += 1
            elif st in {_STATUS_RATE_LIMITED_429, _STATUS_QUOTA_EMPTY}:
                rate_limited += 1
        return {
            "groq_key_count": len(keys),
            "groq_valid_key_count": valid,
            "groq_invalid_key_count": invalid,
            "groq_rate_limited_key_count": rate_limited,
            "groq_keys": keys,
            "provider_chain_deduped": dedup.get("provider_chain_deduped"),
            "deduped_provider_key_count": dedup.get("deduped_provider_key_count"),
        }


def _bridge() -> None:
    from tools.research.stage4_llm_client import _bridge_groq_env_aliases

    _bridge_groq_env_aliases()


def probe_groq_keys(*, client_factory=None) -> Dict[str, Any]:
    """Read-only probe of each deduped Groq key (no secrets in output)."""
    from tools.research.stage4_llm_client import Stage4LLMClient, Stage4LLMConfig

    _bridge()
    registry = GroqKeyRegistry.shared()
    dedup = dedupe_groq_api_keys()
    envs = list(dedup.get("groq_key_envs_deduped") or [])
    error_distribution: Dict[str, int] = {}
    results: List[Dict[str, Any]] = []
    valid_count = 0
    messages = [{"role": "user", "content": '{"final_action":"skip","symbol":"ETHUSDT","candidate_side":"NONE","confidence":0,"why_skip":"probe","side_reason":"p","confidence_reason":"p","risk_notes":[],"patch_awareness":"","uncertainty":"none","requires_manual_review":false}'}]

    for env_name in envs:
        val = (os.environ.get(env_name) or "").strip()
        if not val:
            continue
        fp = key_fingerprint(val)
        if registry.is_disabled(val):
            results.append(
                {
                    "env": env_name,
                    "fingerprint": fp,
                    "status": "disabled",
                    "error_type": registry._entries.get(fp, {}).get("last_error_type"),
                    "valid_json": False,
                }
            )
            continue
        cfg = Stage4LLMConfig(
            provider="groq",
            model=os.environ.get("STAGE4_LLM_MODEL", "llama-3.3-70b-versatile"),
            api_key_env=env_name,
            endpoint="https://api.groq.com/openai/v1/chat/completions",
        )
        client = Stage4LLMClient(load_env=False) if client_factory is None else client_factory()
        client.config = cfg
        client.available = True
        result = client.complete_json(messages, prompt_hash="capacity_probe", call_kind="capacity_probe", use_rate_gate=False)
        err = str(result.get("error_type") or "unknown")
        ok = result.get("status") == "ok" and int(result.get("raw_content_length") or 0) > 0
        if ok:
            registry.record_success(env_name=env_name, key_value=val)
            valid_count += 1
            st = _STATUS_VALID
        else:
            registry.record_error(
                env_name=env_name,
                key_value=val,
                error_type=err,
                http_status=int(result.get("http_status") or 0) or None,
            )
            st = registry._entries.get(fp, {}).get("status", _STATUS_UNKNOWN)
            error_distribution[err] = error_distribution.get(err, 0) + 1
        results.append(
            {
                "env": env_name,
                "fingerprint": fp,
                "status": st,
                "error_type": err if not ok else None,
                "valid_json": ok,
                "http_status": result.get("http_status"),
            }
        )
    return {
        "groq_key_count": len(results),
        "groq_valid_key_count": valid_count,
        "groq_invalid_key_count": sum(1 for r in results if r.get("status") == _STATUS_INVALID_401),
        "groq_rate_limited_key_count": sum(
            1 for r in results if r.get("status") in {_STATUS_RATE_LIMITED_429, _STATUS_QUOTA_EMPTY}
        ),
        "groq_error_distribution": error_distribution,
        "groq_keys": results,
    }
