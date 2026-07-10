export function RiskScoreBadge({ score }: { score: number }) {
  const level = score >= 70 ? "high" : score >= 45 ? "mid" : "low";
  return (
    <span className={`risk-badge ${level}`}>
      Risk {score}
    </span>
  );
}
