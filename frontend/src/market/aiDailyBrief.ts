/**
 * AI Daily Brief data contract (Product 7.2) — traceable, rules-only honest.
 *
 * CONTRACT:
 *   mode:         "rules-only" (no LLM) | "unavailable" (data insufficient).
 *   provider:     "rules-engine" | "none" — never claims LLM without wired provider.
 *   label:        Always shows RULES-ONLY or UNAVAILABLE. Never pretends LLM.
 *
 * STRUCTURE:
 *   Conclusion         — one-line market state summary from rules
 *   Evidence           — supporting data points (concrete, sourced)
 *   ContradictingEvidence — what rules CAN'T confirm or actively contradicts
 *   Risk               — specific risk factors surfaced by rules
 *   Invalidation       — conditions that would invalidate this brief
 *   Freshness          — data timestamp context
 *   DecisionTrace      — exact rule path that produced this output
 *
 * NEVER: generate narrative conclusions not traceable to rule inputs.
 * NEVER: claim "AI says" when no LLM provider is configured.
 */

import { buildMarketSummary, deriveRegime, type PulseInput } from "./marketSummary";
import type { MarketCandidate } from "./scannerApi";

export type AiBriefMode = "rules-only" | "unavailable";

export type AiDailyBrief = {
  /** Mode label — always shown in UI. */
  mode: AiBriefMode;
  /** One-line summary conclusion derived from rules only. */
  conclusion: string;
  /** Concrete evidence points traceable to real data inputs. */
  evidence: string[];
  /** What the rules engine could NOT confirm, or what contradicts conclusion. */
  contradictingEvidence: string[];
  /** Specific risk factors from rule evaluation. */
  risk: string;
  /** Conditions under which this brief is invalidated (must be re-run). */
  invalidation: string;
  /** Invalidation triggers — concrete data changes that invalidate the brief. */
  invalidationTriggers: string[];
  /** Freshness context — data staleness information. */
  freshness: string;
  /** Full rule trace — provider → rules evaluated → outputs. */
  decisionTrace: string;
  /** Structured trace for Pro View display. */
  traceSteps: Array<{ step: string; input: string; output: string }>;
  /** Who produced this brief. */
  provider: "rules-engine" | "none";
  /** ISO timestamp when brief was generated. */
  generatedAt: string;
};

export type DailyBriefInput = {
  pulse: PulseInput;
  longs: MarketCandidate[];
  shorts: MarketCandidate[];
  loading?: boolean;
  llmAvailable?: boolean;
};

export function buildAiDailyBrief(input: DailyBriefInput): AiDailyBrief {
  const freshness = input.pulse.freshness || "更新時間未知";
  const generatedAt = new Date().toISOString();
  const invalidation = "研究模式 · 無下單權限 · Stage 4.19 blocked";
  const invalidationTriggers = [
    "掃描器 freshness > 5 分鐘 → 重新載入",
    "市場狀態從穩定轉換 → 結論失效",
    "高風險候選大幅增加 → Risk 欄位更新",
    "LLM provider 上線 → 切換至 LLM 模式",
  ];

  if (input.llmAvailable) {
    return {
      mode: "unavailable",
      conclusion: "LLM provider 尚未接入。",
      evidence: [],
      contradictingEvidence: ["LLM provider 不可用 — 規則簡報亦無法替代 LLM 推理"],
      risk: "—",
      invalidation,
      invalidationTriggers,
      freshness,
      decisionTrace: "llm-provider · not configured",
      traceSteps: [
        { step: "provider-check", input: "llmAvailable=true", output: "UNAVAILABLE — not wired" },
      ],
      provider: "none",
      generatedAt,
    };
  }

  if (input.loading && !input.pulse.symbolCount && input.pulse.freshness == null) {
    return {
      mode: "unavailable",
      conclusion: "掃描器資料尚未就緒，無法產生可靠簡報。",
      evidence: [],
      contradictingEvidence: ["掃描器尚無有效數據 — 所有衍生結論均不可靠"],
      risk: "資料不足",
      invalidation,
      invalidationTriggers,
      freshness,
      decisionTrace: "rules-engine · awaiting scanner",
      traceSteps: [
        { step: "data-check", input: "loading=true, symbolCount=null", output: "UNAVAILABLE — awaiting scanner" },
      ],
      provider: "none",
      generatedAt,
    };
  }

  const regime = deriveRegime(input.pulse);
  const summary = buildMarketSummary(input.pulse);
  const topL = input.longs[0];
  const topS = input.shorts[0];
  const longN = input.pulse.longCandidates ?? "—";
  const shortN = input.pulse.shortCandidates ?? "—";
  const confirmedN = input.pulse.confirmedCandidates ?? "—";
  const highRiskN = input.pulse.highRiskCandidates ?? "—";

  const traceSteps: AiDailyBrief["traceSteps"] = [
    { step: "regime-derive", input: `longCandidates=${longN}, shortCandidates=${shortN}`, output: `regime=${regime}` },
    { step: "summary-build", input: `regime=${regime}, breadth=...`, output: summary },
    { step: "top-long", input: `longs[0]=${topL?.symbol ?? "none"}`, output: topL ? `focus=${topL.symbol}` : "no-long-focus" },
    { step: "top-short", input: `shorts[0]=${topS?.symbol ?? "none"}`, output: topS ? `focus=${topS.symbol}` : "no-short-focus" },
    { step: "risk-eval", input: `highRiskCandidates=${highRiskN}`, output: `risk=market-state-${regime}` },
  ];

  return {
    mode: "rules-only",
    conclusion: `今日規則簡報（RULES-ONLY）：${summary}`,
    evidence: [
      `做多候選 ${longN} · 做空候選 ${shortN}`,
      `已確認 ${confirmedN} · 高風險 ${highRiskN}`,
      topL ? `最強多方焦點：${topL.symbol}（機會分 ${topL.opportunityScore ?? "—"}）` : "無多方焦點候選",
      topS ? `最強空方焦點：${topS.symbol}（機會分 ${topS.opportunityScore ?? "—"}）` : "無空方焦點候選",
      `市場狀態：${regime}`,
      `掃描新鮮度：${freshness}`,
    ],
    contradictingEvidence: [
      "此簡報非 LLM 生成，缺少敘事推理與跨市場關聯分析",
      "規則引擎不考慮宏觀事件、消息面、鏈上數據",
      confirmedN === "—" || confirmedN === 0
        ? "確認候選為 0 — 結論可信度低"
        : null,
      (typeof highRiskN === "number" && highRiskN > 3)
        ? `高風險候選 ${highRiskN} 個 — 偏多結論需謹慎`
        : null,
    ].filter((x): x is string => x != null),
    risk: `市場狀態 ${regime}${typeof highRiskN === "number" && highRiskN > 0 ? ` · ${highRiskN} 個高風險候選` : ""}`,
    invalidation,
    invalidationTriggers,
    freshness,
    decisionTrace: `rules-engine · regime=${regime} · longs=${longN} · shorts=${shortN} · confirmed=${confirmedN} · highRisk=${highRiskN}`,
    traceSteps,
    provider: "rules-engine",
    generatedAt,
  };
}
