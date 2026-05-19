import os
from dataclasses import dataclass
from typing import Dict, Optional

from backend.audit.audit_logger import AuditLogger
from config.security_config import SECURITY_CONFIG


@dataclass(frozen=True)
class SecretCredentials:
    scope: str
    api_key: str
    api_secret: str
    source_env_key: str
    source_env_secret: str


class SecretManager:
    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self.audit_logger = audit_logger or AuditLogger()

    def apply_runtime_env_bridge(self) -> Dict[str, Dict[str, str]]:
        bridge_report: Dict[str, Dict[str, str]] = {}
        for nexus_env, legacy_envs in SECURITY_CONFIG.runtime_env_bridge.items():
            nexus_value = os.getenv(nexus_env, "").strip()
            matched_legacy = ""
            for legacy_env in legacy_envs:
                legacy_value = os.getenv(legacy_env, "").strip()
                if nexus_value and not legacy_value:
                    os.environ[legacy_env] = nexus_value
                    matched_legacy = legacy_env
                    bridge_report[nexus_env] = {
                        "status": "bridged_to_legacy",
                        "target_env": legacy_env,
                        "value": self.mask_secret(nexus_value),
                    }
                    self.audit_logger.log_security_event(
                        actor="system",
                        action="security_env_bridge",
                        result="ALLOW",
                        risk_level="LOW",
                        metadata=bridge_report[nexus_env],
                    )
                    break
                if legacy_value:
                    matched_legacy = legacy_env
                    if not nexus_value:
                        bridge_report[nexus_env] = {
                            "status": "legacy_fallback_active",
                            "target_env": legacy_env,
                            "value": self.mask_secret(legacy_value),
                            "rotation_hint": "Future key migration only requires setting NEXUS_* env values.",
                        }
                        self.audit_logger.log_security_event(
                            actor="system",
                            action="security_env_migration_hint",
                            result="ALLOW",
                            risk_level="LOW",
                            metadata=bridge_report[nexus_env],
                        )
                    else:
                        bridge_report[nexus_env] = {
                            "status": "nexus_env_active",
                            "target_env": legacy_env,
                            "value": self.mask_secret(nexus_value),
                        }
                    break
            if nexus_env not in bridge_report:
                bridge_report[nexus_env] = {
                    "status": "missing",
                    "target_env": matched_legacy or ",".join(legacy_envs),
                    "value": "",
                }
        return bridge_report

    def get_read_credentials(self) -> SecretCredentials:
        creds = self._load_credentials(
            scope="READ",
            key_env=SECURITY_CONFIG.read_api_key_env,
            secret_env=SECURITY_CONFIG.read_api_secret_env,
            fallback_key_envs=SECURITY_CONFIG.legacy_env_aliases.get("READ_KEY", ()),
            fallback_secret_envs=SECURITY_CONFIG.legacy_env_aliases.get("READ_SECRET", ()),
        )
        self.audit_logger.log_secret_access(
            actor="system",
            secret_label="read_credentials",
            result="ALLOW",
            metadata={
                "scope": creds.scope,
                "api_key": self.mask_secret(creds.api_key),
                "source_env_key": creds.source_env_key,
            },
        )
        return creds

    def get_trade_credentials(self) -> SecretCredentials:
        creds = self._load_credentials(
            scope="TRADE",
            key_env=SECURITY_CONFIG.trade_api_key_env,
            secret_env=SECURITY_CONFIG.trade_api_secret_env,
            fallback_key_envs=SECURITY_CONFIG.legacy_env_aliases.get("TRADE_KEY", ()),
            fallback_secret_envs=SECURITY_CONFIG.legacy_env_aliases.get("TRADE_SECRET", ()),
        )
        self.audit_logger.log_secret_access(
            actor="system",
            secret_label="trade_credentials",
            result="ALLOW",
            metadata={
                "scope": creds.scope,
                "api_key": self.mask_secret(creds.api_key),
                "source_env_key": creds.source_env_key,
                "phase_guard": "Phase 0.1 isolation only",
            },
        )
        return creds

    def get_emergency_metadata(self) -> Dict[str, str]:
        metadata = {
            "scope": "EMERGENCY",
            "key_id": os.getenv(SECURITY_CONFIG.emergency_key_id_env, "").strip(),
            "contact": os.getenv(SECURITY_CONFIG.emergency_contact_env, "").strip(),
            "runbook": os.getenv(SECURITY_CONFIG.emergency_runbook_env, "").strip(),
        }
        self.audit_logger.log_secret_access(
            actor="system",
            secret_label="emergency_metadata",
            result="ALLOW",
            metadata=metadata,
        )
        return metadata

    def validate_key_scope(self, scope: str) -> bool:
        allowed = scope.upper() in SECURITY_CONFIG.allowed_key_scopes
        self.audit_logger.log_security_event(
            actor="system",
            action="validate_key_scope",
            result="ALLOW" if allowed else "DENY",
            risk_level="LOW" if allowed else "MEDIUM",
            metadata={"scope": scope.upper()},
        )
        return allowed

    def validate_startup_configuration(self, strict: bool = False) -> Dict[str, Dict[str, str]]:
        results: Dict[str, Dict[str, str]] = {}
        for label, loader in (
            ("READ", self.get_read_credentials),
            ("TRADE", self.get_trade_credentials),
        ):
            try:
                creds = loader()
                results[label] = {
                    "status": "configured",
                    "api_key": self.mask_secret(creds.api_key),
                    "source_env_key": creds.source_env_key,
                }
            except Exception as exc:
                results[label] = {"status": "missing", "error": str(exc)}
                self.audit_logger.log_validation_failure(
                    actor="system",
                    action="startup_secret_validation",
                    reason=str(exc),
                    metadata={"scope": label},
                )
                if strict:
                    raise

        emergency = self.get_emergency_metadata()
        results["EMERGENCY"] = {
            "status": "metadata_only" if emergency.get("key_id") else "missing",
            "key_id": self.mask_secret(emergency.get("key_id", "")),
        }
        return results

    def mask_secret(self, secret: str) -> str:
        if not secret:
            return ""
        if len(secret) <= SECURITY_CONFIG.mask_prefix + SECURITY_CONFIG.mask_suffix:
            return SECURITY_CONFIG.mask_token
        return (
            secret[: SECURITY_CONFIG.mask_prefix]
            + SECURITY_CONFIG.mask_token
            + secret[-SECURITY_CONFIG.mask_suffix :]
        )

    def rotate_key_placeholder(self, scope: str) -> Dict[str, str]:
        if not self.validate_key_scope(scope):
            raise ValueError(f"Unsupported key scope: {scope}")
        result = {
            "scope": scope.upper(),
            "status": "MANUAL_ROTATION_REQUIRED",
            "message": "Rotate the Binance key out-of-band and update environment variables.",
        }
        self.audit_logger.log_security_event(
            actor="system",
            action="rotate_key_placeholder",
            result="ALLOW",
            risk_level="HIGH",
            metadata=result,
        )
        return result

    def revoke_key_placeholder(self, scope: str) -> Dict[str, str]:
        if not self.validate_key_scope(scope):
            raise ValueError(f"Unsupported key scope: {scope}")
        result = {
            "scope": scope.upper(),
            "status": "MANUAL_REVOKE_REQUIRED",
            "message": "Revoke the Binance key manually in Binance console and confirm audit closure.",
        }
        self.audit_logger.log_security_event(
            actor="system",
            action="revoke_key_placeholder",
            result="ALLOW",
            risk_level="HIGH",
            metadata=result,
        )
        return result

    def _load_credentials(
        self,
        scope: str,
        key_env: str,
        secret_env: str,
        fallback_key_envs=(),
        fallback_secret_envs=(),
    ) -> SecretCredentials:
        api_key, source_key = self._first_present(key_env, fallback_key_envs)
        api_secret, source_secret = self._first_present(secret_env, fallback_secret_envs)
        if not api_key or not api_secret:
            raise RuntimeError(f"{scope} credentials are not fully configured")
        return SecretCredentials(
            scope=scope,
            api_key=api_key,
            api_secret=api_secret,
            source_env_key=source_key,
            source_env_secret=source_secret,
        )

    def _first_present(self, primary_env: str, fallbacks) -> tuple[str, str]:
        candidate_envs = (primary_env, *tuple(fallbacks))
        for env_name in candidate_envs:
            value = os.getenv(env_name, "").strip()
            if value:
                return value, env_name
        return "", primary_env


def initialize_security_foundation(strict: bool = False, audit_logger: Optional[AuditLogger] = None):
    logger = audit_logger or AuditLogger()
    manager = SecretManager(audit_logger=logger)
    bridge_report = manager.apply_runtime_env_bridge()
    summary = manager.validate_startup_configuration(strict=strict)
    startup_metadata = {
        "bridge": {
            env_name: {
                "status": details.get("status"),
                "target_env": details.get("target_env"),
                "value": details.get("value", ""),
            }
            for env_name, details in bridge_report.items()
        }
    }
    startup_metadata.update(
        {
            scope: {
                "status": details.get("status"),
                "api_key": details.get("api_key", ""),
                "key_id": details.get("key_id", ""),
            }
            for scope, details in summary.items()
        }
    )
    logger.log_security_event(
        actor="system",
        action="security_foundation_init",
        result="ALLOW",
        risk_level="LOW",
        metadata=startup_metadata,
    )
    return summary
