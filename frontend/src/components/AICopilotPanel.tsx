import { useState } from "react";
import { COPILOT_PROMPTS } from "../demo/marketIntelligence";

/**
 * AI Commander rail — static prompt cards only (MVP-17/20).
 * No live AI API · no orders · desktop: right rail only.
 */
export function AICopilotPanel({ compact = false }: { compact?: boolean }) {
  const [active, setActive] = useState(COPILOT_PROMPTS[0]?.id ?? "");
  const selected = COPILOT_PROMPTS.find((p) => p.id === active) ?? COPILOT_PROMPTS[0];

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
        Read-only prompts · no live AI · no Buy / Sell / Execute
      </p>
      <div className="copilot-prompt-grid">
        {COPILOT_PROMPTS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`copilot-prompt-btn${active === p.id ? " active" : ""}`}
            onClick={() => setActive(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>
      {selected ? (
        <div className="copilot-prompt-preview">
          <div className="k">Selected prompt</div>
          <p className="mono muted">{selected.prompt}</p>
          <p className="muted" style={{ marginBottom: 0 }}>
            Generate Brief = navigation metaphor · NOT INVESTMENT ADVICE
          </p>
        </div>
      ) : null}
    </section>
  );
}
