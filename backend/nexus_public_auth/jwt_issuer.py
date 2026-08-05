"""Public-only JWT issuer — isolated from private / founder / operator secrets."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from typing import Any, Optional

from backend.nexus_public_auth.constants import (
    PUBLIC_IDENTITY_REALM,
    PUBLIC_JWT_AUDIENCE,
    PUBLIC_JWT_ISSUER,
)
from backend.nexus_public_auth.hard_bans import (
    HardBanViolation,
    refuse_private_admin_session_reuse,
    refuse_private_secret_env,
    refuse_shared_private_jwt_issuer,
    validate_public_issuer,
    validate_public_realm,
)

PUBLIC_JWT_SECRET_ENV = "NEXUS_PUBLIC_JWT_SECRET"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_json(obj: dict[str, Any]) -> str:
    raw = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _b64url(raw)


class PublicJwtIssuer:
    """HS256-compatible compact token issuer bound to the public identity realm."""

    def __init__(self, secret: Optional[str] = None, *, secret_env: str = PUBLIC_JWT_SECRET_ENV):
        refuse_private_secret_env(secret_env)
        if secret_env != PUBLIC_JWT_SECRET_ENV:
            refuse_shared_private_jwt_issuer()
        resolved = secret or os.environ.get(secret_env) or secrets.token_urlsafe(48)
        if not resolved or len(resolved) < 16:
            raise HardBanViolation("HARD BAN: public JWT secret too weak or missing")
        self.secret = resolved
        self.secret_env = secret_env
        self.issuer = PUBLIC_JWT_ISSUER
        self.realm = PUBLIC_IDENTITY_REALM
        self.audience = PUBLIC_JWT_AUDIENCE
        validate_public_issuer(self.issuer)
        validate_public_realm(self.realm)

    def issue(
        self,
        *,
        account_id: str,
        tier: str,
        member_roles: list[str],
        ttl_seconds: int = 3600,
        extra_claims: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        now = int(time.time())
        jti = uuid.uuid4().hex
        header = {"alg": "HS256", "typ": "JWT"}
        payload: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": account_id,
            "jti": jti,
            "iat": now,
            "exp": now + int(ttl_seconds),
            "realm": self.realm,
            "tier": tier,
            "member_roles": list(member_roles),
            "token_use": "public_member_session",
        }
        if extra_claims:
            # Never allow private realm / issuer override via extra claims.
            blocked = {"iss", "realm", "aud", "token_use"}
            for key in blocked:
                if key in extra_claims:
                    raise HardBanViolation(
                        f"HARD BAN: cannot override protected claim {key!r} on public tokens"
                    )
            payload.update(extra_claims)
        token = self._sign(header, payload)
        return {
            "token": token,
            "jti": jti,
            "expires_at_epoch": payload["exp"],
            "issuer": self.issuer,
            "realm": self.realm,
            "account_id": account_id,
        }

    def verify(self, token: str) -> dict[str, Any]:
        header, payload, _sig = self._split(token)
        if header.get("alg") != "HS256":
            raise HardBanViolation("HARD BAN: unsupported JWT alg for public realm")
        expected = self._sign(header, payload)
        if not hmac.compare_digest(expected, token):
            raise HardBanViolation("public JWT signature mismatch")
        validate_public_issuer(str(payload.get("iss", "")))
        validate_public_realm(str(payload.get("realm", "")))
        if payload.get("aud") != self.audience:
            raise HardBanViolation("public JWT audience mismatch")
        if payload.get("token_use") != "public_member_session":
            refuse_private_admin_session_reuse()
        if int(payload.get("exp", 0)) < int(time.time()):
            raise HardBanViolation("public JWT expired")
        return payload

    def reject_foreign_token(self, token: str, *, claimed_issuer: str) -> None:
        """Explicit refusal path for private / founder tokens presented to public APIs."""
        try:
            validate_public_issuer(claimed_issuer)
        except HardBanViolation:
            refuse_private_admin_session_reuse()
        # If issuer string looks public but token payload is foreign, still refuse.
        try:
            payload = self.verify(token)
        except HardBanViolation:
            refuse_private_admin_session_reuse()
            return
        if payload.get("realm") != PUBLIC_IDENTITY_REALM:
            refuse_private_admin_session_reuse()

    def fingerprint(self) -> str:
        return hashlib.sha256(self.secret.encode("utf-8")).hexdigest()[:16]

    def _sign(self, header: dict[str, Any], payload: dict[str, Any]) -> str:
        signing_input = f"{_b64url_json(header)}.{_b64url_json(payload)}".encode("ascii")
        sig = hmac.new(self.secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        return f"{signing_input.decode('ascii')}.{_b64url(sig)}"

    def _split(self, token: str) -> tuple[dict[str, Any], dict[str, Any], str]:
        parts = token.split(".")
        if len(parts) != 3:
            raise HardBanViolation("malformed public JWT")
        header = json.loads(_pad_b64(parts[0]))
        payload = json.loads(_pad_b64(parts[1]))
        return header, payload, parts[2]


def _pad_b64(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def build_issuer_from_env() -> PublicJwtIssuer:
    return PublicJwtIssuer()
