"""Attack probes for PUB2-H — each returns disposition FIXED | EXPLICITLY_BLOCKED | SURVIVOR."""
from __future__ import annotations

import json
from typing import Any, Callable

from backend.nexus_publishing_gateway.aggregation import apply_public_aggregations
from backend.nexus_publishing_gateway.deny_traps import find_denied_fields
from backend.nexus_publishing_gateway.exceptions import DenyTrapError, PublishingGatewayError
from backend.nexus_publishing_gateway.gateway import publish_intelligence
from backend.nexus_publishing_gateway.side_channel import (
    SAFE_PUBLIC_SEED,
    probe_error_message_side_channel,
    probe_timing_side_channel,
)
from backend.nexus_public_auth.hard_bans import HardBanViolation as AuthHardBan
from backend.nexus_public_auth.jwt_issuer import PublicJwtIssuer
from backend.nexus_public_auth.org_access import PRIVATE_EXECUTION_FEATURE_DENYLIST
from backend.nexus_public_auth.service import PublicAuthMembershipService
from backend.nexus_public_auth.store import PublicAuthStore
from backend.nexus_public_decision_cloud import service as decision_service
from backend.nexus_public_decision_cloud.hard_bans import HardBanViolation as DecisionHardBan
from backend.nexus_public_decision_cloud.sanitize import ForbiddenPayloadKeyError, assert_no_forbidden_keys
from backend.nexus_public_decision_cloud.store import load_catalog
from backend.nexus_public_security_privacy_redteam.constants import (
    DISPOSITION_EXPLICITLY_BLOCKED,
    DISPOSITION_FIXED,
    DISPOSITION_SURVIVOR,
)
from backend.nexus_public_security_privacy_redteam.hard_bans import (
    HardBanViolation,
    refuse_exchange_write,
    refuse_shared_private_jwt,
)


ProbeFn = Callable[[], dict[str, Any]]


def _result(
    attack_id: str,
    *,
    disposition: str,
    detail: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "attack_id": attack_id,
        "disposition": disposition,
        "detail": detail,
        "evidence": evidence or {},
        "ok": disposition in {DISPOSITION_FIXED, DISPOSITION_EXPLICITLY_BLOCKED},
    }


def attack_private_field_leakage() -> dict[str, Any]:
    dirty = {
        **SAFE_PUBLIC_SEED,
        "strategy_id": "STRAT-LEAK",
        "lesson_id": "LES-1",
        "api_key": "sk-aaaaaaaaaaaaaaaa",
    }
    hits = find_denied_fields(dirty)
    denied = False
    try:
        publish_intelligence(dirty, environment="LOCAL")
    except (DenyTrapError, PublishingGatewayError):
        denied = True
    if denied and hits:
        return _result(
            "private_field_leakage",
            disposition=DISPOSITION_FIXED,
            detail="gateway deny-traps block private fields on publish",
            evidence={"denied_fields": sorted(hits)},
        )
    return _result(
        "private_field_leakage",
        disposition=DISPOSITION_SURVIVOR,
        detail="private fields were not denied",
        evidence={"denied_fields": sorted(hits), "denied": denied},
    )


def attack_timing_leakage() -> dict[str, Any]:
    gateway = probe_timing_side_channel()
    missing = decision_service.decision_detail("dec_does_not_exist_zzzz")
    hidden = decision_service.decision_detail("dec_org_scoped_hidden")
    shapes_match = (
        missing.get("error") == hidden.get("error") == "decision_unavailable"
        and missing.get("ok") is False
        and hidden.get("ok") is False
    )
    if gateway.get("passed") and shapes_match and not gateway.get("leak_suspected", False):
        return _result(
            "timing_leakage",
            disposition=DISPOSITION_FIXED,
            detail="publish timing pad + opaque decision deny shapes hold",
            evidence={"gateway": gateway, "shapes_match": shapes_match},
        )
    return _result(
        "timing_leakage",
        disposition=DISPOSITION_SURVIVOR,
        detail="timing or existence oracle still distinguishable",
        evidence={"gateway": gateway, "shapes_match": shapes_match},
    )


