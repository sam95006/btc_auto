"""Unified V18-E AI Gateway — typed, sandboxed, no busy-loop."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_ai_gateway_tool_sandbox.adapters import (
    BaseAdapter,
    build_default_adapters,
    provider_status_matrix,
)
from backend.nexus_ai_gateway_tool_sandbox.audit import AuditLog
from backend.nexus_ai_gateway_tool_sandbox.budget import (
    BudgetPolicy,
    InFlightDedupe,
    ResponseCache,
)
from backend.nexus_ai_gateway_tool_sandbox.constants import (
    CAPACITY_DECISIONS,
    CAPACITY_STATUS,
    DEFAULT_TIMEOUT_S,
    MAX_PROVIDER_ATTEMPTS_PER_REQUEST,
    PIPELINE_CONTINUE,
    PROMPT_SCHEMA_VERSION,
)
from backend.nexus_ai_gateway_tool_sandbox.contracts import (
    GATEWAY_RESPONSE_SCHEMA,
    GatewayRequest,
    GatewayResponse,
    ProviderAttempt,
    ToolCallRequest,
    utc_now_iso,
)
from backend.nexus_ai_gateway_tool_sandbox.routing import (
    classify_role,
    provider_chain_for_role,
)
from backend.nexus_ai_gateway_tool_sandbox.tools import ToolSandbox


@dataclass
class UnifiedAIGateway:
    """
    Single typed gateway over:
      LOCAL, OPENAI_COMPATIBLE, GROQ, SAMBANOVA,
      OTHER_APPROVED_PROVIDER, DETERMINISTIC_FALLBACK

    On total provider failure (excluding intentional fallback exhaustion of
    remote providers when fallback also blocked in capacity tests):
      status = PROVIDER_CAPACITY_BLOCKED
      pipeline = CONTINUE_WITHOUT_AI
      decision = WAIT | ABSTAIN
    Never busy-loops.
    """

    adapters: dict[str, BaseAdapter]
    tools: ToolSandbox = field(default_factory=ToolSandbox)
    budget: BudgetPolicy = field(default_factory=BudgetPolicy)
    cache: ResponseCache = field(default_factory=ResponseCache)
    dedupe: InFlightDedupe = field(default_factory=InFlightDedupe)
    audit: AuditLog = field(default_factory=AuditLog)
    busy_loop_count: int = 0
    disable_deterministic_fallback: bool = False

    @classmethod
    def from_env(cls, *, mock: bool = True) -> "UnifiedAIGateway":
        return cls(adapters=build_default_adapters(mock=mock))

    def provider_statuses(self) -> dict[str, dict[str, Any]]:
        return provider_status_matrix(self.adapters)

    def invoke(
        self,
        *,
        prompt: str,
        payload: dict[str, Any] | None = None,
        role: str | None = None,
        tool_calls: list[ToolCallRequest] | None = None,
        schema: dict[str, Any] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_tokens: int = 1024,
        cacheable: bool = True,
        capacity_decision: str = "WAIT",
    ) -> GatewayResponse:
        payload = dict(payload or {})
        resolved_role = classify_role(payload, explicit_role=role)
        request = GatewayRequest(
            request_id=str(uuid.uuid4()),
            role=resolved_role,
            prompt=prompt,
            payload=payload,
            schema=schema or GATEWAY_RESPONSE_SCHEMA,
            prompt_schema_version=PROMPT_SCHEMA_VERSION,
            tool_calls=tuple(tool_calls or ()),
            timeout_s=timeout_s,
            max_tokens=max_tokens,
            cacheable=cacheable,
        )
        return self.invoke_request(request, capacity_decision=capacity_decision)

    def invoke_request(
        self,
        request: GatewayRequest,
        *,
        capacity_decision: str = "WAIT",
    ) -> GatewayResponse:
        t0 = time.perf_counter()
        if capacity_decision not in CAPACITY_DECISIONS:
            capacity_decision = "WAIT"

        # Tool sandbox gate (before any provider call).
        accepted_tools, tool_denials = self.tools.filter_tool_calls(request.tool_calls)
        if tool_denials and not accepted_tools and request.tool_calls:
            # Pure banned/unknown tool request — fail closed without provider churn.
            resp = GatewayResponse(
                request_id=request.request_id,
                provider_id="NONE",
                role=request.role,
                result_status="TOOL_DENIED",
                decision="BLOCK",
                confidence=0.0,
                summary="tool_sandbox_denied",
                output=None,
                pipeline=PIPELINE_CONTINUE,
                capacity_status=None,
                tool_denials=tool_denials,
                busy_loop_count=self.busy_loop_count,
            )
            self.audit.record(request, resp, provider_statuses=self.provider_statuses())
            resp.latency_ms = int((time.perf_counter() - t0) * 1000)
            return resp

        # Rebuild request with sanitized tools only.
        if accepted_tools != list(request.tool_calls):
            request = GatewayRequest(
                request_id=request.request_id,
                role=request.role,
                prompt=request.prompt,
                payload=request.payload,
                schema=request.schema,
                prompt_schema_version=request.prompt_schema_version,
                tool_calls=tuple(accepted_tools),
                timeout_s=request.timeout_s,
                max_tokens=request.max_tokens,
                prefer_provider=request.prefer_provider,
                cacheable=request.cacheable,
            )

        fp = request.fingerprint()

        # Cache
        if request.cacheable:
            cached = self.cache.get(fp)
            if cached is not None:
                cached.request_id = request.request_id
                cached.cache_hit = True
                cached.tool_denials = tool_denials
                cached.busy_loop_count = self.busy_loop_count
                self.audit.record(
                    request,
                    cached,
                    provider_statuses=self.provider_statuses(),
                    notes=["cache_hit"],
                )
                cached.latency_ms = int((time.perf_counter() - t0) * 1000)
                return cached

        # Dedupe in-flight identical fingerprints
        dedupe_state = self.dedupe.begin(fp)
        if dedupe_state is True:
            # Another identical request is in flight — do NOT re-dispatch (no busy-loop).
            self.busy_loop_count += 0  # explicit: we refuse to spin
            resp = GatewayResponse(
                request_id=request.request_id,
                provider_id="DEDUPE",
                role=request.role,
                result_status="DEDUPE_HIT",
                decision=capacity_decision,
                confidence=0.0,
                summary="dedupe_inflight_no_redispatch",
                output=None,
                pipeline=PIPELINE_CONTINUE,
                capacity_status=None,
                dedupe_hit=True,
                tool_denials=tool_denials,
                busy_loop_count=self.busy_loop_count,
            )
            self.audit.record(request, resp, provider_statuses=self.provider_statuses())
            resp.latency_ms = int((time.perf_counter() - t0) * 1000)
            return resp
        if isinstance(dedupe_state, GatewayResponse):
            dedupe_state.dedupe_hit = True
            dedupe_state.request_id = request.request_id
            return dedupe_state

        # Budget
        if not self.budget.can_spend(tokens=request.max_tokens):
            resp = self._capacity_response(
                request,
                capacity_decision=capacity_decision,
                result_status="BUDGET_EXCEEDED",
                tool_denials=tool_denials,
                attempts=[],
            )
            self.dedupe.finish(fp, resp)
            self.audit.record(request, resp, provider_statuses=self.provider_statuses())
            resp.latency_ms = int((time.perf_counter() - t0) * 1000)
            return resp

        chain = list(provider_chain_for_role(request.role))
        if request.prefer_provider and request.prefer_provider in self.adapters:
            chain = [request.prefer_provider] + [p for p in chain if p != request.prefer_provider]
        if self.disable_deterministic_fallback:
            chain = [p for p in chain if p != "DETERMINISTIC_FALLBACK"]

        attempts: list[ProviderAttempt] = []
        attempt_count = 0

        for provider_id in chain:
            if attempt_count >= MAX_PROVIDER_ATTEMPTS_PER_REQUEST:
                # Hard stop — counting a prevented busy-loop.
                self.busy_loop_count += 1
                break
            adapter = self.adapters.get(provider_id)
            if adapter is None:
                continue
            attempt_count += 1
            started = utc_now_iso()
            a0 = time.perf_counter()
            try:
                parsed, status, meta = adapter.complete(request)
            except TimeoutError:
                parsed, status, meta = None, "TIMEOUT", {}
            except Exception as exc:  # noqa: BLE001 — fail closed per attempt
                parsed, status, meta = None, "UNKNOWN", {"error": str(exc)}

            latency = int((time.perf_counter() - a0) * 1000)
            attempts.append(
                ProviderAttempt(
                    provider_id=provider_id,
                    started_at=started,
                    completed_at=utc_now_iso(),
                    latency_ms=latency,
                    result_status=status,
                    input_tokens=meta.get("input_tokens"),
                    output_tokens=meta.get("output_tokens"),
                    error=meta.get("error") or meta.get("detail"),
                )
            )

            if status == "SUCCESS" and parsed is not None:
                tokens = int(meta.get("input_tokens") or 0) + int(
                    meta.get("output_tokens") or 0
                )
                self.budget.record(tokens=tokens)
                resp = GatewayResponse(
                    request_id=request.request_id,
                    provider_id=provider_id,
                    role=request.role,
                    result_status="SUCCESS",
                    decision=str(parsed.get("decision") or capacity_decision),
                    confidence=float(parsed.get("confidence") or 0.0),
                    summary=str(parsed.get("summary") or ""),
                    output=parsed,
                    pipeline="AI_COMPLETED",
                    capacity_status=None,
                    attempts=attempts,
                    tool_denials=tool_denials,
                    busy_loop_count=self.busy_loop_count,
                )
                if request.cacheable:
                    self.cache.put(fp, resp)
                self.dedupe.finish(fp, resp)
                self.audit.record(
                    request, resp, provider_statuses=self.provider_statuses()
                )
                resp.latency_ms = int((time.perf_counter() - t0) * 1000)
                return resp

            # Non-success: try next provider once each — never re-hit same provider.
            continue

        # All providers exhausted → capacity block, continue pipeline without AI.
        resp = self._capacity_response(
            request,
            capacity_decision=capacity_decision,
            result_status=CAPACITY_STATUS,
            tool_denials=tool_denials,
            attempts=attempts,
        )
        self.budget.record(tokens=0)
        self.dedupe.finish(fp, resp)
        self.audit.record(
            request,
            resp,
            provider_statuses=self.provider_statuses(),
            notes=["all_providers_exhausted"],
        )
        resp.latency_ms = int((time.perf_counter() - t0) * 1000)
        return resp

    def _capacity_response(
        self,
        request: GatewayRequest,
        *,
        capacity_decision: str,
        result_status: str,
        tool_denials: list[str],
        attempts: list[ProviderAttempt],
    ) -> GatewayResponse:
        return GatewayResponse(
            request_id=request.request_id,
            provider_id="NONE",
            role=request.role,
            result_status=result_status,
            decision=capacity_decision,
            confidence=0.0,
            summary="provider_capacity_blocked_continue_without_ai",
            output={
                "decision": capacity_decision,
                "confidence": 0.0,
                "summary": "AI unavailable; pipeline continues without AI",
                "provider_id": "NONE",
                "pipeline": PIPELINE_CONTINUE,
                "capacity_status": CAPACITY_STATUS,
            },
            pipeline=PIPELINE_CONTINUE,
            capacity_status=CAPACITY_STATUS,
            attempts=attempts,
            tool_denials=tool_denials,
            busy_loop_count=self.busy_loop_count,
        )
