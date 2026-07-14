import { Link } from "react-router-dom";
import type { ReportIndexItem } from "../types/nexusSnapshot";
import {
  artifactHref,
  getOrderedChainStages,
  stageAnchorId,
} from "../demo/reportIndex";
import { DemoDataBadge } from "./DemoDataBadge";
import { ReleaseHealthBadge } from "./CheckpointHealthCard";

const EXPECTED_STAGES = [
  "4.18-P2D",
  "4.18-P2D-R1",
  "4.18-P2E",
  "4.18-P2F",
  "4.18-P2G",
  "4.18-P2H",
  "4.18-P2H-QA",
];

export function ReportIndexCard({
  items,
  showP2hQaHealthBadge = false,
}: {
  items: ReportIndexItem[];
  showP2hQaHealthBadge?: boolean;
}) {
  const present = new Set(items.map((i) => i.stage));
  const chain = getOrderedChainStages();
  return (
    <section id="report-index" className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Private Operator Report Index</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">READ ONLY</span>
        {showP2hQaHealthBadge ? <ReleaseHealthBadge /> : null}
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · research report index only · No
        live trading · Jump chain: P2D → P2H-REL
      </p>
      {showP2hQaHealthBadge ? (
        <p className="muted">
          P2H-QA health PASS · release checkpoint ready · Backend HOLD confirmed · no Stage 4.19
          start
        </p>
      ) : null}

      <div className="report-stage-chips" aria-label="Deep link chain P2D through P2H-REL">
        {chain.map((stage) => (
          <Link
            key={stage}
            className={
              present.has(stage) || stage.includes("OPS") || stage.includes("REL")
                ? "report-stage-chip present deep-link-chip"
                : "report-stage-chip missing"
            }
            to={artifactHref(stage)}
          >
            {stage.replace("4.18-", "")}
          </Link>
        ))}
      </div>

      <ul className="report-list" style={{ marginTop: "0.75rem" }}>
        {items.map((item) => (
          <li key={item.stage} id={stageAnchorId(item.stage)}>
            <strong>
              <Link className="deep-link" to={artifactHref(item.stage)}>
                {item.stage}
              </Link>{" "}
              — {item.verdict}
            </strong>
            <div className="muted">{item.oneLineConclusion}</div>
            <div className="mono muted">{item.reportPath}</div>
            <div className="muted">Next action: {item.nextAction}</div>
          </li>
        ))}
      </ul>

      {/* Keep EXPECTED_STAGES referenced for older snapshots without P2H-QA */}
      <p className="mono muted" style={{ marginTop: "0.5rem" }}>
        Snapshot stages present: {EXPECTED_STAGES.filter((s) => present.has(s)).join(" · ")}
      </p>
    </section>
  );
}
