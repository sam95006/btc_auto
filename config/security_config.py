from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class SecurityConfig:
    read_api_key_env: str = "NEXUS_READ_BINANCE_API_KEY"
    read_api_secret_env: str = "NEXUS_READ_BINANCE_SECRET_KEY"
    trade_api_key_env: str = "NEXUS_TRADE_BINANCE_API_KEY"
    trade_api_secret_env: str = "NEXUS_TRADE_BINANCE_SECRET_KEY"
    emergency_key_id_env: str = "NEXUS_EMERGENCY_BINANCE_KEY_ID"
    emergency_contact_env: str = "NEXUS_EMERGENCY_CONTACT"
    emergency_runbook_env: str = "NEXUS_EMERGENCY_RUNBOOK"
    read_scope_env: str = "NEXUS_READ_KEY_SCOPE"
    trade_scope_env: str = "NEXUS_TRADE_KEY_SCOPE"
    emergency_scope_env: str = "NEXUS_EMERGENCY_KEY_SCOPE"
    allowed_key_scopes: Tuple[str, ...] = ("READ", "TRADE", "EMERGENCY")
    mask_prefix: int = 4
    mask_suffix: int = 4
    mask_token: str = "****"
    audit_log_path_env: str = "NEXUS_AUDIT_LOG_PATH"
    audit_log_path_default: str = "logs/security_audit.log"
    audit_enabled_env: str = "NEXUS_AUDIT_ENABLED"
    audit_enabled_default: bool = True
    request_validation_enabled_env: str = "NEXUS_REQUEST_VALIDATION_ENABLED"
    request_validation_enabled_default: bool = True
    forbidden_log_fields: Tuple[str, ...] = (
        "api_key",
        "api_secret",
        "secret",
        "secret_key",
        "binance_api_key",
        "binance_secret_key",
        "passphrase",
        "password",
        "private_key",
        "token",
        "authorization",
    )
    sensitive_value_markers: Tuple[str, ...] = (
        "api_key",
        "secret",
        "private_key",
        "passphrase",
        "authorization",
        "token",
    )
    forbidden_payload_patterns: Tuple[str, ...] = (
        "<script",
        "</script>",
        "javascript:",
        "__import__(",
        "os.system",
        "subprocess.",
        "rm -rf",
        "powershell -",
        "cmd /c",
        "curl ",
        "wget ",
        "ignore previous instructions",
        "reveal the secret",
    )
    read_request_required_fields: Tuple[str, ...] = ("actor", "resource")
    admin_request_required_fields: Tuple[str, ...] = ("actor", "action", "justification")
    trade_proposal_required_fields: Tuple[str, ...] = (
        "actor",
        "fleet",
        "symbol",
        "side",
        "proposal_id",
    )
    high_risk_actions: Tuple[str, ...] = ("rotate_key", "revoke_key", "admin_override")
    legacy_env_aliases: Dict[str, Tuple[str, ...]] = field(
        default_factory=lambda: {
            "READ_KEY": ("BINANCE_SPOT_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_KEY"),
            "READ_SECRET": ("BINANCE_SPOT_TESTNET_SECRET_KEY", "BINANCE_FUTURES_TESTNET_SECRET_KEY"),
            "TRADE_KEY": ("BINANCE_FUTURES_TESTNET_API_KEY",),
            "TRADE_SECRET": ("BINANCE_FUTURES_TESTNET_SECRET_KEY",),
        }
    )
    runtime_env_bridge: Dict[str, Tuple[str, ...]] = field(
        default_factory=lambda: {
            "NEXUS_READ_BINANCE_API_KEY": ("BINANCE_SPOT_TESTNET_API_KEY",),
            "NEXUS_READ_BINANCE_SECRET_KEY": ("BINANCE_SPOT_TESTNET_SECRET_KEY",),
            "NEXUS_TRADE_BINANCE_API_KEY": ("BINANCE_FUTURES_TESTNET_API_KEY",),
            "NEXUS_TRADE_BINANCE_SECRET_KEY": ("BINANCE_FUTURES_TESTNET_SECRET_KEY",),
        }
    )


SECURITY_CONFIG = SecurityConfig()


def get_forbidden_log_fields() -> List[str]:
    return list(SECURITY_CONFIG.forbidden_log_fields)
