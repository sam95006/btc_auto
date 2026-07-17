/** Transparent market summary line from real scanner pulse (no LLM). */

export type PulseInput = {
  longCandidates?: number;
  shortCandidates?: number;
  confirmedCandidates?: number;
  highRiskCandidates?: number;
  breadth?: { rising: number; falling: number; neutral: number; insufficient: number };
  symbolCount?: number;
  freshness?: string;
};

export type RegimeLabel = "偏多" | "偏空" | "多空混合" | "低動能" | "資料累積中";

export function deriveRegime(p: PulseInput): RegimeLabel {
  const b = p.breadth;
  const insuff = b?.insufficient ?? 0;
  const sym = p.symbolCount ?? 0;
  if (sym > 0 && insuff >= Math.max(1, sym * 0.7)) return "資料累積中";
  const rising = b?.rising ?? 0;
  const falling = b?.falling ?? 0;
  const ready = rising + falling + (b?.neutral ?? 0);
  if (ready < 8) return "資料累積中";
  if (rising + falling < 6) return "低動能";
  if (rising > falling * 1.25) return "偏多";
  if (falling > rising * 1.25) return "偏空";
  return "多空混合";
}

export function buildMarketSummary(p: PulseInput): string {
  const regime = deriveRegime(p);
  const longs = p.longCandidates ?? 0;
  const shorts = p.shortCandidates ?? 0;
  const risk = p.highRiskCandidates ?? 0;
  const confirmed = p.confirmedCandidates ?? 0;

  if (regime === "資料累積中") {
    return "掃描器正在累積 5 分鐘窗口；排名將在資料足夠後出現。";
  }
  if (regime === "低動能") {
    return "市場動能偏低，多數標的仍在觀察，暫時沒有強烈方向優勢。";
  }

  const balance =
    longs === shorts
      ? "做多與做空候選數量接近"
      : longs > shorts
        ? "做多候選略多"
        : "做空候選略多";

  const riskNote =
    risk > 0 ? `，另有 ${risk} 個高風險／過熱標的需留意` : "，高風險標的暫時不多";

  const confNote = confirmed > 0 ? `；已確認候選 ${confirmed} 個` : "";

  if (regime === "偏多") {
    return `市場偏多，${balance}${riskNote}${confNote}。`;
  }
  if (regime === "偏空") {
    return `市場偏空，${balance}${riskNote}${confNote}。`;
  }
  return `市場多空分歧，${balance}${riskNote}${confNote}。`;
}
