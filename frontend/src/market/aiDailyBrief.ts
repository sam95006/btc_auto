/**
 * AI Daily Brief data contract — rules-only / unavailable honest.
 * Shared by FloatingAIAssistant and Product Simple View entry.
 */

import { buildMarketSummary, deriveRegime, type PulseInput } from "./marketSummary";
import type { MarketCandidate } from "./scannerApi";

export type AiBriefMode = "rules-only" | "unavailable";

export type AiDailyBrief = {
  mode: AiBriefMode;
  conclusion: string;
  evidence: string[];
  contradicting: string[];
  risk: string;
  invalidation: string;
  freshness: string;
  decisionTrace: string;
  provider: "rules-engine" | "none";
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
  const invalidation = "研究模式 · 無下單權限 · Stage 4.19 blocked";

  if (input.llmAvailable) {
    return {
      mode: "unavailable",
      conclusion: "LLM provider 尚未接入。",
      evidence: [],
      contradicting: [],
      risk: "—",
      invalidation,
      freshness,
      decisionTrace: "llm-provider · not configured",
      provider: "none",
    };
  }

  if (input.loading && !input.pulse.symbolCount && input.pulse.freshness == null) {
    return {
      mode: "unavailable",
      conclusion: "掃描器資料尚未就緒，無法產生可靠簡報。",
      evidence: [],
      contradicting: [],
      risk: "資料不足",
      invalidation,
      freshness,
      decisionTrace: "rules-engine · awaiting scanner",
      provider: "none",
    };
  }

  const regime = deriveRegime(input.pulse);
  const summary = buildMarketSummary(input.pulse);
  const topL = input.longs[0];
  const topS = input.shorts[0];

  return {
    mode: "rules-only",
    conclusion: `今日規則簡報：${summary}`,
    evidence: [
      `做多 ${input.pulse.longCandidates ?? "—"} · 做空 ${input.pulse.shortCandidates ?? "—"}`,
      `已確認 ${input.pulse.confirmedCandidates ?? "—"} · 高風險 ${input.pulse.highRiskCandidates ?? "—"}`,
      topL ? `焦點多：${topL.symbol}` : "焦點多：無",
      topS ? `焦點空：${topS.symbol}` : "焦點空：無",
      `市場狀態：${regime}`,
    ],
    contradicting: ["此簡報非 LLM 生成，缺少敘事推理"],
    risk: `市場狀態 ${regime}`,
    invalidation,
    freshness,
    decisionTrace: "rules-engine · no LLM provider configured",
    provider: "rules-engine",
  };
}
