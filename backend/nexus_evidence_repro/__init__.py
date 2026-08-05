"""V12-E Evidence Reproducibility — Founder-private proof surface.

For completed *simulated* Decision lifecycles, bind and verify:
  input evidence hashes, code version, cost version, risk version,
  checkpoint version, AI Provider/model identifiers, deterministic
  replay result, and classification provenance.

No Demo/exchange, no profitability claims, no fabricated learning proofs.
"""
from __future__ import annotations

from backend.nexus_evidence_repro.constants import (
    PROOF_DIMENSIONS,
    REPRO_SCHEMA,
    RISK_GATES_VERSION,
)
from backend.nexus_evidence_repro.envelope import (
    ReproEnvelopeError,
    build_repro_envelope,
    verify_repro_envelope,
)
from backend.nexus_evidence_repro.replay import (
    ReplayMismatchError,
    deterministic_replay_fingerprint,
    run_completed_simulated_lifecycle,
    verify_deterministic_replay,
)
from backend.nexus_evidence_repro.versions import resolve_version_pins

__all__ = [
    "PROOF_DIMENSIONS",
    "REPRO_SCHEMA",
    "RISK_GATES_VERSION",
    "ReproEnvelopeError",
    "ReplayMismatchError",
    "build_repro_envelope",
    "deterministic_replay_fingerprint",
    "resolve_version_pins",
    "run_completed_simulated_lifecycle",
    "verify_deterministic_replay",
    "verify_repro_envelope",
]
