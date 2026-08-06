"""Gate runner for public/mobile contract parity."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_pub17_global_market_contracts.constants import (
    FRESHNESS_STATES as GLOBAL_FRESHNESS,
    REQUIRED_DTO_FIELDS,
)
from backend.nexus_pub17_global_market_contracts.dto import (
    build_all_normalized_dtos,
    validate_dto,
)
from backend.nexus_pub17_market_pulse.constants import FIRST_SCREEN_ANSWER_IDS
from backend.nexus_pub17_market_pulse.fixtures import catalog as pulse_catalog
from backend.nexus_pub17_market_pulse.service import build_first_screen
from backend.nexus_pub17_public_mobile_parity.constants import (
    FAIL_RECOMMENDATION,
    MOBILE_MARKET_PULSE_REQUIRED_FIELDS,
    PASS_RECOMMENDATION,
    PUBLIC_MARKET_PULSE_ANSWER_IDS,
    PUBLIC_NORMALIZED_SOURCE_DTO_FIELDS,
    SHARED_BUYABLE_PRODUCT_LABELS,
    SHARED_FORBIDDEN_PRODUCT_LABELS,
    SHARED_FRESHNESS_STATES,
)
from backend.nexus_pub17_public_mobile_parity.contract import (
    assert_provider_required_payload,
    assert_semantic_map_complete,
    assert_zero_trade_capabilities,
    build_parity_contract,
    validate_freshness_token,
    write_parity_contract_artifact,
)
from backend.nexus_pub17_public_mobile_parity.surface_scan import scan_member_control_surfaces
from backend.nexus_public_subscription_boundary.constants import (
    MEMBER_BUYABLE_PRODUCT_LABELS,
    MEMBER_FORBIDDEN_PRODUCT_LABELS,
)
from backend.nexus_public_subscription_boundary.dto import build_catalog_dto
from backend.nexus_public_subscription_boundary.execution_control import (
    count_member_execution_controls,
)


def run_parity_gate(root: Path | str) -> dict[str, Any]:
    root_path = Path(root)
    errors: list[str] = []
    contract = build_parity_contract()
    artifact_path = write_parity_contract_artifact(root_path)

    # 1) Semantic map completeness.
    errors.extend(assert_semantic_map_complete(contract))

    # 2) Public first-screen answer ids match frozen set.
    if list(FIRST_SCREEN_ANSWER_IDS) != list(PUBLIC_MARKET_PULSE_ANSWER_IDS):
        errors.append("public_pulse_answer_ids_mismatch")

    # 3) Global DTO field set parity with frozen contract.
    if list(REQUIRED_DTO_FIELDS) != list(PUBLIC_NORMALIZED_SOURCE_DTO_FIELDS):
        errors.append("normalized_dto_fields_mismatch")

    # 4) Freshness vocab: global states ⊆ shared; every pulse freshness token known.
    for state in GLOBAL_FRESHNESS:
        if state not in SHARED_FRESHNESS_STATES:
            errors.append(f"global_freshness_not_shared:{state}")
        errors.extend(validate_freshness_token(state))

    # 5) PROVIDER_REQUIRED honesty on pulse fixtures + normalized DTOs.
    provider_required_cases = 0
    for case in pulse_catalog():
        screen = build_first_screen(case)
        mode = str(case.get("mode") or "").upper()
        if mode == "PROVIDER_REQUIRED":
            provider_required_cases += 1
            errors.extend(
                assert_provider_required_payload(
                    {
                        "provider_status": "PROVIDER_REQUIRED",
                        "mode": mode,
                        "data_freshness": screen.get("data_freshness"),
                        "chrome_label": screen.get("chrome_label"),
                        "top_opportunities": [],
                        "fabricated": False,
                        "execution_control_count": 0,
                        "exchange_write_capability": 0,
                        "customer_trading_capability_count": 0,
                    }
                )
            )
            if str(screen.get("chrome_label") or "").upper() == "LIVE":
                errors.append(f"pulse_provider_required_live_chrome:{case.get('case_id')}")
            if str(screen.get("data_freshness") or "").upper() == "LIVE":
                errors.append(f"pulse_provider_required_live_freshness:{case.get('case_id')}")
        # Never fabricate Live chrome for any fixture case.
        if str(screen.get("chrome_label") or "").upper() == "LIVE":
            errors.append(f"pulse_fake_live_chrome:{case.get('case_id')}")
        errors.extend(assert_zero_trade_capabilities(screen))

    if provider_required_cases < 1:
        errors.append("missing_provider_required_pulse_fixture")

    for dto in build_all_normalized_dtos(retrieved_at="2026-08-06T02:00:00Z"):
        errors.extend(validate_dto(dto))
        if dto.get("status") == "PROVIDER_REQUIRED":
            errors.extend(assert_provider_required_payload(dto))
        if dto.get("freshness") == "LIVE" and not dto.get("value"):
            errors.append(f"live_freshness_without_value:{dto.get('domain')}")

    # 6) Subscription label parity (public ↔ shared contract ↔ mobile labels).
    if set(MEMBER_BUYABLE_PRODUCT_LABELS) != set(SHARED_BUYABLE_PRODUCT_LABELS):
        errors.append("buyable_labels_mismatch_public")
    if set(MEMBER_FORBIDDEN_PRODUCT_LABELS) != set(SHARED_FORBIDDEN_PRODUCT_LABELS):
        errors.append("forbidden_labels_mismatch_public")
    catalog = build_catalog_dto().to_dict()
    if int(catalog.get("member_execution_control_count") or 0) != 0:
        errors.append("catalog_execution_controls_nonzero")
    exec_counts = count_member_execution_controls()
    if int(exec_counts.get("member_execution_control_count") or 0) != 0:
        errors.append("member_execution_control_count_nonzero")

    # 7) Surface scan — no trade/copy/exchange controls.
    scan = scan_member_control_surfaces(root_path)
    if scan["survivor_count"] != 0:
        errors.append(f"control_survivors:{scan['survivor_count']}")

    # 8) Mobile field set non-empty freeze (contract itself).
    if len(MOBILE_MARKET_PULSE_REQUIRED_FIELDS) < 10:
        errors.append("mobile_field_set_too_small")

    status = "PASS" if not errors else "FAIL"
    return {
        "ok": status == "PASS",
        "status": status,
        "recommendation": PASS_RECOMMENDATION if status == "PASS" else FAIL_RECOMMENDATION,
        "errors": errors,
        "artifact": str(artifact_path).replace("\\", "/"),
        "contract_schema": contract["schema"],
        "provider_required_pulse_cases": provider_required_cases,
        "surface_scan": {
            "scanned_files": scan["scanned_files"],
            "survivor_count": scan["survivor_count"],
            "definition_hit_count": scan["definition_hit_count"],
            "survivors": scan["survivors"],
        },
        "counts": {
            "public_answer_ids": len(PUBLIC_MARKET_PULSE_ANSWER_IDS),
            "mobile_required_fields": len(MOBILE_MARKET_PULSE_REQUIRED_FIELDS),
            "shared_freshness_states": len(SHARED_FRESHNESS_STATES),
            "buyable_labels": len(SHARED_BUYABLE_PRODUCT_LABELS),
            "forbidden_labels": len(SHARED_FORBIDDEN_PRODUCT_LABELS),
        },
    }
