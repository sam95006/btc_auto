import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

type Funnel = {
  ok?: boolean;
  candidateCount?: number;
  decisionCount?: number;
  riskPassCount?: number;
  riskBlockCount?: number;
  entryEligibleCount?: number;
  orderCount?: number;
  zeroOrderDiagnosis?: string;
  topBlockedSetups?: { reason: string; count: number }[];
};

export function PaperDecisionFunnelPanel() {
  const [data, setData] = useState<Funnel | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/nexus/paper/decision-funnel?windowHours=24")
      .then((r) => r.json())
      .then((j) => {
        if (alive) setData(j);
      })
      .catch((e) => {
        if (alive) setErr(String(e));
      });
    return () => {
      alive = false;
    };
  }, []);

  if (err) return <p className="muted">Funnel unavailable: {err}</p>;
  if (!data?.ok) return <p className="muted">Loading decision funnel…</p>;

  return (
    <section className="nx-card nx-funnel-panel">
      <h3>Natural PAPER Decision Funnel</h3>
      <p className="muted">{data.zeroOrderDiagnosis}</p>
      <div className="nx-funnel-grid">
        <div><strong>{data.candidateCount ?? 0}</strong><span>Candidates</span></div>
        <div><strong>{data.decisionCount ?? 0}</strong><span>Decisions</span></div>
        <div><strong>{data.riskPassCount ?? 0}</strong><span>Risk pass</span></div>
        <div><strong>{data.riskBlockCount ?? 0}</strong><span>Risk block</span></div>
        <div><strong>{data.entryEligibleCount ?? 0}</strong><span>Entry eligible</span></div>
        <div><strong>{data.orderCount ?? 0}</strong><span>Orders</span></div>
      </div>
      {data.topBlockedSetups?.length ? (
        <ul className="nx-funnel-blocks">
          {data.topBlockedSetups.slice(0, 5).map((b) => (
            <li key={b.reason}>{b.reason}: {b.count}</li>
          ))}
        </ul>
      ) : null}
      <p className="muted">
        Gates unchanged — read-only observability.{" "}
        <Link to="/opportunities">View opportunities →</Link>
      </p>
    </section>
  );
}
