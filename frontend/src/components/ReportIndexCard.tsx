import type { ReportIndexItem } from "../types/nexusSnapshot";
import { DemoDataBadge } from "./DemoDataBadge";

export function ReportIndexCard({ items }: { items: ReportIndexItem[] }) {
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
        live trading
      </p>

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
