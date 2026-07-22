/** Phase 6.5 / Product 7 — Intelligence with honest provider status. */
export function IntelligencePage() {
  const layers: { name: string; status: "live" | "pending"; note: string }[] = [
    { name: "公開市場掃描（價格／OI／Funding）", status: "live", note: "Bybit Mainnet public linear" },
    { name: "市場異動雷達", status: "live", note: "讀取中異常與證據欄位" },
    { name: "版塊動能", status: "live", note: "Sector performance overlay" },
    { name: "News", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "Macro", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "On-chain", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "Stablecoin flow", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "DeFi", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "Social sentiment", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "Geopolitical risk", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
  ];
  return (
    <div className="page-stack nx-intel-p7">
      <header>
        <h1>情報</h1>
        <p className="muted">Extended intelligence — live layers vs honest pending providers.</p>
      </header>
      <ul className="nx-intel-pending">
        {layers.map((p) => (
          <li key={p.name}>
            <strong>{p.name}</strong> —{" "}
            {p.status === "live" ? (
              <span className="tag">LIVE</span>
            ) : (
              <span className="tag tag-warn">UNAVAILABLE_PROVIDER_PENDING</span>
            )}
            <span className="muted sm"> · {p.note}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
