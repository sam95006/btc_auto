/** Phase 6.5 — Intelligence placeholder with honest provider status. */
export function IntelligencePage() {
  const pending = [
    "News", "Macro", "On-chain", "Stablecoin flow", "DeFi", "Social sentiment", "Geopolitical risk",
  ];
  return (
    <div className="page-stack">
      <header>
        <h1>情報</h1>
        <p className="muted">Extended intelligence layers — provider integration pending.</p>
      </header>
      <ul className="nx-intel-pending">
        {pending.map((p) => (
          <li key={p}>
            <strong>{p}</strong> — <span className="tag tag-warn">UNAVAILABLE_PROVIDER_PENDING</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
