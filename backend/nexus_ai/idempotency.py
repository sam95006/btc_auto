"""Request idempotency and successful-call deduplication."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def make_idempotency_key(
    *,
    profile_id: str,
    case_id: str,
    prompt_hash: str,
    schema_version: str,
) -> str:
    blob = "|".join(
        [
            str(profile_id),
            str(case_id),
            str(prompt_hash),
            str(schema_version),
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def response_fingerprint(payload: dict[str, Any] | None) -> str:
    return hashlib.sha256(
        json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


class SuccessfulCallDeduper:
    """Never bill a successfully completed (profile, case_id) twice."""

    def __init__(self) -> None:
        self._completed: dict[str, str] = {}  # key -> response_hash
        self._idempotent_keys: set[str] = set()
        self._callback_fingerprints: set[str] = set()

    @staticmethod
    def _case_key(profile_id: str, case_id: str) -> str:
        return f"{profile_id}::{case_id}"

    def already_completed(self, profile_id: str, case_id: str) -> bool:
        return self._case_key(profile_id, case_id) in self._completed

    def mark_completed(
        self,
        profile_id: str,
        case_id: str,
        *,
        response_hash: str,
        idempotency_key: str | None = None,
    ) -> None:
        self._completed[self._case_key(profile_id, case_id)] = response_hash
        if idempotency_key:
            self._idempotent_keys.add(idempotency_key)

    def register_idempotency_key(self, key: str) -> bool:
        """Return False if this key was already used (duplicate request)."""
        if key in self._idempotent_keys:
            return False
        self._idempotent_keys.add(key)
        return True

    def register_callback_fingerprint(self, fingerprint: str) -> bool:
        """Return False if duplicate Provider callback payload."""
        if fingerprint in self._callback_fingerprints:
            return False
        self._callback_fingerprints.add(fingerprint)
        return True

    def completed_response_hash(self, profile_id: str, case_id: str) -> str | None:
        return self._completed.get(self._case_key(profile_id, case_id))

    def load_from_checkpoint(self, state: dict[str, Any]) -> None:
        for cid in state.get("completed_case_ids") or []:
            row = (state.get("case_results") or {}).get(cid) or {}
            rh = str(row.get("response_hash") or state.get("response_hashes", {}).get(cid) or "")
            self.mark_completed(GROQ_PROFILE, str(cid), response_hash=rh)
        for cid in state.get("critic_resolved_ids") or []:
            row = (state.get("case_results") or {}).get(cid) or {}
            rh = str(row.get("critic_response_hash") or f"critic:{cid}")
            self.mark_completed(CRITIC_PROFILE, str(cid), response_hash=rh)
        for key in state.get("idempotency_keys") or []:
            self._idempotent_keys.add(str(key))

    def export(self) -> dict[str, Any]:
        return {
            "completed": dict(self._completed),
            "idempotency_keys": sorted(self._idempotent_keys),
            "callback_fingerprints": sorted(self._callback_fingerprints),
        }


# Local aliases to avoid circular imports at module load for load_from_checkpoint
GROQ_PROFILE = "GROQ_REFLECTION_REASONER"
CRITIC_PROFILE = "SAMBANOVA_INDEPENDENT_CRITIC"
