import { useState } from "react";
import { Link } from "react-router-dom";
import { GUIDED_PROMPTS } from "../demo/productUx";

/** Full-page guided assistant — Chinese labels OK (MVP-21). */
export function AICommanderPanel() {
  const [tab, setTab] = useState(GUIDED_PROMPTS[0]?.id ?? "");
  const selected = GUIDED_PROMPTS.find((p) => p.id === tab) ?? GUIDED_PROMPTS[0];

  return (
    <aside className="ai-rail page-ai" aria-label="AI Assistant">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2>AI Commander</h2>
        <span className="demo-badge priority-med">STATIC</span>
      </div>
      <div className="ai-tabs">
        {GUIDED_PROMPTS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={tab === t.id ? "active" : undefined}
            onClick={() => setTab(t.id)}
          >
            {t.labelZh}
          </button>
        ))}
      </div>
      {selected ? (
        <div className="ai-body">
          <p>
            <strong>{selected.question}</strong>
          </p>
          <p className="muted">{selected.willExplain}</p>
          <p>
            Related:{" "}
            <Link className="deep-link" to={selected.relatedTo}>
              {selected.relatedPage}
            </Link>
          </p>
          <p>{selected.answer}</p>
        </div>
      ) : null}
      <p className="muted" style={{ fontSize: "0.7rem" }}>
        DEMO DATA · READ ONLY · NOT INVESTMENT ADVICE
      </p>
    </aside>
  );
}
