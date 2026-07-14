import type { GateStatusLabel } from "../demo/docSummaries";
import { DemoDataBadge } from "./DemoDataBadge";
import { StatusBadge, type StatusTone } from "./StatusBadge";

function toneForGate(gate: GateStatusLabel): StatusTone {
  switch (gate) {
    case "HOLD":
      return "hold";
    case "BLOCKED":
      return "blocked";
    case "PASS":
    case "READY":
      return "pass";
    case "WAIT":
    case "PARTIAL":
      return "wait";
    default:
      return "neutral";
  }
}

/** Compact page-level sanitized bullet summary (Paper / Risk / Provider). */
export function PageSummaryCard({
  title,
  bullets,
  nextAction,
  gateStatus,
  safetyNote,
}: {
  title: string;
  bullets: string[];
  nextAction: string;
  gateStatus: GateStatusLabel;
  safetyNote: string;
}) {
  return (
    <section className="panel-card" style={{ marginTop: "1rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>{title}</h3>
        <StatusBadge tone={toneForGate(gateStatus)}>{gateStatus}</StatusBadge>
        <span className="demo-badge">SANITIZED</span>
        <DemoDataBadge />
      </div>
      <ul className="summary-bullet-list">
        {bullets.map((b) => (
          <li key={b}>{b}</li>
        ))}
      </ul>
      <p className="muted" style={{ marginBottom: 0 }}>
        Next: {nextAction} · {safetyNote} · READ ONLY · NOT INVESTMENT ADVICE
      </p>
    </section>
  );
}
