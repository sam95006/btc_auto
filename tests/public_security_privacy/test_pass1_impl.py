"""PUB2-H Pass 1 — implementation verification of security/privacy fixes."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_public_security_privacy_redteam import run_pass

ROOT = Path(__file__).resolve().parents[2]


def test_pass1_all_attacks_resolved():
    result = run_pass(1, ROOT)
    assert result["ok"] is True
    assert result["summary"]["survivor_count"] == 0
    assert result["summary"]["finding_count"] == 10
    dispositions = {f["attack_id"]: f["disposition"] for f in result["findings"]}
    assert dispositions["private_field_leakage"] == "FIXED"
    assert dispositions["member_privilege_escalation"] == "FIXED"
    assert dispositions["cross_org_access"] == "FIXED"
    assert dispositions["decision_data_enumeration"] == "FIXED"
    assert dispositions["shared_auth"] == "EXPLICITLY_BLOCKED"
    assert dispositions["public_exchange_write_path"] == "EXPLICITLY_BLOCKED"
