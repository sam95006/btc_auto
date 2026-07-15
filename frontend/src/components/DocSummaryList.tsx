import { useMemo } from "react";
import type { DocSummary } from "../demo/docSummaries";
import { filterDocSummaries } from "../demo/docSummaries";
import { useEvidenceFilterQueryState } from "../hooks/useEvidenceFilterQueryState";
import { DemoDataBadge } from "./DemoDataBadge";
import { DocSummaryCard } from "./DocSummaryCard";
import { DocSummaryFilterBar } from "./DocSummaryFilterBar";
import { EvidencePresetBar } from "./EvidencePresetBar";

/** Drilldown + preset aliases → summary ids (MVP-18/19). */
const ANCHOR_ALIASES: Record<string, string[]> = {
  "p2d-r1": ["p2-r1-btc"],
  p2d: ["p2d-prompt-repair"],
  p2f: ["p2f-watch-gate", "eth-watch-reappearance"],
  "p2h-rel": ["p2h-rel"],
};

/** Filtered list of sanitized doc excerpts + share presets (MVP-15…19). */
export function DocSummaryList({
  summaries,
  title = "Static Doc Summary Viewer",
  enableFilter = false,
}: {
  summaries: DocSummary[];
  title?: string;
  enableFilter?: boolean;
}) {
  const [filter, setFilter] = useEvidenceFilterQueryState();
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
        Sanitized excerpts · share presets · URL filter (q/category/gateStatus/unresolved/tag) · no
        /data · no backend · no control actions · NOT INVESTMENT ADVICE
      </p>
      {enableFilter ? (
        <>
          <EvidencePresetBar />
          <DocSummaryFilterBar value={filter} onChange={setFilter} resultCount={visible.length} />
        </>
      ) : null}
      <div className="doc-summary-stack">
        {visible.length === 0 ? (
          <p className="muted">No sanitized excerpts match these local filters.</p>
        ) : (
          visible.map((s) => (
            <div key={s.id}>
              {(ANCHOR_ALIASES[s.id] ?? []).map((alias) => (
                <span key={alias} id={alias} className="anchor-alias" />
              ))}
              <DocSummaryCard summary={s} />
            </div>
          ))
        )}
      </div>
    </section>
  );
}
