/** Phase 6.5 — Learning hub shell. */
export function LearningPage() {
  const topics = [
    "Indicators & OHLCV basics",
    "Funding / OI / CVD explained",
    "Why Risk Gate blocks entries",
    "Reading AI evidence (3 levels)",
    "Platform usage",
  ];
  return (
    <div className="page-stack">
      <header>
        <h1>學習</h1>
        <p className="muted">Education content — links to academy and evidence.</p>
      </header>
      <ul>
        {topics.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </div>
  );
}
