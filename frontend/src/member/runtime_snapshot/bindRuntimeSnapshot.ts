/**
 * Bind Runtime Snapshot → existing Live Funnel first-screen model (extend, don't rewrite).
 */
import {
  FUNNEL_STAGE_DEFS,
  formatFunnelCount,
  type AiPosture,
  type LiveFunnelFirstScreenModel,
  type PulseAnswer,
  type TopOpportunity,
  PULSE_QUESTIONS,
} from "../live_funnel/liveFunnelModels";
import type { RuntimeSnapshot } from "./runtimeSnapshotContract";
import { runtimeHonestyLabel } from "./runtimeSnapshotContract";

function postureFromSnapshot(snap: RuntimeSnapshot): AiPosture {
  const raw = String(snap.shadow_status?.last_decision || "ABSTAIN").toUpperCase();
  if (raw === "LONG" || raw === "SHORT" || raw === "WAIT" || raw === "ABSTAIN") return raw;
  return "ABSTAIN";
}

export function bindRuntimeSnapshotToFunnel(
  snap: RuntimeSnapshot,
): LiveFunnelFirstScreenModel {
  const chrome = runtimeHonestyLabel(snap);
  const dataClass = String(snap.data_class || chrome);
  const freshness = String(snap.data_freshness || chrome);
  const available = Boolean(snap.universe_funnel?.available) && Boolean(snap.is_live_view || snap.universe_funnel?.available);
  const funnel = snap.universe_funnel;
  const counts: Record<string, number | null> = {
    scanned: funnel?.contracts_scanned ?? null,
    data_available: funnel?.eligible ?? null,
    liquidity: funnel?.observe_only ?? null,
    data_trust: funnel?.eligible ?? null,
    candidate: funnel?.candidates ?? null,
    ai_review: snap.AI_gateway_status?.AI_requests ?? null,
    cost_blocked: available ? 0 : null,
    risk_blocked: funnel?.blocked ?? null,
    shadow_decisions: snap.shadow_status?.shadow_opened_count ?? null,
  };

  // When not live, still show counts if present but chrome must be non-Live.
  const stages = FUNNEL_STAGE_DEFS.map((s) => {
    const count = counts[s.id];
    const stageAvailable = funnel?.available === true && count != null;
    return {
      id: s.id,
      label: s.label,
      count: stageAvailable ? count : null,
      available: stageAvailable,
      display: formatFunnelCount(
        stageAvailable ? count : null,
        stageAvailable,
        snap.is_live_view ? dataClass : chrome,
      ),
    };
  });

  const top: TopOpportunity[] = (snap.top_opportunities || []).slice(0, 3).map((t) => ({
    rank: t.rank,
    market: t.market,
    contract: t.contract,
    side_hint: t.side_hint,
    note: t.note,
  }));

  const posture = postureFromSnapshot(snap);
  const reasons = snap.degraded_reasons || [];

  const answers: PulseAnswer[] = [
    {
      id: "global_market_state",
      question: PULSE_QUESTIONS.global_market_state,
      answer: snap.is_live_view
        ? `Runtime ${snap.runtime_state} · source ${snap.source_health?.status}`
        : `${chrome} — not Live`,
      detail: `last_updated=${snap.last_updated || "UNAVAILABLE"}`,
      state: dataClass,
    },
    {
      id: "crypto_derivatives_risk",
      question: PULSE_QUESTIONS.crypto_derivatives_risk,
      answer: `Source ${snap.source_health?.status || "UNAVAILABLE"} · AI ${snap.AI_gateway_status?.health || "UNAVAILABLE"}`,
      detail: `actual_ordered=${String(snap.actual_ordered)} · actual_filled=${String(snap.actual_filled)}`,
      state: dataClass,
      metrics: [
        {
          key: "source_health",
          display: String(snap.source_health?.status || "UNAVAILABLE"),
          available: Boolean(snap.source_health?.status),
        },
        {
          key: "AI_gateway",
          display: String(snap.AI_gateway_status?.health || "UNAVAILABLE"),
          available: Boolean(snap.AI_gateway_status?.health),
        },
      ],
    },
    {
      id: "top_3_opportunities",
      question: PULSE_QUESTIONS.top_3_opportunities,
      answer: top.length
        ? top.map((t) => `${t.market} (${t.side_hint})`).join(" · ")
        : chrome,
      detail: "Public opportunities only · Shadow Decisions · no trade buttons",
      state: dataClass,
      markets: top,
    },
    {
      id: "ai_posture",
      question: PULSE_QUESTIONS.ai_posture,
      answer: posture,
      detail: "Suggestion / Shadow Decision posture only — not an order",
      state: dataClass,
    },
    {
      id: "supporting_evidence",
      question: PULSE_QUESTIONS.supporting_evidence,
      answer: snap.lineage_id ? `lineage ${snap.lineage_id}` : chrome,
      detail: "runtime projection evidence",
      state: dataClass,
    },
    {
      id: "counter_evidence",
      question: PULSE_QUESTIONS.counter_evidence,
      answer: reasons.length ? reasons.join("; ") : "none in scope",
      detail: `${reasons.length} reason(s)`,
      state: dataClass,
    },
    {
      id: "invalidation",
      question: PULSE_QUESTIONS.invalidation,
      answer: snap.is_live_view
        ? "Invalidate when Data Trust / eligibility gates fail"
        : "Live view invalidated — runtime not live",
      detail: snap.is_live_view ? "status=INTACT" : "status=INVALIDATED",
      state: dataClass,
    },
    {
      id: "data_freshness",
      question: PULSE_QUESTIONS.data_freshness,
      answer: freshness,
      detail: "RUNTIME_STOPPED / STALE / UNAVAILABLE when not live",
      state: freshness,
    },
    {
      id: "data_class_label",
      question: PULSE_QUESTIONS.data_class_label,
      answer: dataClass,
      detail: `chrome=${chrome} · actual_ordered=false · actual_filled=false`,
      state: dataClass,
      actually_traded: false,
    },
  ];

  return {
    caseId: `v18_1_runtime_${snap.lineage_id || "na"}`,
    dataClass,
    chromeLabel: chrome,
    answers,
    aiPosture: posture,
    dataFreshness: freshness,
    funnel: {
      stages,
      summary: stages.map((s) => `${s.label}: ${s.display}`).join(" → "),
    },
    note:
      snap.note ||
      `${chrome} · READ ONLY · Shadow Decisions only · NOT INVESTMENT ADVICE · no trade buttons`,
    tradeButtons: false,
  };
}
