import { Link } from "react-router-dom";
import { COPILOT_PROMPTS } from "../demo/marketIntelligence";

/**
 * Compact main-area AI summary chips (MVP-20).
 * Desktop AI Commander lives in the right rail only — this is not a second full panel.
 * Static prompts · no live AI API · no trading actions.
 */
export function AIPromptChipStrip() {
  const primary = COPILOT_PROMPTS.slice(0, 4);
  return (
    <section
      id="ai-copilot"
      className="ai-prompt-chip-strip"
      aria-label="AI Commander quick prompts"
    >
      <div className="ai-chip-strip-head">
        <span className="ai-chip-strip-label">Ask AI</span>
        <span className="muted">Static prompts · see right rail</span>
        <Link className="ro-nav-chip ghost" to="/assistant">
          Open assistant
        </Link>
      </div>
      <div className="copilot-prompt-grid">
        {primary.map((p) => (
          <span key={p.id} className="copilot-prompt-btn static-chip" title={p.prompt}>
            {p.label}
          </span>
        ))}
      </div>
    </section>
  );
}
