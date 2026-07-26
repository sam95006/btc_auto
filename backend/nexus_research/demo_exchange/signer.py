"""Phase 6.6 — DemoRequestSigner (HMAC-SHA256). Never logs secrets."""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Mapping
from urllib.parse import urlencode

from backend.nexus_research.demo_exchange.constants import RECV_WINDOW_MS
from backend.nexus_research.demo_exchange.credentials import fingerprint_secret


class DemoRequestSigner:
    """Bybit v5 private GET signer. Secrets stay in memory only."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        if not api_key or not api_secret:
            raise ValueError("signer_requires_credentials")
        self._api_key = api_key
        self._api_secret = api_secret
        self.key_fingerprint = fingerprint_secret(api_key)

    def sign_get(
        self,
        params: Mapping[str, str] | None = None,
        *,
        timestamp_ms: int | None = None,
        recv_window: str = RECV_WINDOW_MS,
    ) -> dict[str, str]:
        ts = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
        query = ""
        if params:
            # Stable order for signing
            items = sorted((str(k), str(v)) for k, v in params.items() if v is not None)
            query = urlencode(items)
        payload = f"{ts}{self._api_key}{recv_window}{query}"
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-BAPI-API-KEY": self._api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv_window,
            "X-BAPI-SIGN-TYPE": "2",
        }

    def __repr__(self) -> str:
        return f"DemoRequestSigner(fp={self.key_fingerprint!r})"

    def __str__(self) -> str:
        return self.__repr__()
