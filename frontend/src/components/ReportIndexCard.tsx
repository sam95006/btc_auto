import type { ReportIndexItem } from "../types/nexusSnapshot";
import { DemoDataBadge } from "./DemoDataBadge";

const EXPECTED_STAGES = [
  "4.18-P2D",
  "4.18-P2D-R1",
  "4.18-P2E",
  "4.18-P2F",
  "4.18-P2G",
  "4.18-P2H",
];

export function ReportIndexCard({ items }: { items: ReportIndexItem[] }) {
  const present = new Set(items.map((i) => i.stage));
  return (
    <section className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Private Operator Report Index</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">READ ONLY</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · research report index only · No
        live trading · Required chain: P2D → P2D-R1 → P2E → P2F → P2G → P2H
      </p>

      <div className="report-stage-chips" aria-label="Report stages P2D through P2H">
        {EXPECTED_STAGES.map((stage) => (
          <span
            key={stage}
            className={
              present.has(stage) ? "report-stage-chip present" : "report-stage-chip missing"
            }
          >
            {stage.replace("4.18-", "")}
          </span>
        ))}
      </div>

      <ul className="report-list" style={{ marginTop: "0.75rem" }}>
        {items.map((item) => (
          <li key={item.stage}>
            <strong>
              {item.stage} — {item.verdict}
            </strong>
            <div className="muted">{item.oneLineConclusion}</div>
            <div className="mono muted">{item.reportPath}</div>
            <div className="muted">Next action: {item.nextAction}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}
