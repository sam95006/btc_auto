import { WHY_SAFE_ITEMS } from "../demo/productUx";
import { StatusBadge } from "./StatusBadge";

/** Risk Center first screen — why HOLD research mode is safe (MVP-21). */
export function WhySafeSection() {
  return (
    <section id="why-safe" className="operator-section">
      <div className="section-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          Why this is safe
        </h2>
        <StatusBadge tone="pass">PASS</StatusBadge>
        <StatusBadge tone="hold">READ ONLY</StatusBadge>
      </div>
      <p className="muted section-lede">
        Plain-language safety invariants. NOT INVESTMENT ADVICE · no trading controls.
      </p>
      <div className="why-safe-grid">
        {WHY_SAFE_ITEMS.map((item) => (
          <article key={item.id} className="panel-card dense-card why-safe-card">
            <h3 style={{ margin: 0, fontSize: "0.9rem" }}>{item.label}</h3>
            <p className="muted" style={{ marginBottom: 0 }}>
              {item.explanation}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
