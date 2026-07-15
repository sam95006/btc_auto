import { FEATURE_MAP } from "../demo/productUx";
import { StatusBadge } from "./StatusBadge";

/** Product capability map — Future items explicitly NOT IMPLEMENTED (MVP-21). */
export function FeatureCompletenessMap() {
  const completed = FEATURE_MAP.filter((i) => i.bucket === "completed");
  const waiting = FEATURE_MAP.filter((i) => i.bucket === "waiting");
  const future = FEATURE_MAP.filter((i) => i.bucket === "future");

  return (
    <section id="feature-map" className="operator-section">
      <div className="section-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          Feature Completeness Map
        </h2>
      </div>
      <p className="muted section-lede">
        What this Private Operator console can do today vs waiting vs future-only stubs.
      </p>
      <div className="feature-map-grid">
        <article className="panel-card dense-card">
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>Completed</h3>
            <StatusBadge tone="pass">ready</StatusBadge>
          </div>
          <ul className="feature-map-list">
            {completed.map((i) => (
              <li key={i.id}>
                <strong>{i.label}</strong>
                <span className="muted"> — {i.note}</span>
              </li>
            ))}
          </ul>
        </article>
        <article className="panel-card dense-card">
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>In progress / waiting</h3>
            <StatusBadge tone="wait">HOLD</StatusBadge>
          </div>
          <ul className="feature-map-list">
            {waiting.map((i) => (
              <li key={i.id}>
                <strong>{i.label}</strong>
                <span className="muted"> — {i.note}</span>
              </li>
            ))}
          </ul>
        </article>
        <article className="panel-card dense-card">
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>Future only</h3>
            <StatusBadge tone="blocked">NOT IMPLEMENTED</StatusBadge>
          </div>
          <ul className="feature-map-list">
            {future.map((i) => (
              <li key={i.id}>
                <strong>{i.label}</strong>
                <span className="muted"> — {i.note}</span>
              </li>
            ))}
          </ul>
        </article>
      </div>
    </section>
  );
}
