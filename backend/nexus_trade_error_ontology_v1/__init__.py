"""V16-A Trade Error Ontology V1 — machine-readable gene bank + deterministic classifier."""
from __future__ import annotations

from backend.nexus_trade_error_ontology_v1.ai_proposal import apply_ai_proposal, attempt_ai_override
from backend.nexus_trade_error_ontology_v1.classifier import (
    assert_loss_not_auto_bad,
    assert_win_not_auto_good,
    classify_trade_error,
    migrate_classification,
)
from backend.nexus_trade_error_ontology_v1.constants import (
    ARTIFACT_REL,
    BRANCH,
    ERROR_DIMENSIONS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    ONTOLOGY_VERSION,
    OWNED_PATHS,
    PROCESS_CLASSES,
    SCHEMA,
    SCHEMA_REL,
)
from backend.nexus_trade_error_ontology_v1.gene_bank import build_gene_bank, match_genes
from backend.nexus_trade_error_ontology_v1.schema import build_schema, validate_classification_record
from backend.nexus_trade_error_ontology_v1.three_pass import run_three_passes

__all__ = [
    "SCHEMA",
    "SCHEMA_REL",
    "ONTOLOGY_VERSION",
    "LANE",
    "LANE_NAME",
    "BRANCH",
    "OWNED_PATHS",
    "HARD_BANS",
    "ARTIFACT_REL",
    "PROCESS_CLASSES",
    "ERROR_DIMENSIONS",
    "build_schema",
    "build_gene_bank",
    "match_genes",
    "classify_trade_error",
    "migrate_classification",
    "apply_ai_proposal",
    "attempt_ai_override",
    "assert_loss_not_auto_bad",
    "assert_win_not_auto_good",
    "validate_classification_record",
    "run_three_passes",
]
