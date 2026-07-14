import { Link } from "react-router-dom";
import {
  artifactHref,
  stageAnchorId,
  type PrivateReportMeta,
} from "../demo/reportIndex";
import { DemoDataBadge } from "./DemoDataBadge";
import { RelatedArtifactLinks } from "./RelatedArtifactLinks";

/** Read-only runbook viewer with related checkpoint deep links (MVP-14). */
export function OperatorRunbookCard({
  runbooks,
}: {
  runbooks: PrivateReportMeta[];
}) {
  const items = runbooks.filter((r) => r.kind === "runbook");
  return (
    <section id="runbooks" className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Operator Runbook Viewer</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">HOLD</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · deep links are documentation-only ·
        no auto-run
      </p>
      <ul className="report-list" style={{ marginTop: "0.75rem" }}>
        {items.map((item) => (
          <li key={item.stage} id={stageAnchorId(item.stage)}>
            <strong>
              <Link className="deep-link" to={artifactHref(item.stage)}>
                {item.stage}
              </Link>{" "}
              — {item.title}
            </strong>
            <div className="mono muted">{item.verdict}</div>
            <div className="muted">{item.oneLineConclusion}</div>
            <div className="mono muted">{item.filePath}</div>
            <div className="muted">Next: {item.nextAction}</div>
            <p className="muted" style={{ marginBottom: 0 }}>
              Related checkpoint:{" "}
              <Link className="deep-link" to={artifactHref(item.relatedCheckpoint)}>
                {item.relatedCheckpoint}
              </Link>
            </p>
            <RelatedArtifactLinks artifact={item} />
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
