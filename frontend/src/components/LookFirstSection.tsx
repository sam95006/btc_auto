import { Link } from "react-router-dom";
import { LOOK_FIRST_CARDS } from "../demo/productUx";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";

/** Plain-language first clicks for non-engineers (MVP-21). */
export function LookFirstSection() {
  return (
    <section id="look-first" className="operator-section look-first-section">
      <div className="section-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          What should I look at first?
        </h2>
      </div>
      <p className="muted section-lede">
        You do not need to know the full system. Start with these three.
      </p>
      <div className="look-first-grid">
        {LOOK_FIRST_CARDS.map((card) => (
          <article key={card.id} className="panel-card dense-card look-first-card">
            <h3 style={{ margin: 0 }}>{card.title}</h3>
            <p className="muted">
              <strong>Why it matters:</strong> {card.why}
            </p>
            <div className="ro-nav-row">
              <ReadOnlyNavChip label={card.actionLabel} to={card.to} />
              <Link className="ro-nav-chip ghost" to={card.to}>
                Open
              </Link>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
