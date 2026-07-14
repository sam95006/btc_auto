import type { DocSummary } from "../demo/docSummaries";
import { artifactHref } from "../demo/reportIndex";
import { DemoDataBadge } from "./DemoDataBadge";
import { StatusBadge, type StatusTone } from "./StatusBadge";
import { Link } from "react-router-dom";

function toneForGate(gate: DocSummary["gateStatus"]): StatusTone {
  switch (gate) {
    case "HOLD":
      return "hold";
    case "BLOCKED":
      return "blocked";
    case "PASS":
    case "READY":
      return "pass";
    case "PARTIAL":
    case "WAIT":
      return "wait";
    default:
      return "neutral";
  }
}

/** Single sanitized doc excerpt card (MVP-15). */
export function DocSummaryCard({ summary }: { summary: DocSummary }) {
  return (
    <article className="panel-card doc-summary-card" id={`doc-summary-${summary.id}`}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>
          <Link className="deep-link" to={artifactHref(summary.stage)}>
            {summary.stage}
          </Link>{" "}
          — {summary.title}
        </h3>
        <StatusBadge tone={toneForGate(summary.gateStatus)}>{summary.gateStatus}</StatusBadge>
        <span className="demo-badge">SANITIZED</span>
        <DemoDataBadge />
      </div>
      <p className="mono muted">{summary.verdict}</p>
      <div className="flag-grid" style={{ marginTop: "0.55rem" }}>
        <div className="flag-item">
          <div className="k">One-line summary</div>
          <div className="v">{summary.oneLineSummary}</div>
        </div>
        <div className="flag-item">
          <div className="k">Key conclusion</div>
          <div className="v">{summary.keyConclusion}</div>
        </div>
        <div className="flag-item">
          <div className="k">Next action</div>
          <div className="v">{summary.nextAction}</div>
        </div>
        <div className="flag-item">
          <div className="k">Gate status</div>
          <div className="v">{summary.gateStatus}</div>
        </div>
        <div className="flag-item">
          <div className="k">Safety note</div>
          <div className="v">{summary.safetyNote}</div>
        </div>
      </div>
      <p className="muted" style={{ marginTop: "0.55rem", marginBottom: 0 }}>
        READ ONLY · NOT INVESTMENT ADVICE · excerpt only · no raw report body · no control buttons
      </p>
    </article>
  );
}
