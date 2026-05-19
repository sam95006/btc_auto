import re
from typing import Any, Dict, Iterable

from backend.audit.audit_logger import AuditLogger
from config.security_config import SECURITY_CONFIG


class RequestValidationError(ValueError):
    pass


class RequestValidator:
    SECRET_VALUE_REGEX = re.compile(r"\b[A-Za-z0-9_\-]{16,}\b")

    def __init__(self, audit_logger: AuditLogger | None = None):
        self.audit_logger = audit_logger or AuditLogger()

    def validate_read_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._validate_payload(
            payload=payload,
            required_fields=SECURITY_CONFIG.read_request_required_fields,
            action_name="validate_read_request",
        )

    def validate_admin_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        validated = self._validate_payload(
            payload=payload,
            required_fields=SECURITY_CONFIG.admin_request_required_fields,
            action_name="validate_admin_request",
        )
        if validated.get("action") in SECURITY_CONFIG.high_risk_actions and not validated.get("justification"):
            self._deny("High risk admin request requires justification", payload, "validate_admin_request")
        return validated

    def validate_trade_proposal_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        validated = self._validate_payload(
            payload=payload,
            required_fields=SECURITY_CONFIG.trade_proposal_required_fields,
            action_name="validate_trade_proposal_request",
        )
        if "execute" in str(validated.get("action", "")).lower():
            self._deny("Trade execution requests are forbidden in Phase 0.1", payload, "validate_trade_proposal_request")
        return validated

    def _validate_payload(self, payload: Dict[str, Any], required_fields: Iterable[str], action_name: str) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            self._deny("Payload must be a dictionary", payload, action_name)

        missing = [field for field in required_fields if not payload.get(field)]
        if missing:
            self._deny(f"Missing required fields: {', '.join(missing)}", payload, action_name)

        flattened = self._flatten(payload).lower()
        for pattern in SECURITY_CONFIG.forbidden_payload_patterns:
            if pattern.lower() in flattened:
                self._deny(f"Forbidden pattern detected: {pattern}", payload, action_name)

        if self._contains_secret(payload):
            self._deny("Payload contains secret-like material", payload, action_name)

        return payload

    def _contains_secret(self, payload: Dict[str, Any]) -> bool:
        for key, value in self._walk(payload):
            lower_key = str(key).lower()
            if any(marker in lower_key for marker in SECURITY_CONFIG.sensitive_value_markers):
                return True
            if isinstance(value, str):
                text = value.strip()
                if text.startswith("AKIA") or "-----BEGIN" in text:
                    return True
                if self.SECRET_VALUE_REGEX.search(text) and any(ch.isdigit() for ch in text) and any(ch.isalpha() for ch in text):
                    return True
        return False

    def _walk(self, payload: Any, parent_key: str = ""):
        if isinstance(payload, dict):
            for key, value in payload.items():
                yield key, value
                yield from self._walk(value, str(key))
        elif isinstance(payload, list):
            for item in payload:
                yield from self._walk(item, parent_key)

    def _flatten(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return " ".join(f"{key} {self._flatten(value)}" for key, value in payload.items())
        if isinstance(payload, list):
            return " ".join(self._flatten(item) for item in payload)
        return str(payload)

    def _deny(self, reason: str, payload: Any, action_name: str):
        self.audit_logger.log_validation_failure(
            actor=self._actor_from_payload(payload),
            action=action_name,
            reason=reason,
            metadata={"payload": payload},
        )
        raise RequestValidationError(reason)

    def _actor_from_payload(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return str(payload.get("actor") or "unknown")
        return "unknown"
