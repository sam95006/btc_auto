import type { ActionAdvice, MarketBias, RiskLevel } from "../types/dto";

export function BiasChip({ bias, label }: { bias: MarketBias; label: string }) {
  const cls =
    bias === "bullish" ? "mpv1-chip-bull" : bias === "bearish" ? "mpv1-chip-bear" : "mpv1-chip-neutral";
  return <span className={`mpv1-chip ${cls}`}>{label}</span>;
}

export function AdviceChip({ label }: { advice?: ActionAdvice; label: string }) {
  return <span className="mpv1-chip mpv1-chip-advice">{label}</span>;
}

export function RiskChip({ risk, label }: { risk: RiskLevel; label: string }) {
  const cls =
    risk === "low" ? "mpv1-chip-risk-low" : risk === "high" ? "mpv1-chip-risk-high" : "mpv1-chip-risk-medium";
  return <span className={`mpv1-chip ${cls}`}>{label}</span>;
}

export function ScorePill({ score }: { score: number | null }) {
  if (score == null) return <span className="mpv1-score">—</span>;
  return (
    <span className="mpv1-score">
      {score} <span>/ 100</span>
    </span>
  );
}
