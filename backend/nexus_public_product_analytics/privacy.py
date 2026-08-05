"""Privacy helpers: subject pseudonyms and PII refusal."""
from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any, Mapping

from backend.nexus_public_product_analytics.constants import FORBIDDEN_PROP_KEYS


_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class PrivacyViolation(ValueError):
    """Raised when analytics props would leak PII or secrets."""


def hash_subject_id(raw_subject_id: str, *, salt: str) -> str:
    """HMAC-SHA256 pseudonym; empty subject refused."""
    subject = (raw_subject_id or "").strip()
    if not subject:
        raise PrivacyViolation("empty subject_id refused")
    digest = hmac.new(
        key=salt.encode("utf-8"),
        msg=subject.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sub_{digest[:32]}"


def scrub_props(props: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop forbidden keys and refuse string values that look like emails/secrets."""
    if not props:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in props.items():
        norm = str(key).strip().lower()
        if norm in FORBIDDEN_PROP_KEYS:
            raise PrivacyViolation(f"forbidden analytics prop: {key}")
        if isinstance(value, str):
            lowered = value.lower()
            if _EMAIL_RE.search(value):
                raise PrivacyViolation("email-like value refused in analytics props")
            if any(tok in lowered for tok in ("api_key", "Bearer ", "-----begin")):
                raise PrivacyViolation("secret-like value refused in analytics props")
        cleaned[str(key)] = value
    return cleaned
