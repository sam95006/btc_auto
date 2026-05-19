import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from config.security_config import SECURITY_CONFIG


class AuditLogger:
    def __init__(self, log_path: Optional[str] = None):
        configured_path = log_path or os.getenv(
            SECURITY_CONFIG.audit_log_path_env,
            SECURITY_CONFIG.audit_log_path_default,
        )
        self.log_path = Path(configured_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._previous_hash = self._load_previous_hash()

    def log_security_event(
        self,
        actor: str,
        action: str,
        result: str,
        risk_level: str = "LOW",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor or "system",
            "action": action,
            "result": result,
            "risk_level": risk_level,
            "metadata": self._sanitize(metadata or {}),
        }
        return self._write_record(record)

    def log_secret_access(self, actor: str, secret_label: str, result: str, metadata: Optional[Dict[str, Any]] = None):
        payload = {"secret_label": secret_label}
        payload.update(metadata or {})
        return self.log_security_event(
            actor=actor,
            action="secret_access",
            result=result,
            risk_level="HIGH",
            metadata=payload,
        )

    def log_validation_failure(self, actor: str, action: str, reason: str, metadata: Optional[Dict[str, Any]] = None):
        payload = {"reason": reason}
        payload.update(metadata or {})
        return self.log_security_event(
            actor=actor,
            action=action,
            result="DENY",
            risk_level="MEDIUM",
            metadata=payload,
        )

    def verify_integrity(self) -> bool:
        previous = ""
        if not self.log_path.exists():
            return True
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            expected = self._build_hash(
                previous_hash=previous,
                payload=self._canonical_payload(record, include_hash=False),
            )
            if record.get("hash") != expected:
                return False
            previous = record.get("hash", "")
        return True

    def _load_previous_hash(self) -> str:
        if not self.log_path.exists():
            return ""
        last_hash = ""
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                last_hash = json.loads(line).get("hash", "")
            except Exception:
                continue
        return last_hash

    def _write_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            record["previous_hash"] = self._previous_hash
            record["hash"] = self._build_hash(
                previous_hash=self._previous_hash,
                payload=self._canonical_payload(record, include_hash=False),
            )
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._previous_hash = record["hash"]
        return record

    def _canonical_payload(self, record: Dict[str, Any], include_hash: bool) -> str:
        payload = {k: v for k, v in record.items() if include_hash or k != "hash"}
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _build_hash(self, previous_hash: str, payload: str) -> str:
        return hashlib.sha256(f"{previous_hash}|{payload}".encode("utf-8")).hexdigest()

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self._mask_sensitive(key, subvalue)
                for key, subvalue in value.items()
            }
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        if isinstance(value, tuple):
            return [self._sanitize(item) for item in value]
        return value

    def _mask_sensitive(self, key: str, value: Any) -> Any:
        lower_key = key.lower()
        if lower_key in SECURITY_CONFIG.forbidden_log_fields or lower_key.endswith("_secret") or lower_key.endswith("_token"):
            return self._masked_value(value)
        if isinstance(value, (dict, list, tuple)):
            return self._sanitize(value)
        if isinstance(value, str) and self._looks_like_secret(value):
            return self._masked_value(value)
        return value

    def _looks_like_secret(self, value: str) -> bool:
        condensed = value.strip()
        if " " in condensed or len(condensed) < 16:
            return False
        return any(ch.isdigit() for ch in condensed) and any(ch.isalpha() for ch in condensed)

    def _masked_value(self, value: Any) -> str:
        text = str(value or "")
        if len(text) <= SECURITY_CONFIG.mask_prefix + SECURITY_CONFIG.mask_suffix:
            return SECURITY_CONFIG.mask_token
        return (
            text[: SECURITY_CONFIG.mask_prefix]
            + SECURITY_CONFIG.mask_token
            + text[-SECURITY_CONFIG.mask_suffix :]
        )