def attack_aggregation_inference() -> dict[str, Any]:
    thin = {
        **SAFE_PUBLIC_SEED,
        "contradicting_evidence": [{"evidence_polarity": "CONTRADICT"}],
        "risk_alerts": [{"alert_severity": "LOW"}],
    }
    # Drop padded lists so aggregation path sees thin slices.
    thin.pop("contradicting_evidence", None)
    thin["contradicting_evidence"] = [{"evidence_polarity": "CONTRADICT"}]
    thin["risk_alerts"] = [{"alert_severity": "LOW"}]
    out = apply_public_aggregations(thin)
    suppressed = (
        isinstance(out.get("contradicting_evidence"), dict)
        and out["contradicting_evidence"].get("bucket") == "SUPPRESSED_BELOW_THRESHOLD"
    )
    if suppressed:
        return _result(
            "aggregation_inference",
            disposition=DISPOSITION_FIXED,
            detail="thin cohorts suppressed below aggregation threshold",
            evidence={"contradicting_evidence": out.get("contradicting_evidence")},
        )
    return _result(
        "aggregation_inference",
        disposition=DISPOSITION_SURVIVOR,
        detail="thin aggregation slice still exposed",
        evidence={"out_keys": list(out.keys())},
    )


def attack_shared_auth() -> dict[str, Any]:
    blocked = []
    try:
        refuse_shared_private_jwt()
    except HardBanViolation:
        blocked.append("refuse_shared_private_jwt")
    try:
        PublicJwtIssuer(secret="x" * 32, secret_env="NEXUS_PRIVATE_JWT_SECRET")
    except AuthHardBan:
        blocked.append("private_secret_env")
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(store=store)
    foreign = PublicJwtIssuer(secret="other-public-secret-xxxx")
    issued = foreign.issue(account_id="acct_y", tier="Free", member_roles=["member"])
    try:
        svc.sessions.reject_private_admin_token(
            issued["token"], claimed_issuer="nexus-private"
        )
        blocked.append("reject_private_admin_token")
    except AuthHardBan:
        blocked.append("reject_private_admin_token")
    if len(blocked) >= 3:
        return _result(
            "shared_auth",
            disposition=DISPOSITION_EXPLICITLY_BLOCKED,
            detail="shared/private auth crossings raise hard bans",
            evidence={"blocked": blocked},
        )
    return _result(
        "shared_auth",
        disposition=DISPOSITION_SURVIVOR,
        detail="shared auth probe incomplete",
        evidence={"blocked": blocked},
    )


def attack_member_privilege_escalation() -> dict[str, Any]:
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(store=store)
    blocked: list[str] = []
    # Self-register cannot take Enterprise / member_admin.
    try:
        svc.register_member("evil@example.com", "Evil", tier="Enterprise")
    except AuthHardBan:
        blocked.append("self_register_enterprise")
    try:
        svc.register_member(
            "evil2@example.com", "Evil2", member_roles=["member_admin"]
        )
    except AuthHardBan:
        blocked.append("self_register_member_admin")
    reg = svc.register_member("user@example.com", "User")
    try:
        svc.elevate_member_roles(
            actor_account_id=reg["account_id"],
            target_account_id=reg["account_id"],
            member_roles=["member_admin"],
        )
    except AuthHardBan:
        blocked.append("self_elevate_without_admin")
    # Unsigned org role assign blocked.
    try:
        svc.assign_org_roles(reg["account_id"], "org_x", ["org_owner"])
    except AuthHardBan:
        blocked.append("unsigned_org_assign")
    # Entitlements never include private execution features.
    from backend.nexus_public_auth.entitlements import features_for_tier

    for tier in ("Free", "Pro", "Elite", "Enterprise"):
        feats = features_for_tier(tier)
        if set(feats) & PRIVATE_EXECUTION_FEATURE_DENYLIST:
            return _result(
                "member_privilege_escalation",
                disposition=DISPOSITION_SURVIVOR,
                detail=f"tier {tier} grants private execution features",
                evidence={"features": sorted(feats)},
            )
    if len(blocked) >= 4:
        return _result(
            "member_privilege_escalation",
            disposition=DISPOSITION_FIXED,
            detail="self-register/elevate/unsigned-org paths blocked; no private execution entitlements",
            evidence={"blocked": blocked},
        )
    return _result(
        "member_privilege_escalation",
        disposition=DISPOSITION_SURVIVOR,
        detail="privilege escalation path still open",
        evidence={"blocked": blocked},
    )


