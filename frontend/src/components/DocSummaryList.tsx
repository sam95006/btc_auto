import { useMemo, useState } from "react";
import type { DocSummary } from "../demo/docSummaries";
import {
  EMPTY_DOC_SUMMARY_FILTER,
  filterDocSummaries,
  type DocSummaryFilterState,
} from "../demo/docSummaries";
import { DemoDataBadge } from "./DemoDataBadge";
import { DocSummaryCard } from "./DocSummaryCard";
import { DocSummaryFilterBar } from "./DocSummaryFilterBar";

/** Filtered list of sanitized doc excerpts for Evidence Center (MVP-15 / MVP-16). */
export function DocSummaryList({
  summaries,
  title = "Static Doc Summary Viewer",
  enableFilter = false,
}: {
  summaries: DocSummary[];
  title?: string;
  enableFilter?: boolean;
}) {
  const [filter, setFilter] = useState<DocSummaryFilterState>({ ...EMPTY_DOC_SUMMARY_FILTER });
  const visible = useMemo(
    () => (enableFilter ? filterDocSummaries(summaries, filter) : summaries),
    [summaries, filter, enableFilter],
  );

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
        Sanitized one-line excerpts · key conclusion · next action · gate status · checklist links ·
        no /data raw files · no control actions · NOT INVESTMENT ADVICE
      </p>
      {enableFilter ? (
        <DocSummaryFilterBar value={filter} onChange={setFilter} resultCount={visible.length} />
      ) : null}
      <div className="doc-summary-stack">
        {visible.length === 0 ? (
          <p className="muted">No sanitized excerpts match these local filters.</p>
        ) : (
          visible.map((s) => <DocSummaryCard key={s.id} summary={s} />)
        )}
      </div>
    </section>
  );
}
