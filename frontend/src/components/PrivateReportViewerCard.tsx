import type { PrivateReportMeta } from "../demo/reportIndex";
import { DemoDataBadge } from "./DemoDataBadge";

/** Read-only sanitized report index viewer (Private Operator). */
export function PrivateReportViewerCard({
  reports,
}: {
  reports: PrivateReportMeta[];
}) {
  const items = reports.filter((r) => r.kind === "report");
  return (
    <section className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Private Report Viewer</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">READ ONLY</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · metadata only · why HOLD · which
        report matters · no control buttons · no /data raw files
      </p>
      <ul className="report-list" style={{ marginTop: "0.75rem" }}>
        {items.map((item) => (
          <li key={item.stage}>
            <strong>
              {item.stage} — {item.title}
            </strong>
            <div className="mono muted">{item.verdict}</div>
            <div className="muted">{item.oneLineConclusion}</div>
            <div className="mono muted">{item.filePath}</div>
            <div className="muted">Next: {item.nextAction}</div>
          </li>
        ))}
      </ul>
      <p className="muted" style={{ marginTop: "0.75rem" }}>
        Backend HOLD · wait-for-condition · no auto-run · Stage 4.19 blocked
      </p>
    </section>
  );
}