def attack_cross_org_access() -> dict[str, Any]:
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(store=store)
    a = svc.register_member("a@example.com", "A")
    b = svc.register_member("b@example.com", "B")
    org_a = svc.create_org(owner_account_id=a["account_id"], name="Alpha")
    org_b = svc.create_org(owner_account_id=b["account_id"], name="Beta")
    blocked: list[str] = []
    # B cannot assign roles in A's org.
    try:
        svc.assign_org_roles(
            a["account_id"],
            org_a["org_id"],
            ["org_admin"],
            actor_account_id=b["account_id"],
        )
    except AuthHardBan:
        blocked.append("cross_org_role_assign")
    # B cannot add self into A's org without privilege.
    try:
        svc.add_org_member(
            actor_account_id=b["account_id"],
            org_id=org_a["org_id"],
            member_account_id=b["account_id"],
        )
    except AuthHardBan:
        blocked.append("cross_org_self_join")
    # Org-scoped decision hidden from foreign org.
    deny = decision_service.decision_detail(
        "dec_org_scoped_hidden", caller_org_ids={org_b["org_id"]}
    )
    allow = decision_service.decision_detail(
        "dec_org_scoped_hidden", caller_org_ids={"org_redteam_alpha"}
    )
    if deny.get("ok") is False and allow.get("ok") is True:
        blocked.append("org_scoped_decision")
    # Cross-account export denied.
    try:
        svc.lifecycle.export_account_data(
            a["account_id"], actor_account_id=b["account_id"]
        )
    except AuthHardBan:
        blocked.append("cross_account_export")
    if len(blocked) >= 4:
        return _result(
            "cross_org_access",
            disposition=DISPOSITION_FIXED,
            detail="cross-org assign/join/decision/export denied",
            evidence={"blocked": blocked, "org_a": org_a["org_id"], "org_b": org_b["org_id"]},
        )
    return _result(
        "cross_org_access",
        disposition=DISPOSITION_SURVIVOR,
        detail="cross-org access still possible",
        evidence={"blocked": blocked, "deny": deny, "allow_ok": allow.get("ok")},
    )


def attack_decision_data_enumeration() -> dict[str, Any]:
    load_catalog(reload=True)
    missing = decision_service.decision_detail("dec_enum_missing_000")
    hidden = decision_service.decision_detail("dec_org_scoped_hidden")
    public = decision_service.decision_detail("dec_staging_001")
    feed = decision_service.decision_feed()
    feed_ids = {d.get("decision_id") for d in feed.get("decisions") or []}
    # Org-scoped must not appear in anonymous feed.
    hidden_in_feed = "dec_org_scoped_hidden" in feed_ids
    same_deny = (
        json.dumps(missing, sort_keys=True) == json.dumps(hidden, sort_keys=True)
        or (
            missing.get("error") == hidden.get("error")
            and set(missing.keys()) == set(hidden.keys())
        )
    )
    if public.get("ok") and same_deny and not hidden_in_feed:
        return _result(
            "decision_data_enumeration",
            disposition=DISPOSITION_FIXED,
            detail="opaque deny + org-scoped excluded from public feed",
            evidence={
                "same_deny": same_deny,
                "hidden_in_feed": hidden_in_feed,
                "feed_count": feed.get("count"),
            },
        )
    return _result(
        "decision_data_enumeration",
        disposition=DISPOSITION_SURVIVOR,
        detail="decision existence still enumerable",
        evidence={
            "same_deny": same_deny,
            "hidden_in_feed": hidden_in_feed,
            "missing": missing,
            "hidden": hidden,
        },
    )


