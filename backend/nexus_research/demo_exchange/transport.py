"""Phase 6.6 — DemoReadOnlyTransport: GET-only HTTP to api-demo.bybit.com."""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.nexus_research.demo_exchange.constants import (
    ALLOWED_GET_PATHS,
    DEMO_REST_BASE_URL,
    HTTP_TIMEOUT_SEC,
)
from backend.nexus_research.demo_exchange.credentials import DemoCredentialPresenceValidator
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.errors import (
    MalformedResponseError,
    MethodNotAllowedError,
    PermissionDeniedError,
    RateLimitError,
    SignatureInvalidError,
    TimeoutError_,
    WriteForbiddenError,
)
from backend.nexus_research.demo_exchange.fixtures import FIXTURE_BY_PATH
from backend.nexus_research.demo_exchange.signer import DemoRequestSigner

logger = logging.getLogger(__name__)


class DemoReadOnlyTransport:
    """Private GET transport. POST/PUT/DELETE are impossible."""

    def __init__(
        self,
        *,
        policy: DemoDomainPolicy | None = None,
        signer: DemoRequestSigner | None = None,
        use_fixtures: bool = False,
        timeout_sec: float = HTTP_TIMEOUT_SEC,
        http_get: Callable[..., Any] | None = None,
    ) -> None:
        self.policy = policy or DemoDomainPolicy(DEMO_REST_BASE_URL)
        self.signer = signer
        self.use_fixtures = use_fixtures or signer is None
        self.timeout_sec = float(timeout_sec)
        self._http_get = http_get  # injectable for tests

    # --- hard write blocks ---
    def post(self, *args: Any, **kwargs: Any) -> Any:
        raise MethodNotAllowedError("POST_impossible")

    def put(self, *args: Any, **kwargs: Any) -> Any:
        raise MethodNotAllowedError("PUT_impossible")

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise MethodNotAllowedError("DELETE_impossible")

    def create_order(self, *args: Any, **kwargs: Any) -> Any:
        raise WriteForbiddenError("create_order_impossible")

    def amend_order(self, *args: Any, **kwargs: Any) -> Any:
        raise WriteForbiddenError("amend_order_impossible")

    def cancel_order(self, *args: Any, **kwargs: Any) -> Any:
        raise WriteForbiddenError("cancel_order_impossible")

    def cancel_all(self, *args: Any, **kwargs: Any) -> Any:
        raise WriteForbiddenError("cancel_all_impossible")

    def set_leverage(self, *args: Any, **kwargs: Any) -> Any:
        raise WriteForbiddenError("set_leverage_impossible")

    def trading_stop(self, *args: Any, **kwargs: Any) -> Any:
        raise WriteForbiddenError("trading_stop_impossible")

    def close_position(self, *args: Any, **kwargs: Any) -> Any:
        raise WriteForbiddenError("close_position_impossible")

    def transfer(self, *args: Any, **kwargs: Any) -> Any:
        raise WriteForbiddenError("transfer_impossible")

    def withdraw(self, *args: Any, **kwargs: Any) -> Any:
        raise WriteForbiddenError("withdraw_impossible")

    def apply_demo_money(self, *args: Any, **kwargs: Any) -> Any:
        raise WriteForbiddenError("apply_demo_money_impossible")

    def request(
        self,
        method: str,
        path: str,
        params: Mapping[str, str] | None = None,
        *,
        fixture_kwargs: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.policy.assert_method_allowed(method)
        self.policy.assert_path_not_write(path)
        if path not in ALLOWED_GET_PATHS:
            raise WriteForbiddenError(f"path_not_in_get_allowlist:{path}")

        if self.use_fixtures:
            factory = FIXTURE_BY_PATH.get(path)
            if factory is None:
                raise MalformedResponseError(f"no_fixture_for:{path}")
            return dict(factory(**(fixture_kwargs or {})))

        return self._live_get(path, params or {})

    def _live_get(self, path: str, params: Mapping[str, str]) -> dict[str, Any]:
        if self.signer is None:
            raise SignatureInvalidError("signer_required_for_live")
        base = self.policy.base_url
        query = urlencode(sorted((str(k), str(v)) for k, v in params.items()))
        url = f"{base}{path}"
        if query:
            url = f"{url}?{query}"
        headers = self.signer.sign_get(params)
        headers["Content-Type"] = "application/json"
        # Never log headers (contain key + sign)
        logger.info("demo_readonly_get path=%s", path)

        if self._http_get is not None:
            raw = self._http_get(url, headers=headers, timeout=self.timeout_sec)
            return self._parse_body(raw)

        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                body = resp.read().decode("utf-8")
        except TimeoutError as exc:  # noqa: PERF203
            raise TimeoutError_("http_timeout") from exc
        except HTTPError as exc:
            return self._map_http_error(exc)
        except URLError as exc:
            reason = str(getattr(exc, "reason", exc))
            if "timed out" in reason.lower():
                raise TimeoutError_("http_timeout") from exc
            raise MalformedResponseError("url_error") from exc

        return self._parse_body(body)

    def _map_http_error(self, exc: HTTPError) -> dict[str, Any]:
        code = int(getattr(exc, "code", 0) or 0)
        try:
            body = exc.read().decode("utf-8")
            data = json.loads(body) if body else {}
        except Exception:  # noqa: BLE001
            data = {}
        ret = int(data.get("retCode") or 0)
        if code == 429 or ret == 10006:
            raise RateLimitError("rate_limit")
        if ret in {10003, 10004} or code == 401:
            raise SignatureInvalidError("invalid_signature")
        if ret in {10005, 10016} or code == 403:
            raise PermissionDeniedError("permission_denied")
        raise MalformedResponseError(f"http_error:{code}")

    def _parse_body(self, body: Any) -> dict[str, Any]:
        if isinstance(body, dict):
            data = body
        else:
            try:
                data = json.loads(body)
            except Exception as exc:  # noqa: BLE001
                raise MalformedResponseError("malformed_json") from exc
        if not isinstance(data, dict):
            raise MalformedResponseError("response_not_object")
        ret = int(data.get("retCode") or 0)
        if ret == 10006:
            raise RateLimitError("rate_limit")
        if ret in {10003, 10004}:
            raise SignatureInvalidError("invalid_signature")
        if ret in {10005, 10016}:
            raise PermissionDeniedError("permission_denied")
        return data

    def public_status(self) -> dict[str, Any]:
        return {
            "baseUrl": self.policy.base_url,
            "useFixtures": self.use_fixtures,
            "writeAllowed": False,
            "getOnly": True,
            "signerFingerprint": getattr(self.signer, "key_fingerprint", None),
        }
