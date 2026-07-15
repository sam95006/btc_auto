import { Link } from "react-router-dom";
import { GUIDED_PROMPTS } from "../demo/productUx";

/**
 * Compact main-area guided prompt chips (MVP-21).
 * Full AI Commander stays in the right rail.
 */
export function AIPromptChipStrip() {
  const primary = GUIDED_PROMPTS.slice(0, 5);
  return (
    <section
      id="ai-copilot"
      className="ai-prompt-chip-strip"
      aria-label="AI Commander quick prompts"
    >
      <div className="ai-chip-strip-head">
        <span className="ai-chip-strip-label">Ask AI</span>
        <span className="muted">Guided static prompts · see right rail</span>
        <Link className="ro-nav-chip ghost" to="/assistant">
          Open assistant
        </Link>
      </div>
      <div className="copilot-prompt-grid">
        {primary.map((p) => (
          <span key={p.id} className="copilot-prompt-btn static-chip" title={p.question}>
            {p.labelZh}
          </span>
        ))}
      </div>
    </section>
  );
}
