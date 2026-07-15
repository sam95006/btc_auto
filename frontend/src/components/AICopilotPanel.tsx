import { useState } from "react";
import { Link } from "react-router-dom";
import { GUIDED_PROMPTS } from "../demo/productUx";

/**
 * Guided AI Commander — static prompts only (MVP-21).
 * No live AI API · no orders · desktop right rail.
 */
export function AICopilotPanel({ compact = false }: { compact?: boolean }) {
  const [active, setActive] = useState(GUIDED_PROMPTS[0]?.id ?? "");
  const selected = GUIDED_PROMPTS.find((p) => p.id === active) ?? GUIDED_PROMPTS[0];

  return (
    <section
      className={`panel-card dense-card ai-copilot-panel${compact ? " compact" : ""}`}
      aria-label="AI Commander"
    >
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0, fontSize: "0.9rem" }}>AI Commander</h3>
        <span className="demo-badge priority-med">STATIC</span>
      </div>
      <p className="muted" style={{ marginTop: "0.35rem", marginBottom: 0 }}>
        Guided questions · no live AI · no Buy / Sell / Execute
      </p>
      <div className="copilot-prompt-grid">
        {GUIDED_PROMPTS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`copilot-prompt-btn${active === p.id ? " active" : ""}`}
            onClick={() => setActive(p.id)}
          >
            {p.labelZh}
          </button>
        ))}
      </div>
      {selected ? (
        <div className="copilot-prompt-preview guided-preview">
          <div className="k">Question</div>
          <p style={{ margin: "0.25rem 0" }}>
            <strong>{selected.question}</strong>
          </p>
          <div className="k">What it will explain</div>
          <p className="muted">{selected.willExplain}</p>
          <div className="k">Related page</div>
          <p className="muted">
            <Link className="deep-link" to={selected.relatedTo}>
              {selected.relatedPage}
            </Link>
          </p>
          <div className="k">Static answer</div>
          <p className="mono muted" style={{ marginBottom: 0 }}>
            {selected.answer}
          </p>
          <p className="muted" style={{ marginBottom: 0, marginTop: "0.45rem" }}>
            Generate Brief = navigation metaphor · NOT INVESTMENT ADVICE
          </p>
        </div>
      ) : null}
    </section>
  );
}
