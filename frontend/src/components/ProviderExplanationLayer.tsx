import { PROVIDER_EXPLAIN } from "../demo/productUx";

/** Provider page plain-language meaning layer (MVP-21). */
export function ProviderExplanationLayer() {
  return (
    <section id="provider-explain" className="operator-section">
      <div className="section-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          What this means
        </h2>
      </div>
      <p className="muted section-lede">
        Product language for Provider Intelligence. Permanent routing stays false · no routing
        editor.
      </p>
      <div className="provider-explain-grid">
        {PROVIDER_EXPLAIN.map((item) => (
          <article key={item.id} className="panel-card dense-card">
            <h3 style={{ margin: 0, fontSize: "0.9rem" }}>{item.title}</h3>
            <p className="muted" style={{ marginBottom: 0 }}>
              {item.meaning}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
