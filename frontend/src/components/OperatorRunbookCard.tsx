import type { PrivateReportMeta } from "../demo/reportIndex";
import { DemoDataBadge } from "./DemoDataBadge";

/** Read-only runbook viewer for Private Operator HOLD ops. */
export function OperatorRunbookCard({
  runbooks,
}: {
  runbooks: PrivateReportMeta[];
}) {
  const items = runbooks.filter((r) => r.kind === "runbook");
  return (
    <section className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Operator Runbook Viewer</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">HOLD</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · how to lift HOLD · future gate
        checker usage · short-regression + Stage 4.19 checklists · no auto-run
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
        Conditions must reappear before operator may approve short regression. Never auto-start
        Stage 4.19.
      </p>
    </section>
  );
}
