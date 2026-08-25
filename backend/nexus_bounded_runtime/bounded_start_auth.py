"""Signed one-shot Founder start for bounded 6H — no transient Zeabur env authority."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from tools.ci.demo_bounded_session_lease import FOUNDER_PHRASE

SECRET_ENV = "NEXUS_BOUNDED_SESSION_CONTROL_SECRET"
SHORT_FOUNDER_PHRASE = "START_NEXUS_BYBIT_DEMO_CERTIFIED_SHORT_V1"
_MAX_SKEW_SEC = 300
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def _secret_bytes() -> bytes:
    raw = (os.environ.get(SECRET_ENV) or "").strip()
    if not raw:
        raise ValueError("bounded_control_secret_missing")
    return raw.encode("utf-8")


def canonical_start_bytes(*, lease: dict[str, Any], founder_phrase: str, signed_at: str) -> bytes:
    payload = {
        "founder_phrase": founder_phrase,
        "lease": lease,
        "signed_at": signed_at,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_bounded_start_request(
    *,
    lease: dict[str, Any],
    founder_phrase: str = FOUNDER_PHRASE,
    signed_at: str | None = None,
    secret: str | None = None,
) -> dict[str, Any]:
    ts = signed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    key = (secret or os.environ.get(SECRET_ENV) or "").strip().encode("utf-8")
    if not key:
        raise ValueError("bounded_control_secret_missing")
    body_bytes = canonical_start_bytes(lease=lease, founder_phrase=founder_phrase, signed_at=ts)
    signature = hmac.new(key, body_bytes, hashlib.sha256).hexdigest()
    return {
        "lease": lease,
        "founder_phrase": founder_phrase,
        "signed_at": ts,
        "signature": signature,
    }


def verify_bounded_start_request(
    body: dict[str, Any] | None,
    *,
    expected_founder_phrase: str = FOUNDER_PHRASE,
) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {"ok": False, "reason": "start_request_missing"}
    lease = body.get("lease")
    if not isinstance(lease, dict):
        return {"ok": False, "reason": "lease_missing"}
    founder_phrase = str(body.get("founder_phrase") or "").strip()
    signed_at = str(body.get("signed_at") or "").strip()
    signature = str(body.get("signature") or "").strip().lower()
    if founder_phrase != expected_founder_phrase:
        return {"ok": False, "reason": "founder_phrase_invalid"}
    if not signed_at:
        return {"ok": False, "reason": "signed_at_missing"}
    if not _SHA256_HEX.fullmatch(signature):
        return {"ok": False, "reason": "signature_invalid"}
    try:
        key = _secret_bytes()
    except ValueError:
        return {"ok": False, "reason": "bounded_control_secret_missing"}
    expected = hmac.new(
        key,
        canonical_start_bytes(lease=lease, founder_phrase=founder_phrase, signed_at=signed_at),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return {"ok": False, "reason": "signature_mismatch"}
    try:
        signed_dt = datetime.fromisoformat(signed_at.replace("Z", "+00:00"))
        skew = abs((datetime.now(timezone.utc) - signed_dt).total_seconds())
        if skew > _MAX_SKEW_SEC:
            return {"ok": False, "reason": "signed_at_skew_exceeded"}
    except ValueError:
        return {"ok": False, "reason": "signed_at_invalid"}
    return {"ok": True, "lease": lease, "founder_authorization_one_shot": True}