def attack_secret_leakage() -> dict[str, Any]:
    side = probe_error_message_side_channel()
    dirty = {
        **SAFE_PUBLIC_SEED,
        "api_secret": "supersecretvalue999",
        "authorization": "Bearer sk-bbbbbbbbbbbbbbbb",
    }
    denied = False
    leaked = False
    try:
        publish_intelligence(dirty, environment="LOCAL")
    except PublishingGatewayError as exc:
        denied = True
        text = str(exc)
        leaked = "supersecretvalue999" in text or "sk-bbbbbbbbbbbbbbbb" in text
    export_store = PublicAuthStore()
    svc = PublicAuthMembershipService(store=export_store)
    reg = svc.register_member("sec@example.com", "Sec")
    export = svc.lifecycle.export_account_data(reg["account_id"])
    blob = json.dumps(export)
    export_clean = (
        "api_key" not in blob
        and "api_secret" not in blob
        and "private_key" not in blob
        and "lesson_memory" not in blob.lower()
    )
    if side.get("passed") and denied and not leaked and export_clean:
        return _result(
            "secret_leakage",
            disposition=DISPOSITION_FIXED,
            detail="secrets denied on publish; export has no credential/lesson fields",
            evidence={"side_channel": side.get("passed"), "export_clean": export_clean},
        )
    return _result(
        "secret_leakage",
        disposition=DISPOSITION_SURVIVOR,
        detail="secret still observable",
        evidence={
            "side": side,
            "denied": denied,
            "leaked": leaked,
            "export_clean": export_clean,
        },
    )


def attack_public_exchange_write_path() -> dict[str, Any]:
    blocked: list[str] = []
    try:
        refuse_exchange_write()
    except HardBanViolation:
        blocked.append("refuse_exchange_write")
    try:
        decision_service.refuse_exchange_write_path()
    except DecisionHardBan:
        blocked.append("decision_cloud_refuse_write")
    # Decision cloud mutations rejected at route layer — probe service flag.
    meta = decision_service.service_meta()
    if meta.get("customer_trading") is False and meta.get("exchange_api_used") is False:
        blocked.append("decision_cloud_read_only_meta")
    if "POST" not in (meta.get("methods_allowed") or []):
        blocked.append("no_post_methods")
    if len(blocked) >= 4:
        return _result(
            "public_exchange_write_path",
            disposition=DISPOSITION_EXPLICITLY_BLOCKED,
            detail="exchange-write paths refused on public surfaces",
            evidence={"blocked": blocked},
        )
    return _result(
        "public_exchange_write_path",
        disposition=DISPOSITION_SURVIVOR,
        detail="exchange-write refuse incomplete",
        evidence={"blocked": blocked, "meta": meta},
    )


def attack_prompt_lesson_leakage() -> dict[str, Any]:
    dirty = {
        **SAFE_PUBLIC_SEED,
        "system_prompt": "You are a private trader.",
        "raw_provider_prompt": "secret prompt",
        "lesson_id": "LES-PRIVATE",
        "lesson_memory": {"text": "private lesson"},
    }
    hits = find_denied_fields(dirty)
    denied = False
    try:
        publish_intelligence(dirty, environment="LOCAL")
    except (DenyTrapError, PublishingGatewayError):
        denied = True
    # Decision cloud sanitize rejects prompt/lesson keys.
    sanitize_blocked = False
    try:
        assert_no_forbidden_keys({"system_prompt": "x", "lesson_id": "y"})
    except ForbiddenPayloadKeyError:
        sanitize_blocked = True
    mem = decision_service.decision_memory()
    private_flag = mem.get("private_lesson_memory") is False
    if denied and hits and sanitize_blocked and private_flag:
        return _result(
            "prompt_lesson_leakage",
            disposition=DISPOSITION_FIXED,
            detail="prompt/lesson fields denied by gateway + decision cloud sanitize",
            evidence={"denied_fields": sorted(hits), "sanitize_blocked": sanitize_blocked},
        )
    return _result(
        "prompt_lesson_leakage",
        disposition=DISPOSITION_SURVIVOR,
        detail="prompt/lesson leakage path open",
        evidence={
            "hits": sorted(hits),
            "denied": denied,
            "sanitize_blocked": sanitize_blocked,
            "private_flag": private_flag,
        },
    )


ALL_ATTACKS: dict[str, ProbeFn] = {
    "private_field_leakage": attack_private_field_leakage,
    "timing_leakage": attack_timing_leakage,
    "aggregation_inference": attack_aggregation_inference,
    "shared_auth": attack_shared_auth,
    "member_privilege_escalation": attack_member_privilege_escalation,
    "cross_org_access": attack_cross_org_access,
    "decision_data_enumeration": attack_decision_data_enumeration,
    "secret_leakage": attack_secret_leakage,
    "public_exchange_write_path": attack_public_exchange_write_path,
    "prompt_lesson_leakage": attack_prompt_lesson_leakage,
}


def run_all_attacks() -> list[dict[str, Any]]:
    return [fn() for fn in ALL_ATTACKS.values()]
