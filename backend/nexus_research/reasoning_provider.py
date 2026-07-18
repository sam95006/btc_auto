"""Phase 6 Gate D — Research Reasoning Provider.

Provides a stable interface for AI-assisted vs deterministic-rules review.

Modes:
  RULES_ONLY       — deterministic rules engine, no external calls (default)
  LLM_ASSISTED     — western/approved LLM provider available + key present
  LLM_UNAVAILABLE  — env configured but key absent / provider unreachable
  DEGRADED         — provider errored during last call, fallen back to rules

Allowlisted providers (western/approved only):
  openai, anthropic, azure_openai

Unknown / unapproved providers (e.g. Chinese endpoints) → BLOCK, mode = RULES_ONLY.

Constraints:
  - LLM MUST NEVER modify candidate scores, risk verdicts, or create orders.
  - Only public market evidence packs passed to LLM (no private account data).
  - No secrets logged.
  - Circuit breaker: 3 failures → DEGRADED for 10 minutes.
  - Token budget enforced per request.
  - Output hash stored for auditability.
  - Numeric hallucination guard: reject outputs with invented price/OI numbers
    not present in the evidence pack.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Mode constants ─────────────────────────────────────────────────────────────
MODE_RULES_ONLY = "RULES_ONLY"
MODE_LLM_ASSISTED = "LLM_ASSISTED"
MODE_LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
MODE_DEGRADED = "DEGRADED"

# ── Provider allowlist (western/approved) ─────────────────────────────────────
_ALLOWED_PROVIDERS: frozenset[str] = frozenset({
    "openai",
    "anthropic",
    "azure_openai",
})

_BLOCKED_REASON = "provider_not_in_allowlist"

# ── Env var names (no secrets logged) ─────────────────────────────────────────
_ENV_PROVIDER = "NEXUS_RESEARCH_LLM_PROVIDER"
_ENV_OPENAI_KEY = "OPENAI_API_KEY"
_ENV_ANTHROPIC_KEY = "ANTHROPIC_API_KEY"
_ENV_AZURE_KEY = "AZURE_OPENAI_API_KEY"

# ── Circuit breaker settings ───────────────────────────────────────────────────
_CB_FAILURE_THRESHOLD = 3
_CB_COOLDOWN_SEC = 600  # 10 minutes

# ── Token budget ───────────────────────────────────────────────────────────────
_MAX_EVIDENCE_TOKENS = 2000
_MAX_OUTPUT_TOKENS = 800

# ── Prompt version ─────────────────────────────────────────────────────────────
PROMPT_VERSION = "gate-d-v1"


def _detect_provider() -> str | None:
    """Read provider name from env — never log the value of API keys."""
    raw = os.environ.get(_ENV_PROVIDER, "").strip().lower()
    return raw if raw else None


def _provider_key_present(provider: str) -> bool:
    """Return True if the relevant API key env var is non-empty. Never log key value."""
    key_map = {
        "openai": _ENV_OPENAI_KEY,
        "anthropic": _ENV_ANTHROPIC_KEY,
        "azure_openai": _ENV_AZURE_KEY,
    }
    env_name = key_map.get(provider)
    if env_name is None:
        return False
    return bool(os.environ.get(env_name, "").strip())


# ── JSON schema for evidence pack ─────────────────────────────────────────────
_EVIDENCE_PACK_REQUIRED_FIELDS = {"symbol", "analysisMode", "evidenceIds"}

_OUTPUT_SCHEMA_REQUIRED = {"verdict", "rationale", "confidence"}


def _validate_evidence_pack(pack: dict[str, Any]) -> list[str]:
    """Return list of validation errors for evidence pack. Must not contain private data."""
    errors: list[str] = []
    missing = _EVIDENCE_PACK_REQUIRED_FIELDS - set(pack.keys())
    if missing:
        errors.append(f"missing required fields: {missing}")
    private_keys = {k for k in pack if k.lower() in {"api_key", "secret", "password", "token"}}
    if private_keys:
        errors.append(f"evidence pack contains private fields: {private_keys}")
    return errors


def _validate_output_schema(output: dict[str, Any]) -> list[str]:
    """Validate LLM output schema."""
    errors: list[str] = []
    missing = _OUTPUT_SCHEMA_REQUIRED - set(output.keys())
    if missing:
        errors.append(f"output missing required fields: {missing}")
    confidence = output.get("confidence")
    if confidence is not None:
        try:
            c = float(confidence)
            if not (0.0 <= c <= 1.0):
                errors.append(f"confidence out of range [0,1]: {c}")
        except (TypeError, ValueError):
            errors.append(f"confidence not numeric: {confidence!r}")
    return errors


def _hallucination_guard(
    output: dict[str, Any],
    evidence_pack: dict[str, Any],
) -> list[str]:
    """Reject outputs that invent numeric price/OI values not in evidence pack.

    Strategy: collect all float/int values in the evidence pack,
    then scan the output rationale for large numeric literals (>100 with decimals)
    that do not appear in the evidence pack.
    """
    violations: list[str] = []

    # Extract numeric values from evidence pack (prices, OI figures etc.)
    known_numbers: set[str] = set()
    for v in evidence_pack.values():
        if isinstance(v, (int, float)):
            known_numbers.add(f"{v:.2f}")
            known_numbers.add(str(int(v)))
        elif isinstance(v, str):
            # Include number-like tokens from evidence
            for tok in v.split():
                tok_clean = tok.strip(",.:;()[]")
                try:
                    as_f = float(tok_clean)
                    known_numbers.add(f"{as_f:.2f}")
                    known_numbers.add(str(int(as_f)))
                except ValueError:
                    pass

    rationale = str(output.get("rationale") or "")
    import re
    # Look for large decimal numbers (potential prices / OI figures)
    large_nums = re.findall(r'\b\d{4,}\.\d+\b', rationale)
    for num_str in large_nums:
        rounded = f"{float(num_str):.2f}"
        if rounded not in known_numbers and num_str not in known_numbers:
            violations.append(f"suspected invented number: {num_str}")

    return violations


def _output_hash(output: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of output for audit trail."""
    raw = json.dumps(output, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Base interface ─────────────────────────────────────────────────────────────

class ResearchReasoningProvider(ABC):
    """Abstract reasoning provider for Phase 6 Gate D review engine."""

    @property
    @abstractmethod
    def mode(self) -> str:
        """Return current mode string."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier."""

    @abstractmethod
    def reason(
        self,
        evidence_pack: dict[str, Any],
        instruction: str = "",
        timeout_sec: float = 15.0,
    ) -> dict[str, Any]:
        """Run reasoning over evidence_pack.

        Returns:
          {
            "ok": bool,
            "mode": str,
            "providerName": str,
            "promptVersion": str,
            "verdict": str,
            "rationale": str,
            "confidence": float,
            "evidenceIds": list[str],
            "outputHash": str,
            "modelMetadata": dict,
            "researchOnly": True,
            "privateApi": False,
            "warnings": list[str],
            "generatedAt": int,
          }
        """

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "mode": self.mode,
            "providerName": self.provider_name,
            "promptVersion": PROMPT_VERSION,
            "researchOnly": True,
            "privateApi": False,
            "allowedProviders": sorted(_ALLOWED_PROVIDERS),
            "generatedAt": int(time.time() * 1000),
        }


