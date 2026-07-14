import {
  BTC_PROVIDER_DIVERGENCE_SUMMARY,
  PROVIDER_DIVERGENCE_TIMELINE,
} from "../demo/providerHistory";
import { DemoDataBadge } from "./DemoDataBadge";

/** Sanitized provider divergence timeline (MVP-18). */
export function ProviderDivergenceTimeline() {
  return (
    <section id="provider-divergence-timeline" className="panel-card dense-card">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>Provider Divergence Timeline</h3>
        <span className="demo-badge">SANITIZED</span>
        <DemoDataBadge />
      </div>
      <p className="muted">{BTC_PROVIDER_DIVERGENCE_SUMMARY}</p>
      <ol className="provider-timeline">
        {PROVIDER_DIVERGENCE_TIMELINE.map((e) => (
          <li key={e.id} id={e.id === "btc-exp" ? "btc-cerebras-first" : undefined}>
            <div className="mono muted">{e.stage}</div>
            <strong>{e.title}</strong>
            <div className="muted">{e.summary}</div>
          </li>
        ))}
      </ol>
      <p className="muted" style={{ marginBottom: 0 }}>
        READ ONLY · shadow not used for graduation · permanent routing=false · no routing editor
      </p>
    </section>
  );
}
