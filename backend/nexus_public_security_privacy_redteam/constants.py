"""PUB2-H Public Security & Privacy Red Team — constants."""
from __future__ import annotations

LANE = "PUB2-H"
LANE_NAME = "PUBLIC_SECURITY_AND_PRIVACY_REDTEAM"
PACKAGE = "NEXUS_PUBLIC_V2_SECURITY_PRIVACY_REDTEAM"
SCHEMA = "public_security_privacy_redteam_v1"
BRANCH = "feature/public-v2-security-privacy-redteam"
BASE_COMMIT = "5e93f677ece9f283aeade98657b5e3d5736991b5"

ATTACK_IDS: tuple[str, ...] = (
    "private_field_leakage",
    "timing_leakage",
    "aggregation_inference",
    "shared_auth",
    "member_privilege_escalation",
    "cross_org_access",
    "decision_data_enumeration",
    "secret_leakage",
    "public_exchange_write_path",
    "prompt_lesson_leakage",
)

HARD_BANS: frozenset[str] = frozenset(
    {
        "no_pr26_merge",
        "no_pr27_merge",
        "no_private_core_exposure",
        "no_exchange_write",
        "no_demo_trading",
        "no_shadow_trading",
        "no_mainnet",
        "no_real_money",
        "no_fabricated_customers",
        "no_fabricated_metrics",
        "no_human_facing_status_json",
        "no_acceleration_report_edit",
        "no_shared_private_jwt",
        "no_private_admin_session_reuse",
        "no_live_billing",
    }
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_public_security_privacy_redteam/",
    "backend/nexus_public_auth/org_access.py",
    "tests/public_security_privacy/",
    "tools/public/run_pub2_h_security_privacy_redteam.py",
)

# Paths the red-team may harden as part of findings remediation.
REMEDIATION_PATHS: tuple[str, ...] = (
    "backend/nexus_public_auth/",
    "backend/nexus_public_decision_cloud/",
    "backend/nexus_publishing_gateway/",
)

FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "backend.trading",
    "backend.wallet",
    "backend.fleets",
    "backend.nexus_demo_execution",
    "backend.nexus_execution",
    "backend.nexus_autonomy",
    "backend.nexus_research",
    "ccxt",
    "pybit",
)

DISPOSITION_FIXED = "FIXED"
DISPOSITION_EXPLICITLY_BLOCKED = "EXPLICITLY_BLOCKED"
DISPOSITION_SURVIVOR = "SURVIVOR"
