import { useState } from "react";
import { getRoundTable } from "../data/nexusDataAdapter";
import { DemoDataBadge } from "./DemoDataBadge";

const TABS = [
  "Ask current page",
  "Find risk",
  "Find opportunity",
  "Daily brief",
  "Explain decision",
  "Ask reflection",
  "Ask evidence",
  "Why can’t we trade now?",
] as const;

export function AICommanderPanel() {
  const [tab, setTab] = useState<(typeof TABS)[number]>(TABS[0]);
  const rt = getRoundTable();

  const body = (() => {
    switch (tab) {
      case "Find risk":
        return "Elevated MAE on SOL/PEPE; PEPE blocked_by_risk. Defensive ON.";
      case "Find opportunity":
        return "BTC valid_watch only — observation priority, not an action cue.";
      case "Daily brief":
        return `${rt.consensus} ${rt.whyNotTradeNow}`;
      case "Explain decision":
        return "Decisions are observe / watch / skip / blocked language only.";
      case "Ask reflection":
        return "Reflection AI: confidence haircut on meme names (demo).";
      case "Ask evidence":
        return "Open Evidence Vault for decision rows with stage markers.";
      case "Why can’t we trade now?":
        return rt.whyNotTradeNow;
      default:
        return "Research assistant stub. Answers use DEMO DATA only.";
    }
  })();

  return (
    <aside className="ai-rail" aria-label="AI Assistant">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2>AI Commander</h2>
        <DemoDataBadge />
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
        DEMO DATA - READ ONLY - NOT INVESTMENT ADVICE
      </p>
    </aside>
  );
}
