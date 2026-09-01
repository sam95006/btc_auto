/** Locale-aware display labels for backend market states (regime / volatility /
 * risk / attention). Keeps the reused data panels single-language (no bilingual
 * clutter). Technical field names (Regime, 24H, Source…) stay English as
 * intentional secondary labels across all locales. */
import type { Locale } from "../i18n";

const REGIME: Record<Locale, Record<string, string>> = {
  "zh-TW": { RISK_ON: "偏多", RISK_OFF: "防禦", NEUTRAL: "中性" },
  "en-US": { RISK_ON: "Risk-On", RISK_OFF: "Risk-Off", NEUTRAL: "Neutral" },
  "ja-JP": { RISK_ON: "リスクオン", RISK_OFF: "リスクオフ", NEUTRAL: "中立" },
  "ko-KR": { RISK_ON: "위험선호", RISK_OFF: "위험회피", NEUTRAL: "중립" },
};
const VOL: Record<Locale, Record<string, string>> = {
  "zh-TW": { high: "偏高", moderate: "中等", low: "偏低" },
  "en-US": { high: "High", moderate: "Moderate", low: "Low" },
  "ja-JP": { high: "高", moderate: "中", low: "低" },
  "ko-KR": { high: "높음", moderate: "보통", low: "낮음" },
};
const RISK: Record<Locale, Record<string, string>> = {
  "zh-TW": { elevated: "偏高", moderate: "中等", contained: "受控" },
  "en-US": { elevated: "Elevated", moderate: "Moderate", contained: "Contained" },
  "ja-JP": { elevated: "高", moderate: "中", low: "低", contained: "抑制" },
  "ko-KR": { elevated: "높음", moderate: "보통", contained: "통제" },
};

export function regimeLabel(v: string | null | undefined, loc: Locale): string {
  return v ? REGIME[loc]?.[v] ?? v : "—";
}
export function volLabel(v: string | null | undefined, loc: Locale): string {
  return v ? VOL[loc]?.[v] ?? v : "—";
}
export function riskLabel(v: string | null | undefined, loc: Locale): string {
  return v ? RISK[loc]?.[v] ?? v : "—";
}
