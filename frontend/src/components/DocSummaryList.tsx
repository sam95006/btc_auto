import type { DocSummary } from "../demo/docSummaries";
import { DemoDataBadge } from "./DemoDataBadge";
import { DocSummaryCard } from "./DocSummaryCard";

/** List of sanitized doc excerpts for Evidence Center (MVP-15). */
export function DocSummaryList({
  summaries,
  title = "Static Doc Summary Viewer",
}: {
  summaries: DocSummary[];
  title?: string;
}) {
  return (
    <section id="doc-summaries" className="operator-section">
      <div className="meta-row" style={{ marginTop: 0, marginBottom: "0.65rem" }}>
        <h2 className="section-title" style={{ margin: 0 }}>
          {title}
        </h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">READ ONLY</span>
        <DemoDataBadge />
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Sanitized one-line excerpts · key conclusion · next action · gate status · no /data raw
        files · no control actions · NOT INVESTMENT ADVICE
      </p>
      <div className="doc-summary-stack">
        {summaries.map((s) => (
          <DocSummaryCard key={s.id} summary={s} />
        ))}
      </div>
    </section>
  );
}
