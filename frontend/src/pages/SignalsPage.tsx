import { DemoDataBadge } from "../components/DemoDataBadge";
import { SignalStatusBadge } from "../components/SignalStatusBadge";
import { getSignals } from "../demo/nexusDataAdapter";

export function SignalsPage() {
  const rows = getSignals();

  return (
    <div>
      <header className="page-header">
        <h1>Signal / Anomaly Center</h1>
        <DemoDataBadge />
        <p className="page-sub">
          Taxonomy uses observe / watch / skip / blocked — never buy/sell labels.
        </p>
      </header>
      <div className="list-stack">
        {rows.map((s) => (
          <article key={s.id} className="panel-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>
                {s.symbol} · {s.id}
              </h3>
              <DemoDataBadge />
              <SignalStatusBadge status={s.status} />
            </div>
            <p>{s.reason}</p>
            <p className="muted">Risk: {s.risk}</p>
            <p className="muted">Invalidation: {s.invalidation}</p>
            <div className="meta-row">
              <span className="muted">MAE {s.mae}</span>
              <span className="muted">conf {(s.confidence * 100).toFixed(0)}%</span>
              <span className="muted">{s.dataQuality}</span>
              <span className="muted">{s.provider}</span>
              <span className="muted">evidence {s.evidenceId}</span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
