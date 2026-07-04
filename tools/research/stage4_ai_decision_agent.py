"""Stage 4 AI Decision Agent — mock or real LLM dry-run (no orders)."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.research.bybit_demo_learning_common import MAX_MARGIN_USD, utc_now_iso
from tools.research.stage3_learning_loop import append_jsonl, resolve_output_dir, setup_key
from tools.research.stage4_decision_schema import parse_llm_decision
from tools.research.stage4_parse_error_metrics import normalize_parse_error_type
from tools.research.stage4_prompt_builder import build_decision_prompt, prompt_fingerprint
from tools.research.stage4_context_summary import (  # noqa: E402
    blocking_patches,
    load_stage3_context,
    resolve_stage3_data_dir,
    summarize_patches,
    summarize_reflections,
    summarize_trades,
)
from tools.research.stage4_risk_supervisor import Stage4RiskSupervisor, safety_constraints_from_env

ROOT = Path(__file__).resolve().parents[2]
MOCK_MODEL_NAME = "mock_ai_decision_agent"
DEFAULT_DECISION_SOURCE = "mock_ai_decision_agent"

REQUIRED_DECISION_FIELDS = (
    "decision_id",
    "created_at_utc",
    "decision_source",
    "mode",
    "model_name",
    "prompt_hash",
    "symbol",
    "candidate_side",
    "final_action",
    "confidence",
    "position_size_suggestion",
    "market_context",
    "account_context",
    "retrieved_patches",
    "why_enter",
    "why_skip",
    "side_reason",
    "confidence_reason",
    "risk_notes",
    "safety_constraints",
    "risk_supervisor_result",
    "final_decision",
    "order_sent",
    "real_llm_used",
)


def resolve_stage4_output_dir() -> Path:
    import os

    custom = os.environ.get("STAGE4_OUTPUT_DIR", "").strip()
    if custom:
        out = Path(custom)
        out.mkdir(parents=True, exist_ok=True)
        return out
    nexus = os.environ.get("NEXUS_DATA_DIR", "").strip()
    if nexus:
        candidate = Path(nexus) / "stage4_ai_decisions"
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test = candidate / ".write_probe"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            return candidate
        except OSError:
            pass
    out = ROOT / "data" / "external_alpha" / "stage4_ai_decisions"
    out.mkdir(parents=True, exist_ok=True)
    return out


def resolve_stage3_learning_dir() -> Path:
    return resolve_stage3_data_dir()


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


class Stage4PatchRetriever:
    """JSONL retrieval by symbol / side / setup_key / failure_reason."""

    def __init__(self, stage3_dir: Optional[Path] = None) -> None:
        self.stage3_dir = stage3_dir or resolve_stage3_learning_dir()

    def retrieve(
        self,
        *,
        symbol: str,
        side: str,
        regime: str = "unknown",
        failure_reason: str = "",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        patches = _read_jsonl(self.stage3_dir / "applied_learning_patches.jsonl")
        sym = symbol.upper()
        side_u = side.upper()
        key_hint = setup_key(sym, side_u, regime, failure_reason or "controlled_demo_order")
        matched: List[Dict[str, Any]] = []
        for row in reversed(patches):
            row_sym = str(row.get("symbol") or "").upper()
            row_side = str(row.get("side") or "").upper()
            row_key = str(row.get("setup_key") or "")
            if row_sym == sym and (not side_u or side_u == "NONE" or row_side == side_u):
                matched.append(row)
            elif key_hint and row_key == key_hint:
                matched.append(row)
            elif row_sym == sym:
                matched.append(row)
            if len(matched) >= limit:
                break
        return matched[:limit]

    def recent_trades(self, *, symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
        trades = _read_jsonl(self.stage3_dir / "trade_results.jsonl")
        sym = symbol.upper()
        return [t for t in reversed(trades) if str(t.get("symbol", "")).upper() == sym][:limit]

    def recent_reflections(self, limit: int = 5) -> List[Dict[str, Any]]:
        rows = _read_jsonl(self.stage3_dir / "reflection_records.jsonl")
        return list(reversed(rows))[:limit]


class Stage4AIDecisionAgent:
    """Mock or real LLM proposals for dry-run; Risk Supervisor always runs after."""

    def __init__(
        self,
        *,
        model_name: str = MOCK_MODEL_NAME,
        is_mock_ai: bool = True,
        use_real_llm: bool = False,
        retriever: Optional[Stage4PatchRetriever] = None,
        supervisor: Optional[Stage4RiskSupervisor] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        self.use_real_llm = use_real_llm
        self.real_llm_used = False
        self.fallback_to_mock = False
        self.provider = ""
        self.llm_client = llm_client
        self.retriever = retriever or Stage4PatchRetriever()
        self.supervisor = supervisor or Stage4RiskSupervisor()

        if use_real_llm:
            from tools.research.stage4_llm_client import (
                RealLLMRequiredError,
                mock_fallback_allowed,
            )
            from tools.research.stage4_provider_chain import Stage4ProviderChainClient

            self.llm_client = llm_client or Stage4ProviderChainClient(load_env=True)
            avail = self.llm_client.availability()
            if avail.get("real_llm_available"):
                self.is_mock_ai = False
                self.real_llm_used = True
                self.model_name = str(avail.get("model_name") or model_name)
                self.provider = str(avail.get("provider") or "")
                self.decision_source = "ai_decision_agent"
            elif not mock_fallback_allowed(use_real_llm=True):
                reason = str(avail.get("reason") or "missing_real_llm_key")
                raise RealLLMRequiredError(reason)
            else:
                self.is_mock_ai = True
                self.real_llm_used = False
                self.fallback_to_mock = True
                self.model_name = MOCK_MODEL_NAME
                self.provider = ""
                self.decision_source = DEFAULT_DECISION_SOURCE
        else:
            self.model_name = model_name
            self.is_mock_ai = is_mock_ai
            self.provider = ""
            self.decision_source = DEFAULT_DECISION_SOURCE if is_mock_ai else "ai_decision_agent"

    def _mock_proposal(
        self,
        *,
        symbol: str,
        market_context: Dict[str, Any],
        patches: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        last = float(market_context.get("last_price") or 0)
        prev = float(market_context.get("prev_price_24h") or last)
        change_pct = ((last - prev) / prev * 100.0) if prev else 0.0
        regime = "trend_up" if change_pct > 0.1 else "trend_down" if change_pct < -0.1 else "range"

        veto_patch = next(
            (p for p in patches if str(p.get("action")) in {"block_reentry", "manual_review_required"}),
            None,
        )
        if veto_patch:
            return {
                "candidate_side": str(veto_patch.get("side") or "BUY").upper(),
                "final_action": "enter",
                "confidence": 0.55,
                "position_size_suggestion": min(12.0, MAX_MARGIN_USD),
                "regime": regime,
                "why_enter": "Mock AI would re-enter same setup despite prior loss pattern.",
                "why_skip": "",
                "side_reason": f"Prior side from patch {veto_patch.get('side')}",
                "confidence_reason": "Moderate confidence before supervisor patch veto.",
                "risk_notes": [f"active_patch_action={veto_patch.get('action')}"],
            }

        if abs(change_pct) < 0.05:
            return {
                "candidate_side": "NONE",
                "final_action": "skip",
                "confidence": 0.25,
                "position_size_suggestion": 0.0,
                "regime": regime,
                "why_enter": "",
                "why_skip": "Flat 24h move; mock AI skips low-edge range.",
                "side_reason": "No directional edge in mock regime classifier.",
                "confidence_reason": "Confidence below trade threshold due to flat market.",
                "risk_notes": ["low_volatility_skip"],
            }

        side = "BUY" if change_pct >= 0 else "SELL"
        conf = min(0.72, 0.45 + abs(change_pct) * 0.05)
        return {
            "candidate_side": side,
            "final_action": "enter",
            "confidence": round(conf, 4),
            "position_size_suggestion": min(MAX_MARGIN_USD, 14.0 + abs(change_pct)),
            "regime": regime,
            "why_enter": f"Mock AI sees {regime} with 24h change {change_pct:.3f}%.",
            "why_skip": "",
            "side_reason": f"Side follows short-term demo signal ({side}).",
            "confidence_reason": f"Scaled confidence from abs(change_pct)={abs(change_pct):.3f}.",
            "risk_notes": ["mock_ai_dry_run_only"],
        }

    def _llm_proposal(
        self,
        *,
        symbol: str,
        market_context: Dict[str, Any],
        account_context: Dict[str, Any],
        patches: List[Dict[str, Any]],
        recent_trades: List[Dict[str, Any]],
        recent_reflections: List[Dict[str, Any]],
        open_positions: int,
        stage3_context: Dict[str, Any],
    ) -> tuple[Dict[str, Any], str, bool, str, Dict[str, Any]]:
        constraints = safety_constraints_from_env()
        messages = build_decision_prompt(
            symbol=symbol,
            market_context=market_context,
            account_context=account_context,
            retrieved_patches=summarize_patches(patches, limit=3),
            recent_trade_results=summarize_trades(recent_trades, limit=3),
            recent_reflections=summarize_reflections(recent_reflections, limit=3),
            safety_constraints=constraints,
            current_open_positions=open_positions,
            stage3_context=stage3_context,
        )
        prompt_hash = prompt_fingerprint(messages)
        result = self.llm_client.complete_json(messages, prompt_hash=prompt_hash, symbol=symbol)
        from tools.research.stage4_llm_client import ProviderRateLimited, Stage4LLMClient

        provider_meta = {
            "provider": str(
                result.get("provider")
                or getattr(getattr(self.llm_client, "config", None), "provider", None)
                or getattr(self, "provider", None)
                or "unknown"
            ),
            "model_name": str(result.get("model") or self.model_name),
            "provider_chain": result.get("provider_chain") or getattr(self.llm_client, "provider_chain", []),
            "provider_attempts": result.get("provider_attempts") or [],
            "fallback_used": bool(result.get("fallback_used")),
            "fallback_reason": result.get("fallback_reason"),
            "primary_provider": result.get("primary_provider"),
            "primary_error": result.get("primary_error"),
            "is_mock_ai": False,
            "finish_reason": result.get("finish_reason"),
            "response_text_chars": result.get("response_text_chars") or result.get("raw_content_length"),
            "cerebras_truncation_retry": bool(result.get("cerebras_truncation_retry")),
            "cerebras_truncation_retry_success": bool(result.get("cerebras_truncation_retry_success")),
            "cerebras_max_tokens_retry": result.get("cerebras_max_tokens_retry"),
        }

        if Stage4LLMClient.is_rate_limited_result(result):
            err_type = str(result.get("error_type") or "provider_rate_limited")
            raise ProviderRateLimited(
                provider=str(provider_meta["provider"]),
                model_name=str(provider_meta["model_name"]),
                symbol=symbol.upper(),
                retry_count=int(result.get("retry_count") or 0),
                reason=err_type,
                http_status=int(result.get("http_status") or 0) or None,
                gate_status={
                    "seconds_since_last_llm_call": result.get("seconds_since_last_llm_call"),
                    "required_wait_seconds": result.get("required_wait_seconds"),
                    "backoff_until_utc": result.get("backoff_until_utc"),
                },
                provider_attempts=provider_meta.get("provider_attempts"),
                fallback_used=bool(provider_meta.get("fallback_used")),
                fallback_reason=str(provider_meta.get("fallback_reason") or ""),
            )
        if str(result.get("error_type") or "") == "provider_chain_failed":
            raise ProviderRateLimited(
                provider=str(provider_meta["provider"]),
                model_name=str(provider_meta["model_name"]),
                symbol=symbol.upper(),
                retry_count=int(result.get("retry_count") or 0),
                reason="provider_chain_failed",
                event_type="provider_chain_failed",
                provider_attempts=provider_meta.get("provider_attempts"),
                fallback_used=bool(provider_meta.get("fallback_used")),
                fallback_reason=str(provider_meta.get("fallback_reason") or ""),
            )
        parsed = result.get("parsed") or {}
        proposal, ok, err = parse_llm_decision(parsed, symbol=symbol)
        schema_repair_meta: Dict[str, Any] = {}
        if not ok and result.get("status") == "ok":
            from tools.research.stage4_schema_repair import attempt_schema_safe_repair

            repaired, schema_repair_meta = attempt_schema_safe_repair(
                parsed,
                symbol=symbol,
                parse_error=err,
            )
            if repaired is not None:
                proposal = repaired
                ok = True
                err = ""
        if not ok or result.get("status") != "ok":
            err_type = result.get("parse_error_type") or result.get("error_type") or err or "llm_parse_failed"
            raw_nonempty = bool(str(result.get("raw_text") or "").strip())
            attempts = result.get("provider_attempts") or provider_meta.get("provider_attempts") or []
            if (
                err_type in {"content_empty", "empty_llm_response"} or bool(result.get("raw_content_empty"))
            ) and not raw_nonempty:
                if len(attempts) > 1:
                    raise ProviderRateLimited(
                        provider=str(provider_meta["provider"]),
                        model_name=str(provider_meta["model_name"]),
                        symbol=symbol.upper(),
                        retry_count=int(result.get("retry_count") or 0),
                        reason="provider_chain_failed",
                        event_type="provider_chain_failed",
                        provider_attempts=attempts,
                        fallback_used=bool(provider_meta.get("fallback_used")),
                        fallback_reason=str(provider_meta.get("fallback_reason") or ""),
                    )
                raise ProviderRateLimited(
                    provider=str(provider_meta["provider"]),
                    model_name=str(provider_meta["model_name"]),
                    symbol=symbol.upper(),
                    retry_count=int(result.get("retry_count") or 0),
                    reason="empty_llm_response",
                    provider_attempts=attempts,
                )
            proposal["parse_error"] = True
            proposal["parse_error_type"] = normalize_parse_error_type(
                err_type,
                raw_content_empty=bool(result.get("raw_content_empty")),
                finish_reason=result.get("finish_reason"),
            )
            proposal["raw_content_empty"] = bool(result.get("raw_content_empty"))
            proposal["why_skip"] = err or result.get("error") or "llm_parse_failed"
            return proposal, prompt_hash, False, err or result.get("error") or err, provider_meta
        if schema_repair_meta:
            provider_meta.update(schema_repair_meta)
        if provider_meta["provider"]:
            self.provider = str(provider_meta["provider"])
        if provider_meta["model_name"]:
            self.model_name = str(provider_meta["model_name"])
        return proposal, prompt_hash, True, "", provider_meta

    def decide(
        self,
        *,
        symbol: str,
        mode: str = "dry_run",
        market_context: Dict[str, Any],
        account_context: Dict[str, Any],
        open_positions: int = 0,
    ) -> Dict[str, Any]:
        patches = self.retriever.retrieve(symbol=symbol, side="NONE", limit=3)
        stage3_ctx = load_stage3_context(self.retriever.stage3_dir, symbol=symbol)
        recent_trades_raw = self.retriever.recent_trades(symbol=symbol, limit=3)
        recent_reflections_raw = self.retriever.recent_reflections(limit=3)
        recent_trades = stage3_ctx.get("recent_trade_results") or summarize_trades(recent_trades_raw, limit=3)
        recent_reflections = stage3_ctx.get("recent_reflections") or summarize_reflections(
            recent_reflections_raw, limit=3
        )
        parse_error = False
        llm_parse_ok = True
        provider_meta: Dict[str, Any] = {}

        if self.real_llm_used and self.llm_client:
            proposal, prompt_hash, llm_parse_ok, _, provider_meta = self._llm_proposal(
                symbol=symbol,
                market_context=market_context,
                account_context=account_context,
                patches=patches,
                recent_trades=recent_trades_raw,
                recent_reflections=recent_reflections_raw,
                open_positions=open_positions,
                stage3_context=stage3_ctx,
            )
            parse_error = not llm_parse_ok or bool(proposal.get("parse_error"))
        else:
            payload = json.dumps(
                {
                    "symbol": symbol,
                    "market": market_context,
                    "patches": len(patches),
                },
                sort_keys=True,
            )
            prompt_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
            proposal = self._mock_proposal(symbol=symbol, market_context=market_context, patches=patches)

        supervisor_result = self.supervisor.evaluate(
            proposal=proposal,
            account_context=account_context,
            retrieved_patches=patches,
            open_positions=open_positions,
            market_context=market_context,
            dry_run=True,
        )
        if parse_error:
            supervisor_result.approved = False
            supervisor_result.final_decision = "skip"
            supervisor_result.veto_reason = proposal.get("why_skip") or "parse_error"
            supervisor_result.action = "force_skip"

        sr = supervisor_result.to_dict()
        final_decision = sr["final_decision"]
        final_action = "skip" if final_decision == "skip" else proposal.get("final_action", "skip")

        if not sr.get("approved") and final_decision == "skip" and not proposal.get("why_skip"):
            proposal["why_skip"] = sr.get("veto_reason") or "Risk supervisor veto."
            proposal["why_enter"] = ""

        blockers = blocking_patches(patches)
        veto = str(sr.get("veto_reason") or "")
        patch_blocked = bool(blockers) and veto in {"patch_block", "manual_review_required"}

        row = {
            "decision_id": str(uuid.uuid4()),
            "created_at_utc": utc_now_iso(),
            "decision_source": self.decision_source,
            "mode": mode,
            "model_name": self.model_name,
            "provider": provider_meta.get("provider") or self.provider or (None if self.is_mock_ai else ""),
            "provider_chain": provider_meta.get("provider_chain") or [],
            "provider_attempts": provider_meta.get("provider_attempts") or [],
            "fallback_used": bool(provider_meta.get("fallback_used")),
            "fallback_reason": provider_meta.get("fallback_reason"),
            "primary_provider": provider_meta.get("primary_provider"),
            "primary_error": provider_meta.get("primary_error"),
            "is_mock_ai": self.is_mock_ai,
            "real_llm_used": self.real_llm_used,
            "fallback_to_mock": self.fallback_to_mock,
            "fallback_model_name": MOCK_MODEL_NAME if self.fallback_to_mock else None,
            "prompt_hash": prompt_hash,
            "symbol": symbol.upper(),
            "candidate_side": proposal.get("candidate_side", "NONE"),
            "final_action": final_action,
            "confidence": proposal.get("confidence", 0),
            "position_size_suggestion": proposal.get("position_size_suggestion", 0),
            "market_context": market_context,
            "account_context": account_context,
            "retrieved_patches": patches,
            "recent_trade_results": recent_trades,
            "recent_reflections": recent_reflections,
            "active_patch_count": len(patches),
            "patch_applied_before_decision": bool(patches),
            "current_open_positions": open_positions,
            "why_enter": proposal.get("why_enter", ""),
            "why_skip": proposal.get("why_skip", ""),
            "side_reason": proposal.get("side_reason", ""),
            "confidence_reason": proposal.get("confidence_reason", ""),
            "risk_notes": proposal.get("risk_notes", []),
            "patch_awareness": proposal.get("patch_awareness", ""),
            "uncertainty": proposal.get("uncertainty", ""),
            "reasoning_summary": proposal.get("why_enter") or proposal.get("why_skip") or "",
            "regime": proposal.get("regime") or market_context.get("regime", "unknown"),
            "decision_intent": proposal.get("decision_intent"),
            "missing_data": proposal.get("missing_data") or [],
            "edge_factors": proposal.get("edge_factors") or [],
            "risk_factors": proposal.get("risk_factors") or [],
            "stage3_context_summary": {
                "stage3_context_available": stage3_ctx.get("stage3_context_available", False),
                "stage3_context_reason": stage3_ctx.get("stage3_context_reason", "unknown"),
                "recent_trade_results_count": stage3_ctx.get("recent_trade_results_count", len(recent_trades)),
                "recent_reflections_count": stage3_ctx.get("recent_reflections_count", len(recent_reflections)),
                "active_patches_count": stage3_ctx.get("active_patches_count", len(patches)),
                "recent_trade_results": recent_trades[:5],
                "recent_reflections": recent_reflections[:5],
                "active_patches": summarize_patches(patches, limit=5),
            },
            "stage3_context_available": stage3_ctx.get("stage3_context_available", False),
            "stage3_context_reason": stage3_ctx.get("stage3_context_reason", "unknown"),
            "recent_trade_results_count": stage3_ctx.get("recent_trade_results_count", len(recent_trades)),
            "recent_reflections_count": stage3_ctx.get("recent_reflections_count", len(recent_reflections)),
            "active_patches_count": stage3_ctx.get("active_patches_count", len(patches)),
            "patch_blocked": patch_blocked,
            "patch_block_reason": (
                f"active_patch_{blockers[0].get('action')}" if patch_blocked and blockers else ""
            ),
            "matched_patch_count": len(blockers),
            "matched_patch_actions": [str(p.get("action") or "") for p in blockers],
            "parse_error": parse_error,
            "parse_error_type": (
                normalize_parse_error_type(
                    proposal.get("parse_error_type"),
                    raw_content_empty=bool(proposal.get("raw_content_empty")),
                    finish_reason=provider_meta.get("finish_reason"),
                )
                if parse_error
                else None
            ),
            "raw_content_empty": proposal.get("raw_content_empty"),
            "finish_reason": provider_meta.get("finish_reason"),
            "response_text_chars": provider_meta.get("response_text_chars"),
            "cerebras_truncation_retry": bool(provider_meta.get("cerebras_truncation_retry")),
            "cerebras_truncation_retry_success": provider_meta.get("cerebras_truncation_retry_success"),
            "cerebras_max_tokens_retry": provider_meta.get("cerebras_max_tokens_retry"),
            "schema_repaired": bool(proposal.get("schema_repaired") or provider_meta.get("schema_repaired")),
            "schema_repair_mode": proposal.get("schema_repair_mode") or provider_meta.get("schema_repair_mode"),
            "schema_mismatch_repair_attempted": bool(
                provider_meta.get("schema_mismatch_repair_attempted")
            ),
            "safety_constraints": safety_constraints_from_env(),
            "risk_supervisor_result": sr,
            "final_decision": final_decision,
            "order_sent": False,
        }
        return row


def write_decision(output_dir: Path, decision: Dict[str, Any]) -> None:
    append_jsonl(output_dir / "ai_decisions.jsonl", decision)
    append_jsonl(
        output_dir / "risk_supervisor_decisions.jsonl",
        {
            "decision_id": decision["decision_id"],
            "created_at_utc": decision["created_at_utc"],
            "symbol": decision["symbol"],
            "real_llm_used": decision.get("real_llm_used"),
            "parse_error": decision.get("parse_error"),
            "risk_supervisor_result": decision["risk_supervisor_result"],
            "final_decision": decision["final_decision"],
            "order_sent": False,
        },
    )
