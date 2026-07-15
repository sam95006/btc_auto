import { DECISION_CARDS, HOLD_HEADLINE } from "../demo/productUx";
import { StatusBadge } from "./StatusBadge";

/** 3-second Overview headline + four decision cards (MVP-21). */
export function HoldDecisionStrip() {
  return (
    <section id="hold-summary" className="hold-decision-strip" aria-label="HOLD summary">
      <header className="hold-headline-block">
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <StatusBadge tone="blocked">Stage 4.19 BLOCKED</StatusBadge>
        <h1 className="hold-headline">{HOLD_HEADLINE}</h1>
        <p className="muted section-lede">
          READ ONLY · NOT INVESTMENT ADVICE · Wait is the only next action · no trading controls
        </p>
      </header>
      <div className="decision-card-grid">
        {DECISION_CARDS.map((c) => (
          <article key={c.id} className={`panel-card dense-card decision-card tone-${c.tone}`}>
            <div className="k">{c.title}</div>
            <div className="decision-value">{c.value}</div>
            <p className="muted" style={{ marginBottom: 0 }}>
              {c.detail}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
