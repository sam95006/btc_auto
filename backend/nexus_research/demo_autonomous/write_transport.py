"""Session-gated Bybit Demo write transport (api-demo.bybit.com only)."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.nexus_research.demo_autonomous.session_authorization import (
    AuthorizationError,
    AuthorizationValidator,
    get_authorization_validator,
)
from backend.nexus_research.demo_exchange.constants import DEMO_REST_BASE_URL, HTTP_TIMEOUT_SEC, RECV_WINDOW_MS
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.errors import (
    DomainRejectedError,
    MalformedResponseError,
    RateLimitError,
    SignatureInvalidError,
    TimeoutError_,
    WriteForbiddenError,
)
from backend.nexus_research.demo_exchange.signer import DemoRequestSigner

logger = logging.getLogger(__name__)

ALLOWED_WRITE_PATHS = frozenset({
    "/v5/order/create",
    "/v5/order/cancel",
    "/v5/position/set-leverage",
    "/v5/position/trading-stop",
    "/v5/account/set-margin-mode",
    "/v5/position/switch-mode",
})

# Classic path — intentionally NOT allowlisted for Demo UTA.
DEMO_BLOCKED_CLASSIC_PATHS = frozenset({
    "/v5/position/switch-isolated",
})

ALLOWED_PRIVATE_GET_PATHS = frozenset({
    "/v5/user/query-api",
    "/v5/account/info",
    "/v5/account/wallet-balance",
    "/v5/position/list",
    "/v5/order/realtime",
    "/v5/order/history",
    "/v5/execution/list",
    "/v5/market/instruments-info",
})

FORBIDDEN_ALWAYS = frozenset({
    "/v5/asset/transfer",
    "/v5/asset/withdraw",
    "/v5/asset/deposit",
})


class DemoWriteTransport:
    """POST-capable Demo transport. Requires active session authorization."""

    def __init__(
        self,
        *,
        signer: DemoRequestSigner,
        auth: AuthorizationValidator | None = None,
        policy: DemoDomainPolicy | None = None,
        timeout_sec: float = HTTP_TIMEOUT_SEC,
        dry_run: bool = False,
    ) -> None:
        self.signer = signer
        self.auth = auth or get_authorization_validator()
        self.policy = policy or DemoDomainPolicy(DEMO_REST_BASE_URL)
        self.timeout_sec = float(timeout_sec)
        self.dry_run = dry_run
        self.write_calls = 0

    def _assert_session(self) -> None:
        self.auth.require_active()

    def _assert_path(self, path: str) -> None:
        if path in FORBIDDEN_ALWAYS or "withdraw" in path or "transfer" in path:
            raise WriteForbiddenError(f"path_forbidden:{path}")
        if path in DEMO_BLOCKED_CLASSIC_PATHS:
            raise WriteForbiddenError(f"path_not_supported_on_bybit_demo:{path}")
        if path not in ALLOWED_WRITE_PATHS:
            raise WriteForbiddenError(f"path_not_in_write_allowlist:{path}")
        # Domain must remain demo
        if self.policy.ALLOWED_HOST != "api-demo.bybit.com":
            raise DomainRejectedError("host_not_demo")

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Private GET for account/position truth (session not required for preflight reads)."""
        if path not in ALLOWED_PRIVATE_GET_PATHS:
            raise WriteForbiddenError(f"path_not_in_private_get_allowlist:{path}")
        if self.policy.ALLOWED_HOST != "api-demo.bybit.com":
            raise DomainRejectedError("host_not_demo")
        if self.dry_run:
            return {"retCode": 0, "retMsg": "OK", "result": {"dryRun": True, "list": []}}
        return self._live_get(path, dict(params or {}))

    def post(self, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        self._assert_session()
        self._assert_path(path)
        self.write_calls += 1
        self.auth.record_write()
        if self.dry_run:
            logger.info("demo_write_dry_run path=%s keys=%s", path, sorted(body.keys()))
            return {
                "retCode": 0,
                "retMsg": "OK",
                "result": {"dryRun": True, "orderId": f"dry-{int(time.time()*1000)}"},
                "time": int(time.time() * 1000),
            }
        return self._live_post(path, dict(body))

    def _live_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        from urllib.parse import urlencode

        str_params = {str(k): str(v) for k, v in params.items() if v is not None}
        headers = self.signer.sign_get(str_params)
        query = urlencode(sorted(str_params.items())) if str_params else ""
        url = f"{self.policy.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except HTTPError as exc:
            if exc.code == 429:
                raise RateLimitError("rate_limit") from exc
            if exc.code in (401, 403):
                raise SignatureInvalidError("auth_rejected") from exc
            raise MalformedResponseError(f"http_{exc.code}") from exc
        except URLError as exc:
            raise TimeoutError_(f"url_error:{type(exc).__name__}") from exc
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise MalformedResponseError("non_object")
        return data

    def _live_post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        ts = str(int(time.time() * 1000))
        body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        # Bybit v5 POST sign: timestamp + apiKey + recvWindow + body
        payload = f"{ts}{self.signer._api_key}{RECV_WINDOW_MS}{body_json}"
        import hashlib
        import hmac as hm

        signature = hm.new(
            self.signer._api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "X-BAPI-API-KEY": self.signer._api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": RECV_WINDOW_MS,
            "X-BAPI-SIGN-TYPE": "2",
            "Content-Type": "application/json",
        }
        url = f"{self.policy.base_url}{path}"
        req = Request(url, data=body_json.encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except HTTPError as exc:
            if exc.code == 429:
                raise RateLimitError("rate_limit") from exc
            if exc.code in (401, 403):
                raise SignatureInvalidError("auth_rejected") from exc
            raise MalformedResponseError(f"http_{exc.code}") from exc
        except URLError as exc:
            raise TimeoutError_(f"url_error:{type(exc).__name__}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MalformedResponseError("invalid_json") from exc
        if not isinstance(data, dict):
            raise MalformedResponseError("non_object")
        return data
