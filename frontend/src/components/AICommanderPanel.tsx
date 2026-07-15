import { useState } from "react";
import { getRoundTable } from "../demo/nexusDataAdapter";

/** Full-page assistant tabs — Chinese prompt labels allowed (MVP-20 language strategy). */
const TABS = [
  "問目前頁",
  "找風險",
  "找機會",
  "今日簡報",
  "Explain decision",
  "Ask evidence",
  "Why HOLD now?",
] as const;

export function AICommanderPanel() {
  const [tab, setTab] = useState<(typeof TABS)[number]>(TABS[0]);
  const rt = getRoundTable();

  const body = (() => {
    switch (tab) {
      case "找風險":
        return "Elevated MAE on SOL/PEPE; PEPE blocked_by_risk. Defensive ON.";
      case "找機會":
        return "BTC prior evidence only — observation priority, not an action cue.";
      case "今日簡報":
        return `${rt.consensus} ${rt.whyNotTradeNow}`;
      case "Explain decision":
        return "Decisions use observe / watch / skip / blocked language only.";
      case "Ask evidence":
        return "Open Evidence for decision rows with stage markers.";
      case "Why HOLD now?":
        return rt.whyNotTradeNow;
      default:
        return "Research assistant stub. Answers use DEMO DATA only. READ ONLY.";
    }
  })();

  return (
    <aside className="ai-rail page-ai" aria-label="AI Assistant">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2>AI Commander</h2>
        <span className="demo-badge priority-med">STATIC</span>
      </div>
      <div className="ai-tabs">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            className={tab === t ? "active" : undefined}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="ai-body">{body}</div>
      <p className="muted" style={{ fontSize: "0.7rem" }}>
        DEMO DATA · READ ONLY · NOT INVESTMENT ADVICE
      </p>
    </aside>
  );
}
