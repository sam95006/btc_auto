"""V16-A Trade Error Ontology V1 — unit, adversarial, and three-pass tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_trade_error_ontology_v1.ai_proposal import (  # noqa: E402
    apply_ai_proposal,
    attempt_ai_override,
)
from backend.nexus_trade_error_ontology_v1.classifier import (  # noqa: E402
    assert_loss_not_auto_bad,
    assert_win_not_auto_good,
    classify_trade_error,
    migrate_classification,
)
from backend.nexus_trade_error_ontology_v1.constants import (  # noqa: E402
    ARTIFACT_REL,
    ERROR_DIMENSIONS,
    HARD_BANS,
    OWNED_PATHS,
    PROCESS_CLASSES,
    SCHEMA,
    SCHEMA_REL,
)
from backend.nexus_trade_error_ontology_v1.fixtures import (  # noqa: E402
    expected_class_by_trade_id,
    labeled_fixture_controls,
)
from backend.nexus_trade_error_ontology_v1.gene_bank import (  # noqa: E402
    build_gene_bank,
    match_genes,
)
from backend.nexus_trade_error_ontology_v1.hard_bans import (  # noqa: E402
    HardBanViolation,
    assert_no_status_json_filenames,
    refuse_ai_override,
    refuse_exchange_write,
)
from backend.nexus_trade_error_ontology_v1.schema import (  # noqa: E402
    build_schema,
    validate_classification_record,
)
from backend.nexus_trade_error_ontology_v1.three_pass import run_three_passes  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def test_process_classes_and_dimensions():
    assert set(PROCESS_CLASSES) == {
        "GOOD_PROCESS_WIN",
        "GOOD_PROCESS_LOSS",
        "BAD_PROCESS_WIN",
        "BAD_PROCESS_LOSS",
        "UNAVOIDABLE_SHOCK",
        "INSUFFICIENT_EVIDENCE",
    }
    assert set(ERROR_DIMENSIONS) == {
        "DATA",
        "REGIME",
        "STRATEGY",
        "ENTRY",
        "EXIT",
        "EXECUTION",
        "LIQUIDITY",
        "COST",
        "AI_REASONING",
        "RISK",
        "PORTFOLIO",
        "INFRASTRUCTURE",
        "EXTERNAL_SHOCK",
    }
    assert "no_ai_override_of_deterministic_class" in HARD_BANS
    assert any("nexus_trade_error_ontology_v1" in p for p in OWNED_PATHS)


def test_migrate_legacy_classes():
    assert migrate_classification("UNDETERMINED") == "INSUFFICIENT_EVIDENCE"
    assert migrate_classification("UNDETERMINED_PROCESS") == "INSUFFICIENT_EVIDENCE"
    assert migrate_classification("BAD_PROCESS_WIN") == "BAD_PROCESS_WIN"
    assert migrate_classification("junk") == "INSUFFICIENT_EVIDENCE"


def test_gene_bank_covers_all_dimensions():
    bank = build_gene_bank()
    covered = {g["dimension"] for g in bank["genes"]}
    assert covered == set(ERROR_DIMENSIONS)
    assert bank["gene_count"] >= len(ERROR_DIMENSIONS)
    assert bank["policy"]["ai_cannot_override_deterministic"] is True
    assert bank["policy"]["supports_profitable_bad_process_win"] is True
    for g in bank["genes"]:
        assert g["evidence_ref_keys"]
        assert g["recurrence_signature_template"].startswith("DIM=")
        assert 0.0 <= g["causal_confidence_floor"] <= 1.0
        assert g["version"]


def test_schema_requires_core_fields():
    schema = build_schema()
    required = set(schema["required"])
    for field in (
        "evidence_refs",
        "severity",
        "avoidability",
        "recurrence_signature",
        "causal_confidence",
        "versioning",
        "classifier_authority",
        "deterministic_class",
    ):
        assert field in required
    assert schema["policy"]["deterministic_classifier_fallback"] is True


def test_fixture_matrix_matches_expected():
    expected = expected_class_by_trade_id()
    for pkt in labeled_fixture_controls():
        result = classify_trade_error(pkt)
        assert result["process_classification"] == expected[pkt["trade_id"]]
        assert result["process_classification"] == result["deterministic_class"]
        assert result["recurrence_signature"].startswith("RS|")
        assert isinstance(result["evidence_refs"], list)
        assert result["severity"] in {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
        assert result["avoidability"] in {
            "AVOIDABLE",
            "PARTIALLY_AVOIDABLE",
            "UNAVOIDABLE",
            "UNKNOWN",
        }
        assert 0.0 <= result["causal_confidence"] <= 1.0
        assert not validate_classification_record(result)


def test_profitable_bad_process_win():
    pkt = next(p for p in labeled_fixture_controls() if p["trade_id"] == "V16A_FIX_bad_cost_win")
    result = classify_trade_error(pkt)
    assert result["process_classification"] == "BAD_PROCESS_WIN"
    assert result["is_win"] is True
    assert result["is_bad_process"] is True
    assert result["is_good_process"] is False
    assert "COST" in result["dimensions"]
    assert assert_win_not_auto_good(pkt) is True


def test_good_process_loss_not_auto_bad():
    pkt = next(p for p in labeled_fixture_controls() if p["trade_id"] == "V16A_FIX_good_loss")
    result = classify_trade_error(pkt)
    assert result["process_classification"] == "GOOD_PROCESS_LOSS"
    assert result["is_loss"] is True
    assert result["is_bad_process"] is False
    assert assert_loss_not_auto_bad(pkt) is True


def test_unavoidable_shock():
    pkt = next(
        p for p in labeled_fixture_controls() if p["trade_id"] == "V16A_FIX_unavoidable_shock"
    )
    result = classify_trade_error(pkt)
    assert result["process_classification"] == "UNAVOIDABLE_SHOCK"
    assert result["avoidability"] == "UNAVOIDABLE"
    assert "EXTERNAL_SHOCK" in result["dimensions"]


def test_insufficient_evidence():
    pkt = next(p for p in labeled_fixture_controls() if p["trade_id"] == "V16A_FIX_insufficient")
    result = classify_trade_error(pkt)
    assert result["process_classification"] == "INSUFFICIENT_EVIDENCE"


def test_ai_proposes_cannot_override():
    pkt = next(p for p in labeled_fixture_controls() if p["trade_id"] == "V16A_FIX_bad_cost_win")
    with pytest.raises(HardBanViolation):
        attempt_ai_override(pkt, {"process_classification": "GOOD_PROCESS_WIN"})
    with pytest.raises(HardBanViolation):
        apply_ai_proposal(pkt, {"process_classification": "GOOD_PROCESS_WIN"}, allow_override=True)
    with pytest.raises(HardBanViolation):
        refuse_ai_override()

    merged = apply_ai_proposal(
        pkt,
        {
            "process_classification": "GOOD_PROCESS_WIN",
            "dimensions": ["COST", "AI_REASONING"],
            "narrative": "profit proves process",
        },
    )
    assert merged["process_classification"] == "BAD_PROCESS_WIN"
    assert merged["deterministic_class"] == "BAD_PROCESS_WIN"
    assert merged["ai_proposed_class"] == "GOOD_PROCESS_WIN"
    assert merged["classifier_authority"]["ai_can_override"] is False
    assert merged["classifier_authority"]["deterministic_is_final"] is True
    assert merged["classifier_authority"]["ai_disagreement"] is True
    assert merged["classifier_authority"]["fallback"] == "deterministic_classifier"


def test_match_genes_cost_gate():
    genes = match_genes(["cost_gate_failed"])
    assert any(g["gene_id"] == "TEG.COST.GATE_FAIL" for g in genes)


def test_hard_ban_exchange_write():
    with pytest.raises(HardBanViolation):
        refuse_exchange_write()


def test_no_status_json_in_owned_artifact_names():
    assert_no_status_json_filenames(
        [
            f"{ARTIFACT_REL}/gene_bank_v1.json",
            f"{ARTIFACT_REL}/trade_error_ontology_v1.schema.json",
            f"{ARTIFACT_REL}/three_pass_report.json",
        ]
    )
    with pytest.raises(HardBanViolation):
        assert_no_status_json_filenames([f"{ARTIFACT_REL}/v16a_status.json"])


def test_three_passes_pass(tmp_path: Path | None = None):
    report = run_three_passes(ROOT)
    assert report["overall_status"] == "PASS"
    assert len(report["passes"]) == 3
    assert all(p["status"] == "PASS" for p in report["passes"])

    schema_path = ROOT / SCHEMA_REL
    gene_path = ROOT / ARTIFACT_REL / "gene_bank_v1.json"
    assert schema_path.is_file()
    assert gene_path.is_file()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["schema_name"] == SCHEMA
    bank = json.loads(gene_path.read_text(encoding="utf-8"))
    assert bank["gene_count"] >= 13

    written = list((ROOT / ARTIFACT_REL).rglob("*"))
    names = [p.name for p in written if p.is_file()]
    assert not any(n.endswith("_status.json") for n in names)
    assert "three_pass_report.json" in names
    assert "NEXUS_FINAL_ACCELERATION_REPORT.json" not in names
