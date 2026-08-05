"""Two-pass adversarial review for PUB-L package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.public_mobile_release.android_config_gate import validate_android_config
from backend.public_mobile_release.hard_bans import BanFinding
from backend.public_mobile_release.ios_config_gate import validate_ios_config
from backend.public_mobile_release.package_gate import package_root, repo_root, run_package_gate
from backend.public_mobile_release.regional_flags import GLOBAL_BAN_KEYS, RegionalFlagEngine
from backend.public_mobile_release.yaml_lite import load_simple_yaml


@dataclass
class PassResult:
    name: str
    findings: list[BanFinding]

    @property
    def ok(self) -> bool:
        return not self.findings


def pass1_completeness(root: Path | None = None) -> PassResult:
    return PassResult("pass1_completeness", run_package_gate(root))


def pass2_adversarial(root: Path | None = None) -> PassResult:
    root = root or repo_root()
    pkg = package_root(root)
    findings: list[BanFinding] = []

    # Identifiers must separate env bundle ids
    ids = load_simple_yaml(pkg / "identifiers" / "app_ids.yaml")
    ios = ids.get("ios") or {}
    android = ids.get("android") or {}
    if ios.get("bundle_id") == ios.get("bundle_id_dev"):
        findings.append(BanFinding("ID_COLLISION", "app_ids.yaml", "ios bundle_id == bundle_id_dev"))
    if android.get("application_id") == android.get("application_id_dev"):
        findings.append(BanFinding("ID_COLLISION", "app_ids.yaml", "android application_id collision"))

    # Regional engine must force billing false
    engine = RegionalFlagEngine.from_package(pkg)
    for region in ("US", "EU", "TW", "CN", "ZZ"):
        decision = engine.evaluate(region)
        for key in GLOBAL_BAN_KEYS:
            if decision.flags.get(key) is True:
                findings.append(BanFinding("REGIONAL_BAN_LEAK", region, key))
        if decision.flags.get("subscription_purchase_ui") is True:
            findings.append(BanFinding("SUBSCRIPTION_UI_ENABLED", region, "must be false"))

    # Subscription state file must keep billing false
    sub = load_simple_yaml(pkg / "subscriptions" / "restore_cancel_refund_states.yaml")
    if sub.get("live_billing_enabled") is True or sub.get("real_iap_products_enabled") is True:
        findings.append(BanFinding("SUBSCRIPTION_BILLING_ENABLED", "restore_cancel_refund_states.yaml", "true"))

    # CI must deny status json + store upload
    ci = load_simple_yaml(pkg / "ci" / "pipeline_spec.yaml")
    if ci.get("publish_to_stores") is True:
        findings.append(BanFinding("CI_PUBLISH_STORES", "pipeline_spec.yaml", "true"))
    forbidden = ci.get("forbidden_ci_steps") or []
    for required in ("upload_to_app_store", "upload_to_play_store", "fastlane_deliver"):
        if required not in forbidden:
            findings.append(BanFinding("CI_FORBIDDEN_STEP_MISSING", "pipeline_spec.yaml", required))

    # Platform gates
    ios_findings, _ = validate_ios_config(root)
    findings.extend(ios_findings)
    findings.extend(validate_android_config(root))

    # Draft docs must not claim legal approval
    for rel in (
        "privacy/data_safety_draft.md",
        "privacy/financial_disclosure_draft.md",
        "privacy/age_rating_draft.md",
    ):
        text = (pkg / rel).read_text(encoding="utf-8").lower()
        if "legal approval claimed:** yes" in text or "legal approval claimed: yes" in text:
            findings.append(BanFinding("LEGAL_CLAIM", rel, "yes"))
        if "not_legal_advice" not in text and "not legal advice" not in text and "no_legal_approval" not in text:
            if "legal approval claimed:** no" not in text and "legal approval claimed: no" not in text:
                findings.append(BanFinding("MISSING_LEGAL_DISCLAIMER", rel, "disclaimer"))

    # Deletion contract forbids private paths
    deletion = load_simple_yaml(pkg / "deletion" / "deletion_api_contract.yaml")
    forbidden_paths = deletion.get("forbidden") or []
    # yaml_lite may parse forbidden as list of dicts or scalars
    serialized = str(forbidden_paths).lower()
    for needle in ("/private/", "/execution/", "/lesson-memory/"):
        if needle not in serialized:
            findings.append(BanFinding("DELETION_FORBIDDEN_PATH_MISSING", "deletion_api_contract.yaml", needle))

    return PassResult("pass2_adversarial", findings)


def run_two_passes(root: Path | None = None) -> list[PassResult]:
    return [pass1_completeness(root), pass2_adversarial(root)]


def main() -> int:
    results = run_two_passes()
    failed = False
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"{result.name}:{status}:findings={len(result.findings)}")
        for f in result.findings:
            print(f"  {f.code} {f.path} :: {f.detail}")
            failed = True
    print("TWO_PASS_PASS" if not failed else "TWO_PASS_FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
