import { useState } from "react";
import { FLOATING_AI_PROMPTS } from "../demo/marketDashboard";

/**
 * Bottom-right floating AI — small panel, static prompts only (MVP-22).
 * No live AI API · no orders.
 */
export function FloatingAIAssistant() {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<(typeof FLOATING_AI_PROMPTS)[number]["id"]>(
    FLOATING_AI_PROMPTS[0].id,
  );
  const selected = FLOATING_AI_PROMPTS.find((p) => p.id === active) ?? FLOATING_AI_PROMPTS[0];

  return (
    <div className="floating-ai" aria-label="AI Assistant">
      {open ? (
        <div className="floating-ai-panel panel-card" role="dialog" aria-label="AI prompts">
          <div className="floating-ai-head">
            <strong>AI Assistant</strong>
            <button type="button" className="ro-nav-chip ghost" onClick={() => setOpen(false)}>
              Close
            </button>
          </div>
          <p className="muted" style={{ margin: "0.25rem 0 0.5rem" }}>
            Static prompts · 研究說明 · 非投資建議
          </p>
          <div className="copilot-prompt-grid">
            {FLOATING_AI_PROMPTS.map((p) => (
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
          {selected ? <p className="mono muted floating-ai-answer">{selected.answer}</p> : null}
        </div>
      ) : null}
      <button
        type="button"
        className="floating-ai-fab"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        title="AI Assistant"
      >
        AI
      </button>
    </div>
  );
}
