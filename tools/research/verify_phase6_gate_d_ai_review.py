#!/usr/bin/env python3
"""Phase 6 Gate D Verification — AI Review Engine & Reasoning Provider.

Verifies:
  T01  PROVIDER_IMPORT: reasoning_provider module importable
  T02  PROVIDER_SINGLETON: get_reasoning_provider() returns singleton
  T03  PROVIDER_ALLOWLIST: unknown provider → RULES_ONLY (not BLOCKED crash)
  T04  PROVIDER_ALLOWLIST_CHINESE: Chinese/non-allowlisted provider blocked
  T05  PROVIDER_MODE_NO_ENV: no env configured → RULES_ONLY mode
  T06  PROVIDER_RULES_ONLY_REASON: RulesOnlyProvider returns valid result
  T07  PROVIDER_EVIDENCE_VALIDATION: invalid evidence pack returns warnings
  T08  PROVIDER_PRIVATE_DATA_REJECTED: private fields in pack → warning
  T09  PROVIDER_OUTPUT_HASH: output hash present and 16 chars
  T10  PROVIDER_NO_HALLUCINATION: hallucination guard rejects invented numbers
  T11  PROVIDER_FABRICATED_CHAT_FALSE: fabricatedChat=false in output
  T12  PROVIDER_RESEARCH_ONLY: output has researchOnly=true, privateApi=false
  T13  REVIEW_ENGINE_IMPORT: review_engine module importable
  T14  REVIEW_ENGINE_SINGLETON: get_review_engine() returns singleton
  T15  REVIEW_ENGINE_STATUS: status() returns reviewMode + providerName
  T16  REVIEW_ENGINE_RUN: run_review() returns roleDecision + reasoning
  T17  REVIEW_ENGINE_NO_MODIFY_RISK: reasoning never modifies decisionStatus
  T18  REVIEW_ENGINE_UI_LABEL: uiModeLabel honest (no 'generative AI' when RULES_ONLY)
  T19  REVIEW_ENGINE_FABRICATED_CHAT: status shows fabricatedChat=false
  T20  LLM_UNAVAILABLE_MODE: key absent → LLM_UNAVAILABLE mode in status
  T21  DEGRADED_CIRCUIT_BREAKER: simulate 3 failures → mode goes DEGRADED
  T22  PROVIDER_STATUS_SHAPE: status() has required fields
  T23  NO_SECRET_IN_LOGS: provider operations do not reveal secret values
  T24  EVIDENCE_PACK_NO_PRIVATE: _build_evidence_pack strips private fields

VERDICT=PASS if all pass, VERDICT=FAIL otherwise.

Usage:
  python tools/research/verify_phase6_gate_d_ai_review.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_PASS = "PASS"
_FAIL = "FAIL"
_SKIP = "SKIP"

_results: list[dict] = []


def _test(name: str, fn) -> dict:
    start = time.time()
    try:
        fn()
        elapsed = time.time() - start
        result = {"test": name, "verdict": _PASS, "elapsedMs": round(elapsed * 1000)}
        print(f"  [PASS] {name}  ({elapsed * 1000:.0f}ms)")
    except Exception as exc:  # noqa: BLE001
        elapsed = time.time() - start
        result = {"test": name, "verdict": _FAIL, "error": str(exc), "elapsedMs": round(elapsed * 1000)}
        print(f"  [FAIL] {name}  ({elapsed * 1000:.0f}ms)")
        print(f"         {exc}")
    _results.append(result)
    return result


# ── T01: Import ────────────────────────────────────────────────────────────────

def t01_import():
    from backend.nexus_research.reasoning_provider import ResearchReasoningProvider  # noqa: F401


# ── T02: Singleton ─────────────────────────────────────────────────────────────

def t02_singleton():
    from backend.nexus_research.reasoning_provider import get_reasoning_provider, reset_reasoning_provider
    reset_reasoning_provider()
    a = get_reasoning_provider()
    b = get_reasoning_provider()
    assert a is b, "must be same singleton"
    reset_reasoning_provider()


# ── T03: Unknown provider → RULES_ONLY ────────────────────────────────────────

def t03_allowlist_unknown():
    os.environ["NEXUS_RESEARCH_LLM_PROVIDER"] = "unknown_provider_xyz"
    try:
        from backend.nexus_research.reasoning_provider import LlmAssistedProvider
        p = LlmAssistedProvider()
        assert p.mode == "RULES_ONLY", f"expected RULES_ONLY for unknown provider, got {p.mode}"
    finally:
        del os.environ["NEXUS_RESEARCH_LLM_PROVIDER"]


# ── T04: Chinese/non-allowlisted provider blocked ──────────────────────────────

def t04_allowlist_chinese():
    os.environ["NEXUS_RESEARCH_LLM_PROVIDER"] = "baidu_ernie"
    try:
        from backend.nexus_research.reasoning_provider import LlmAssistedProvider
        p = LlmAssistedProvider()
        # Must be RULES_ONLY (blocked)
        assert p.mode == "RULES_ONLY", f"expected RULES_ONLY for blocked provider, got {p.mode}"
    finally:
        del os.environ["NEXUS_RESEARCH_LLM_PROVIDER"]


# ── T05: No env → RULES_ONLY ──────────────────────────────────────────────────

def t05_no_env_rules_only():
    # Ensure env is clean
    for k in ("NEXUS_RESEARCH_LLM_PROVIDER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        os.environ.pop(k, None)
    from backend.nexus_research.reasoning_provider import reset_reasoning_provider, get_reasoning_provider
    reset_reasoning_provider()
    p = get_reasoning_provider()
    assert p.mode == "RULES_ONLY", f"expected RULES_ONLY with no env, got {p.mode}"
    reset_reasoning_provider()


# ── T06: RulesOnlyProvider result ─────────────────────────────────────────────

def t06_rules_only_reason():
    from backend.nexus_research.reasoning_provider import RulesOnlyProvider
    p = RulesOnlyProvider()
    result = p.reason(evidence_pack={
        "symbol": "BTCUSDT",
        "analysisMode": "RESEARCH",
        "evidenceIds": ["e1", "e2"],
        "score": 65.0,
    })
    assert result["ok"] is True
    assert result["mode"] == "RULES_ONLY"
    assert result["researchOnly"] is True
    assert result["privateApi"] is False
    assert "verdict" in result
    assert "rationale" in result
    assert "confidence" in result


# ── T07: Invalid evidence pack → warnings ─────────────────────────────────────

def t07_evidence_validation():
    from backend.nexus_research.reasoning_provider import RulesOnlyProvider
    p = RulesOnlyProvider()
    # Missing required fields
    result = p.reason(evidence_pack={"score": 50.0})
    warnings = result.get("warnings", [])
    assert any("missing" in w for w in warnings), f"expected missing-field warning: {warnings}"


# ── T08: Private fields → warning ─────────────────────────────────────────────

def t08_private_data_rejected():
    from backend.nexus_research.reasoning_provider import _validate_evidence_pack
    errors = _validate_evidence_pack({
        "symbol": "BTCUSDT",
        "analysisMode": "RESEARCH",
        "evidenceIds": ["e1"],
        "api_key": "secret123",  # private field
    })
    assert any("private" in e for e in errors), f"expected private field error: {errors}"


# ── T09: Output hash ──────────────────────────────────────────────────────────

def t09_output_hash():
    from backend.nexus_research.reasoning_provider import RulesOnlyProvider
    p = RulesOnlyProvider()
    result = p.reason(evidence_pack={
        "symbol": "ETHUSDT",
        "analysisMode": "RESEARCH",
        "evidenceIds": ["e3"],
    })
    h = result.get("outputHash", "")
    assert len(h) == 16, f"expected 16-char hash, got {len(h)}: {h!r}"
    assert h.isalnum(), f"hash not alphanumeric: {h!r}"


# ── T10: Hallucination guard ──────────────────────────────────────────────────

def t10_hallucination_guard():
    from backend.nexus_research.reasoning_provider import _hallucination_guard
    # Output contains a large decimal not in evidence pack
    output = {
        "verdict": "FAVORABLE",
        "rationale": "Price has reached 98765.43 which suggests bullish momentum",
        "confidence": 0.7,
        "evidenceIds": ["e1"],
    }
    evidence = {
        "symbol": "BTCUSDT",
        "analysisMode": "RESEARCH",
        "evidenceIds": ["e1"],
        "score": 60.0,
    }
    violations = _hallucination_guard(output, evidence)
    assert violations, "expected hallucination guard to flag invented price"


# ── T11: fabricatedChat=false ─────────────────────────────────────────────────

def t11_fabricated_chat_false():
    from backend.nexus_research.reasoning_provider import RulesOnlyProvider
    p = RulesOnlyProvider()
    result = p.reason(evidence_pack={
        "symbol": "SOLUSDT",
        "analysisMode": "RESEARCH",
        "evidenceIds": ["e4"],
    })
    assert result.get("fabricatedChat") is False, "fabricatedChat must be False"


# ── T12: researchOnly + privateApi ───────────────────────────────────────────

def t12_research_only():
    from backend.nexus_research.reasoning_provider import RulesOnlyProvider
    p = RulesOnlyProvider()
    result = p.reason(evidence_pack={
        "symbol": "BNBUSDT",
        "analysisMode": "RESEARCH",
        "evidenceIds": [],
    })
    assert result["researchOnly"] is True
    assert result["privateApi"] is False


# ── T13: Review engine import ─────────────────────────────────────────────────

def t13_review_engine_import():
    from backend.nexus_research.review_engine import ReviewEngine  # noqa: F401


# ── T14: Review engine singleton ──────────────────────────────────────────────

def t14_review_engine_singleton():
    from backend.nexus_research.review_engine import get_review_engine
    a = get_review_engine()
    b = get_review_engine()
    assert a is b, "must return singleton"


# ── T15: Status shape ────────────────────────────────────────────────────────

def t15_review_engine_status():
    from backend.nexus_research.review_engine import get_review_engine
    status = get_review_engine().status()
    required = {"ok", "researchOnly", "reviewMode", "providerName", "uiModeLabel", "fabricatedChat"}
    missing = required - set(status.keys())
    assert not missing, f"status missing keys: {missing}"
    assert status["ok"] is True
    assert status["researchOnly"] is True


# ── T16: run_review result shape ─────────────────────────────────────────────

def t16_run_review():
    from backend.nexus_research.review_engine import get_review_engine
    engine = get_review_engine()
    result = engine.run_review(
        case_id="test_case_001",
        candidate={
            "symbol": "BTCUSDT",
            "side": "LONG",
            "score": 65.0,
            "change24hPct": 2.0,
            "fundingRate": 0.0001,
            "riskScore": 30.0,
            "stage": "CONFIRMED",
        },
        context={"activeCases": 3},
    )
    assert result["ok"] is True
    assert result["researchOnly"] is True
    assert result["privateApi"] is False
    assert "roleDecision" in result
    assert "reviewMode" in result
    assert "decisionStatus" in result


# ── T17: Reasoning never modifies decisionStatus ─────────────────────────────

def t17_no_modify_risk():
    from backend.nexus_research.review_engine import get_review_engine
    engine = get_review_engine()
    result = engine.run_review(
        case_id="test_case_002",
        candidate={
            "symbol": "ETHUSDT",
            "side": "LONG",
            "score": 10.0,  # low score → weak
            "riskScore": 90.0,  # high risk → BLOCKED
            "stage": "OVEREXTENDED",
        },
    )
    role_decision = result["roleDecision"]
    # decisionStatus from roles.py is authoritative — reasoning cannot change it
    assert result["decisionStatus"] == role_decision.get("decisionStatus"), \
        "reviewEngine decisionStatus must match roleDecision.decisionStatus"
    assert result.get("_invariant") is not None, "invariant annotation must be present"


# ── T18: UI label honest for RULES_ONLY ──────────────────────────────────────

def t18_ui_label_honest():
    from backend.nexus_research.review_engine import _mode_ui_label
    label = _mode_ui_label("RULES_ONLY")
    # Must NOT say "generative AI" or "LLM" when in RULES_ONLY mode
    label_lower = label.lower()
    assert "llm" not in label_lower or "非" in label, \
        f"RULES_ONLY label must clarify it's not generative AI: {label}"
    assert "規則" in label or "rules" in label_lower, \
        f"RULES_ONLY label must mention rules: {label}"


# ── T19: fabricatedChat=false in status ──────────────────────────────────────

def t19_fabricated_chat_status():
    from backend.nexus_research.review_engine import get_review_engine
    status = get_review_engine().status()
    assert status.get("fabricatedChat") is False, "fabricatedChat must be False in status"


# ── T20: LLM_UNAVAILABLE when key absent ────────────────────────────────────

def t20_llm_unavailable():
    os.environ["NEXUS_RESEARCH_LLM_PROVIDER"] = "openai"
    os.environ.pop("OPENAI_API_KEY", None)
    try:
        from backend.nexus_research.reasoning_provider import LlmAssistedProvider
        p = LlmAssistedProvider()
        assert p.mode == "LLM_UNAVAILABLE", f"expected LLM_UNAVAILABLE, got {p.mode}"
    finally:
        del os.environ["NEXUS_RESEARCH_LLM_PROVIDER"]


# ── T21: DEGRADED after 3 failures ───────────────────────────────────────────

def t21_degraded_circuit_breaker():
    from backend.nexus_research.reasoning_provider import LlmAssistedProvider, _CB_FAILURE_THRESHOLD
    p = LlmAssistedProvider.__new__(LlmAssistedProvider)
    import threading
    p._lock = threading.RLock()
    p._call_count = 0
    p._failure_count = 0
    p._last_failure_ts = 0.0
    p._degraded_until = 0.0
    p._detected_provider = "openai"
    p._mode = "LLM_ASSISTED"
    p._block_reason = None

    for _ in range(_CB_FAILURE_THRESHOLD):
        p._record_failure()

    assert p._is_circuit_open(), "circuit breaker should be open after threshold failures"


# ── T22: Provider status shape ───────────────────────────────────────────────

def t22_provider_status_shape():
    from backend.nexus_research.reasoning_provider import get_reasoning_provider, reset_reasoning_provider
    reset_reasoning_provider()
    p = get_reasoning_provider()
    status = p.status()
    required = {"ok", "mode", "providerName", "promptVersion", "researchOnly", "privateApi", "allowedProviders"}
    missing = required - set(status.keys())
    assert not missing, f"provider status missing keys: {missing}"
    reset_reasoning_provider()


# ── T23: No secret in provider status ────────────────────────────────────────

def t23_no_secret_in_status():
    from backend.nexus_research.reasoning_provider import get_reasoning_provider, reset_reasoning_provider
    reset_reasoning_provider()
    p = get_reasoning_provider()
    status_str = str(p.status())
    # Spot-check: known fake key values must not appear
    for forbidden in ("sk-", "api-key-", "AKIA", "Bearer "):
        assert forbidden not in status_str, f"potential secret value leaked: {forbidden!r}"
    reset_reasoning_provider()


# ── T24: Evidence pack strips private fields ─────────────────────────────────

def t24_evidence_pack_no_private():
    from backend.nexus_research.review_engine import ReviewEngine
    engine = ReviewEngine()
    candidate = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "score": 60.0,
        "api_key": "secret_value_12345",  # private — must be stripped
        "accountBalance": 99999.99,        # private — must be stripped
    }
    role_decision = {"decisionStatus": "WATCH_ONLY", "assessments": []}
    pack = engine._build_evidence_pack(candidate, role_decision)
    assert "api_key" not in pack, "api_key must be stripped from evidence pack"
    assert "accountBalance" not in pack, "accountBalance must be stripped from evidence pack"
    assert "symbol" in pack, "symbol should be present"


# ── Runner ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Phase 6 Gate D — AI Review Verification")
    print("=" * 60)

    tests = [
        ("T01_PROVIDER_IMPORT", t01_import),
        ("T02_PROVIDER_SINGLETON", t02_singleton),
        ("T03_ALLOWLIST_UNKNOWN", t03_allowlist_unknown),
        ("T04_ALLOWLIST_CHINESE", t04_allowlist_chinese),
        ("T05_NO_ENV_RULES_ONLY", t05_no_env_rules_only),
        ("T06_RULES_ONLY_REASON", t06_rules_only_reason),
        ("T07_EVIDENCE_VALIDATION", t07_evidence_validation),
        ("T08_PRIVATE_DATA_REJECTED", t08_private_data_rejected),
        ("T09_OUTPUT_HASH", t09_output_hash),
        ("T10_HALLUCINATION_GUARD", t10_hallucination_guard),
        ("T11_FABRICATED_CHAT_FALSE", t11_fabricated_chat_false),
        ("T12_RESEARCH_ONLY", t12_research_only),
        ("T13_REVIEW_ENGINE_IMPORT", t13_review_engine_import),
        ("T14_REVIEW_ENGINE_SINGLETON", t14_review_engine_singleton),
        ("T15_REVIEW_ENGINE_STATUS", t15_review_engine_status),
        ("T16_RUN_REVIEW", t16_run_review),
        ("T17_NO_MODIFY_RISK", t17_no_modify_risk),
        ("T18_UI_LABEL_HONEST", t18_ui_label_honest),
        ("T19_FABRICATED_CHAT_STATUS", t19_fabricated_chat_status),
        ("T20_LLM_UNAVAILABLE", t20_llm_unavailable),
        ("T21_DEGRADED_CIRCUIT_BREAKER", t21_degraded_circuit_breaker),
        ("T22_PROVIDER_STATUS_SHAPE", t22_provider_status_shape),
        ("T23_NO_SECRET_IN_STATUS", t23_no_secret_in_status),
        ("T24_EVIDENCE_PACK_NO_PRIVATE", t24_evidence_pack_no_private),
    ]

    for name, fn in tests:
        _test(name, fn)

    print()
    print("=" * 60)
    passes = sum(1 for r in _results if r["verdict"] == _PASS)
    fails = sum(1 for r in _results if r["verdict"] == _FAIL)
    skips = sum(1 for r in _results if r["verdict"] == _SKIP)
    total = len(_results)
    verdict = _PASS if fails == 0 else _FAIL
    print(f"TOTAL={total}  PASS={passes}  FAIL={fails}  SKIP={skips}")
    print(f"VERDICT={verdict}")
    print("=" * 60)

    if fails > 0:
        print("\nFailed tests:")
        for r in _results:
            if r["verdict"] == _FAIL:
                print(f"  {r['test']}: {r.get('error', '')}")

    sys.exit(0 if verdict == _PASS else 1)


if __name__ == "__main__":
    main()
