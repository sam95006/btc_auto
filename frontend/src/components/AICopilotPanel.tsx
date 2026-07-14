import { useState } from "react";
import { COPILOT_PROMPTS } from "../demo/marketIntelligence";
import { DemoDataBadge } from "./DemoDataBadge";

/**
 * Static AI prompt cards only — no live AI API, no orders (MVP-17).
 */
export function AICopilotPanel({ compact = false }: { compact?: boolean }) {
  const [active, setActive] = useState(COPILOT_PROMPTS[0]?.id ?? "");
  const selected = COPILOT_PROMPTS.find((p) => p.id === active) ?? COPILOT_PROMPTS[0];

  return (
    <section
      id="ai-copilot"
      className={`panel-card dense-card ai-copilot-panel${compact ? " compact" : ""}`}
      aria-label="AI Commander Mini Panel"
    >
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0, fontSize: "0.9rem" }}>AI Commander</h3>
        <span className="demo-badge">STATIC PROMPTS</span>
        <DemoDataBadge />
      </div>
      <p className="muted" style={{ marginTop: "0.35rem" }}>
        Read-only prompt cards · no live AI API · no Buy / Sell / Execute · NOT INVESTMENT ADVICE
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
          <div className="k">Selected static prompt</div>
          <p className="mono muted">{selected.prompt}</p>
          <p className="muted" style={{ marginBottom: 0 }}>
            Display only · Generate Brief is navigation metaphor · no order execution
          </p>
        </div>
      ) : null}
    </section>
  );
}