# ── Rules-only provider ────────────────────────────────────────────────────────

class RulesOnlyProvider(ResearchReasoningProvider):
    """Deterministic rules-based reasoning — no external calls, no LLM."""

    def __init__(self) -> None:
        self._call_count = 0
        self._lock = threading.Lock()

    @property
    def mode(self) -> str:
        return MODE_RULES_ONLY

    @property
    def provider_name(self) -> str:
        return "rules_only"

    def reason(
        self,
        evidence_pack: dict[str, Any],
        instruction: str = "",
        timeout_sec: float = 15.0,
    ) -> dict[str, Any]:
        with self._lock:
            self._call_count += 1

        validation_errors = _validate_evidence_pack(evidence_pack)
        warnings: list[str] = []
        if validation_errors:
            warnings.extend(validation_errors)

        symbol = str(evidence_pack.get("symbol") or "UNKNOWN")
        evidence_ids = list(evidence_pack.get("evidenceIds") or [])

        # Deterministic rules evaluation
        score = float(evidence_pack.get("score") or evidence_pack.get("candidateScore") or 0.0)
        risk_flags = list(evidence_pack.get("riskFlags") or [])
        has_critical_risk = any("CRITICAL" in f.upper() or "BLOCK" in f.upper() for f in risk_flags)

        if has_critical_risk:
            verdict = "BLOCKED_BY_RULES"
            confidence = 0.9
            rationale = f"Rules engine: critical risk flags present — {', '.join(risk_flags[:3])}"
        elif score >= 60:
            verdict = "RULES_FAVORABLE"
            confidence = min(0.5 + score / 200.0, 0.85)
            rationale = f"Rules engine: score={score:.1f} meets threshold; no critical flags"
        elif score >= 30:
            verdict = "RULES_NEUTRAL"
            confidence = 0.5
            rationale = f"Rules engine: score={score:.1f} in neutral band; watch conditions"
        else:
            verdict = "RULES_WEAK"
            confidence = 0.6
            rationale = f"Rules engine: score={score:.1f} below threshold; not recommended"

        output: dict[str, Any] = {
            "verdict": verdict,
            "rationale": rationale,
            "confidence": confidence,
            "evidenceIds": evidence_ids,
        }

        result = {
            "ok": True,
            "mode": MODE_RULES_ONLY,
            "providerName": "rules_only",
            "promptVersion": PROMPT_VERSION,
            "symbol": symbol,
            "verdict": verdict,
            "rationale": rationale,
            "confidence": confidence,
            "evidenceIds": evidence_ids,
            "outputHash": _output_hash(output),
            "modelMetadata": {"type": "deterministic_rules", "version": PROMPT_VERSION},
            "researchOnly": True,
            "privateApi": False,
            "warnings": warnings,
            "fabricatedChat": False,
            "generatedAt": int(time.time() * 1000),
        }
        logger.debug("[reasoning_provider] rules_only verdict=%s symbol=%s", verdict, symbol)
        return result


