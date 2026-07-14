import { PROVIDER_WATCH_BARS } from "../demo/providerHistory";
import { DemoDataBadge } from "./DemoDataBadge";

/** CSS bar chart — Groq vs Cerebras valid_watch (sanitized static, MVP-18). */
export function ProviderHistoryChart() {
  const max = Math.max(
    1,
    ...PROVIDER_WATCH_BARS.flatMap((b) => [b.groq, b.cerebras]),
  );

  return (
    <section id="provider-history-chart" className="panel-card dense-card">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>Groq vs Cerebras valid_watch</h3>
        <span className="demo-badge">SANITIZED STATIC</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Static metadata bars only · no live series · no /data · no backend · NOT INVESTMENT ADVICE
      </p>
      <div className="provider-bar-list">
        {PROVIDER_WATCH_BARS.map((b) => (
          <div key={b.label} className="provider-bar-row">
            <div className="k">{b.label}</div>
            <div className="provider-bar-tracks">
              <div className="provider-bar-track">
                <span className="mono">Groq {b.groq}</span>
                <div className="provider-bar-fill groq" style={{ width: `${(b.groq / max) * 100}%` }} />
              </div>
              <div className="provider-bar-track">
                <span className="mono">Cerebras {b.cerebras}</span>
                <div
                  className="provider-bar-fill cerebras"
                  style={{ width: `${(b.cerebras / max) * 100}%` }}
                />
              </div>
            </div>
            <div className="muted">{b.note}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
