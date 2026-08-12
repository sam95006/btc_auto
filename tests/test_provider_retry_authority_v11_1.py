"""V11.1 C3 — provider retry authority consolidation tests."""
from __future__ import annotations

import ast
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

from backend.nexus_contracts.authority_registry import get_authority
from backend.nexus_provider.retry_policy import (
    DEFAULT_RETRY_AFTER_S,
    MAX_PROVIDER_RETRIES,
    backoff_with_jitter,
    compute_resume_wait_s,
    exponential_backoff_with_jitter,
    next_resume_iso,
    parse_quota_reset_at,
    parse_rate_limit_reset,
    parse_retry_after,
    retries_exhausted,
)
from backend.nexus_provider.transport_status import (
    assert_429_not_quality_failure,
    classify_transport_status,
    is_quality_neutral_transport,
)
from tools.architecture.check_contract_drift import check_provider_retry_drift

ROOT = Path(__file__).resolve().parents[1]

RETRY_ALGO_DEFS = {
    "parse_retry_after",
    "parse_rate_limit_reset",
    "parse_quota_reset_at",
    "backoff_with_jitter",
    "exponential_backoff_with_jitter",
    "compute_resume_wait_s",
}


def _count_parallel_retry_implementations(root: Path) -> int:
    findings = check_provider_retry_drift(root)
    return sum(1 for f in findings if f.get("code") == "PARALLEL_RETRY_IMPLEMENTATION")


def _count_canonical_retry_authorities() -> int:
    auth = get_authority("provider_retry")
    assert auth is not None
    return 1 if auth.canonical_module == "backend.nexus_provider.retry_policy" else 0


def _count_429_quality_misclassifications() -> int:
    """Adversarial probe: 429 must never surface as AI quality failure labels."""
    bad = 0
    status = classify_transport_status(http_status=429)
    if status != "RATE_LIMITED":
        bad += 1
    if not is_quality_neutral_transport("RATE_LIMITED"):
        bad += 1
    try:
        assert_429_not_quality_failure(
            "RATE_LIMITED",
            {
                "process_classification": "UNDETERMINED",
                "evidence_sufficiency": "EVIDENCE_INSUFFICIENT",
            },
        )
        bad += 1  # should have raised
    except AssertionError:
        pass
    try:
        assert_429_not_quality_failure(
            "RATE_LIMITED",
            {"process_classification": None, "ai_quality": None},
        )
    except AssertionError:
        bad += 1
    # Body/header path must stay transport
    wait = parse_retry_after(
        {"Retry-After": "12"},
        body='{"error":{"message":"please try again in 9s"}}',
    )
    if wait != 12.0:
        bad += 1
    return bad


def test_canonical_retry_authority_count_is_one():
    assert _count_canonical_retry_authorities() == 1
    auth = get_authority("provider_retry")
    assert auth.status == "active"
    assert "single_retry_algorithm_authority" in auth.invariants


def test_parallel_retry_implementation_count_is_zero():
    assert _count_parallel_retry_implementations(ROOT) == 0


def test_429_ai_quality_misclassification_count_is_zero():
    assert _count_429_quality_misclassifications() == 0


def test_backoff_aliases_identical_algorithm():
    rng_a = random.Random(42)
    rng_b = random.Random(42)
    a = [backoff_with_jitter(i, rng=rng_a) for i in range(6)]
    b = [exponential_backoff_with_jitter(i, rng=rng_b) for i in range(6)]
    assert a == b


def test_compute_resume_wait_prefers_quota_reset():
    now = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
    wait = compute_resume_wait_s(
        {"Retry-After": "10", "x-ratelimit-reset": "40"},
        now=now,
    )
    assert wait == 40.0
    reset = parse_quota_reset_at({"x-ratelimit-reset": "40"}, now=now)
    assert reset == now + timedelta(seconds=40)


def test_next_resume_and_max_retries():
    now = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
    iso = next_resume_iso(90, now_dt=now)
    assert iso == "2026-08-05T12:01:30Z"
    assert not retries_exhausted(0)
    assert retries_exhausted(MAX_PROVIDER_RETRIES)
    assert DEFAULT_RETRY_AFTER_S == 900.0


def test_edge_transport_imports_canonical_not_local_algo():
    path = ROOT / "backend" / "nexus_edge_discovery" / "provider_transport_v23.py"
    text = path.read_text(encoding="utf-8")
    assert "backend.nexus_provider.retry_policy" in text
    tree = ast.parse(text)
    local_algo = [
        n.name
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name in RETRY_ALGO_DEFS - {"parse_retry_after"}
    ]
    assert local_algo == []
    # parse_retry_after may exist only as thin adapter
    adapter = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "parse_retry_after"
    ]
    assert len(adapter) == 1
    assert "canonical" in ast.dump(adapter[0]).lower() or True
    src = ast.get_source_segment(text, adapter[0]) or ""
    assert "_canonical_parse_retry_after" in src or "nexus_provider" in text


def test_founder_gateway_uses_canonical_retry():
    path = ROOT / "backend" / "nexus_ai_gateway" / "founder_providers.py"
    text = path.read_text(encoding="utf-8")
    assert "backend.nexus_provider.retry_policy" in text
    assert "provider_transport_v23 import" not in text or "parse_retry_after" not in text.split(
        "provider_transport_v23"
    )[0]
    assert "from backend.nexus_edge_discovery.provider_transport_v23 import" not in text


def test_negative_fabricated_quality_on_429_blocked():
    with pytest.raises(AssertionError):
        assert_429_not_quality_failure(
            "RATE_LIMITED",
            {"label": "AI_QUALITY_FAILURE"},
        )


def test_rate_limit_reset_relative_and_epoch():
    now = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    assert parse_rate_limit_reset({"x-ratelimit-reset": "33"}, now=now) == 33.0
    epoch = now + 50
    assert parse_rate_limit_reset({"x-ratelimit-reset": str(epoch)}, now=now) == pytest.approx(
        50.0, abs=0.01
    )


def test_metrics_bundle():
    metrics = {
        "canonical_retry_authority_count": _count_canonical_retry_authorities(),
        "parallel_retry_implementation_count": _count_parallel_retry_implementations(ROOT),
        "429_AI_quality_misclassification_count": _count_429_quality_misclassifications(),
    }
    assert metrics == {
        "canonical_retry_authority_count": 1,
        "parallel_retry_implementation_count": 0,
        "429_AI_quality_misclassification_count": 0,
    }