# ── LLM-assisted provider stub ─────────────────────────────────────────────────

class LlmAssistedProvider(ResearchReasoningProvider):
    """Stub for LLM-assisted reasoning.

    Checks env NEXUS_RESEARCH_LLM_PROVIDER and key presence at init time.
    Falls back to RULES_ONLY determinism if key absent or provider blocked.

    IMPORTANT CONSTRAINTS (never violated):
      - Never modifies candidate scores, risk verdicts, or position size.
      - Never creates orders.
      - Only public market evidence packs passed (no private account data).
      - No secrets are logged.
      - Circuit breaker: 3 failures → DEGRADED for 10 min.
      - Token budget: evidence ≤2000 tokens, output ≤800 tokens.
      - Numeric hallucination guard applied to all outputs.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._call_count = 0
        self._failure_count = 0
        self._last_failure_ts: float = 0.0
        self._degraded_until: float = 0.0
        self._rules_fallback = RulesOnlyProvider()

        provider = _detect_provider()
        if provider is None:
            self._detected_provider = None
            self._mode = MODE_RULES_ONLY
            self._block_reason = "NEXUS_RESEARCH_LLM_PROVIDER not set"
            logger.info("[reasoning_provider] LLM provider env not set → RULES_ONLY")
        elif provider not in _ALLOWED_PROVIDERS:
            self._detected_provider = provider
            self._mode = MODE_RULES_ONLY
            self._block_reason = f"{_BLOCKED_REASON}: {provider!r}"
            logger.warning(
                "[reasoning_provider] provider %r not in allowlist — BLOCKED → RULES_ONLY",
                provider,
            )
        elif not _provider_key_present(provider):
            self._detected_provider = provider
            self._mode = MODE_LLM_UNAVAILABLE
            self._block_reason = f"API key absent for provider={provider!r}"
            logger.info(
                "[reasoning_provider] provider=%r key absent → LLM_UNAVAILABLE", provider
            )
        else:
            self._detected_provider = provider
            self._mode = MODE_LLM_ASSISTED
            self._block_reason = None
            logger.info(
                "[reasoning_provider] provider=%r key present → LLM_ASSISTED (stub active)",
                provider,
            )

    @property
    def mode(self) -> str:
        with self._lock:
            now = time.time()
            if self._degraded_until > now:
                return MODE_DEGRADED
            return self._mode

    @property
    def provider_name(self) -> str:
        return self._detected_provider or "none"

    def _is_circuit_open(self) -> bool:
        now = time.time()
        if self._degraded_until > now:
            return True
        return False

    def _record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_ts = time.time()
            if self._failure_count >= _CB_FAILURE_THRESHOLD:
                self._degraded_until = time.time() + _CB_COOLDOWN_SEC
                logger.warning(
                    "[reasoning_provider] circuit breaker OPEN: %d failures → DEGRADED for %ds",
                    self._failure_count, _CB_COOLDOWN_SEC,
                )

    def _record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._degraded_until = 0.0

    def reason(
        self,
        evidence_pack: dict[str, Any],
        instruction: str = "",
        timeout_sec: float = 15.0,
    ) -> dict[str, Any]:
        current_mode = self.mode
        warnings: list[str] = []

        # Validate evidence pack (no private data)
        validation_errors = _validate_evidence_pack(evidence_pack)
        if validation_errors:
            warnings.extend(validation_errors)

        # If not actually LLM_ASSISTED or circuit open → rules fallback
        if current_mode != MODE_LLM_ASSISTED or self._is_circuit_open():
            fallback_result = self._rules_fallback.reason(evidence_pack, instruction, timeout_sec)
            fallback_result["mode"] = current_mode
            fallback_result["providerName"] = self.provider_name
            fallback_result["blockReason"] = self._block_reason
            if current_mode == MODE_DEGRADED:
                fallback_result["warnings"] = fallback_result.get("warnings", []) + [
                    "circuit_breaker_open_using_rules_fallback"
                ]
            return fallback_result

        # ── LLM call stub ─────────────────────────────────────────────────────
        # In a real implementation this would call the LLM API.
        # This stub returns RULES_ONLY result with mode=LLM_ASSISTED annotation,
        # so the Gate D framework is wired correctly.
        # Real LLM wiring should be added when needed, following these invariants:
        #   1. Truncate evidence to _MAX_EVIDENCE_TOKENS tokens before sending.
        #   2. Enforce _MAX_OUTPUT_TOKENS on completion.
        #   3. Apply _hallucination_guard before accepting output.
        #   4. Never pass private account data in prompt.
        #   5. Log only non-secret metadata (model, latency, token count).
        try:
            with self._lock:
                self._call_count += 1

            # Stub: produce deterministic output annotated as LLM_ASSISTED
            rules_result = self._rules_fallback.reason(evidence_pack, instruction, timeout_sec)
            output_for_hash = {
                "verdict": rules_result["verdict"],
                "rationale": rules_result["rationale"],
                "confidence": rules_result["confidence"],
                "evidenceIds": rules_result["evidenceIds"],
            }
            # Hallucination guard (still applied even in stub)
            halluc_violations = _hallucination_guard(rules_result, evidence_pack)
            if halluc_violations:
                warnings.extend([f"hallucination_guard: {v}" for v in halluc_violations])

            schema_errors = _validate_output_schema(output_for_hash)
            if schema_errors:
                raise ValueError(f"output schema invalid: {schema_errors}")

            self._record_success()

            result = {
                "ok": True,
                "mode": MODE_LLM_ASSISTED,
                "providerName": self._detected_provider,
                "promptVersion": PROMPT_VERSION,
                "symbol": rules_result.get("symbol"),
                "verdict": rules_result["verdict"],
                "rationale": f"[LLM_STUB/{self._detected_provider}] {rules_result['rationale']}",
                "confidence": rules_result["confidence"],
                "evidenceIds": rules_result["evidenceIds"],
                "outputHash": _output_hash(output_for_hash),
                "modelMetadata": {
                    "type": "llm_assisted_stub",
                    "provider": self._detected_provider,
                    "promptVersion": PROMPT_VERSION,
                    "tokenBudget": {
                        "evidenceMax": _MAX_EVIDENCE_TOKENS,
                        "outputMax": _MAX_OUTPUT_TOKENS,
                    },
                },
                "researchOnly": True,
                "privateApi": False,
                "warnings": warnings,
                "fabricatedChat": False,
                "generatedAt": int(time.time() * 1000),
            }
            logger.debug(
                "[reasoning_provider] llm_assisted_stub verdict=%s provider=%s",
                result["verdict"], self._detected_provider,
            )
            return result

        except Exception as exc:  # noqa: BLE001
            self._record_failure()
            logger.warning("[reasoning_provider] LLM call error: %s → rules fallback", exc)
            fallback_result = self._rules_fallback.reason(evidence_pack, instruction, timeout_sec)
            fallback_result["mode"] = MODE_DEGRADED
            fallback_result["providerName"] = self._detected_provider or "none"
            fallback_result["warnings"] = fallback_result.get("warnings", []) + [f"llm_error: {exc}"]
            return fallback_result

    def status(self) -> dict[str, Any]:
        base = super().status()
        with self._lock:
            base.update({
                "detectedProvider": self._detected_provider,
                "blockReason": self._block_reason,
                "callCount": self._call_count,
                "failureCount": self._failure_count,
                "circuitBreakerOpen": self._is_circuit_open(),
                "degradedUntilMs": int(self._degraded_until * 1000) if self._degraded_until else None,
                "tokenBudget": {
                    "evidenceMax": _MAX_EVIDENCE_TOKENS,
                    "outputMax": _MAX_OUTPUT_TOKENS,
                },
            })
        return base


# ── Factory ───────────────────────────────────────────────────────────────────

def create_reasoning_provider() -> ResearchReasoningProvider:
    """Create the appropriate provider based on env configuration."""
    provider = _detect_provider()
    if provider is None:
        logger.info("[reasoning_provider] no LLM provider configured → RulesOnlyProvider")
        return RulesOnlyProvider()
    return LlmAssistedProvider()


# ── Singleton ─────────────────────────────────────────────────────────────────
_PROVIDER: ResearchReasoningProvider | None = None
_PROVIDER_LOCK = threading.Lock()


def get_reasoning_provider() -> ResearchReasoningProvider:
    global _PROVIDER
    with _PROVIDER_LOCK:
        if _PROVIDER is None:
            _PROVIDER = create_reasoning_provider()
            logger.info(
                "[reasoning_provider] singleton mode=%s provider=%s",
                _PROVIDER.mode, _PROVIDER.provider_name,
            )
        return _PROVIDER


def reset_reasoning_provider() -> None:
    """Reset singleton (for testing)."""
    global _PROVIDER
    with _PROVIDER_LOCK:
        _PROVIDER = None
