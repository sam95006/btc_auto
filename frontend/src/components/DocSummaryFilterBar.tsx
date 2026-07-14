import type { DocCategory, DocSummaryFilterState, GateStatusLabel } from "../demo/docSummaries";
import { DOC_CATEGORIES, EMPTY_DOC_SUMMARY_FILTER, GATE_STATUS_OPTIONS } from "../demo/docSummaries";
import { DemoDataBadge } from "./DemoDataBadge";

/** Static sanitized-metadata search / filter (MVP-16) — no backend, no /data. */
export function DocSummaryFilterBar({
  value,
  onChange,
  resultCount,
}: {
  value: DocSummaryFilterState;
  onChange: (next: DocSummaryFilterState) => void;
  resultCount: number;
}) {
  const set = (patch: Partial<DocSummaryFilterState>) => onChange({ ...value, ...patch });

  return (
    <section className="panel-card doc-filter-bar" aria-label="Static doc summary filters">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0, fontSize: "1rem" }}>Static Excerpt Search / Filter</h3>
        <span className="demo-badge">LOCAL METADATA</span>
        <span className="demo-badge">READ ONLY</span>
        <DemoDataBadge />
      </div>
      <p className="muted" style={{ marginTop: "0.35rem" }}>
        Sanitized metadata only · no backend calls · no /data · no control actions · NOT INVESTMENT
        ADVICE
      </p>
      <div className="doc-filter-grid">
        <label className="doc-filter-field">
          <span className="k">Search</span>
          <input
            type="search"
            value={value.query}
            placeholder="P2D · P2E · HOLD · Stage 4.19 · no 60m · ETH watch · prompt repair · release checkpoint"
            onChange={(e) => set({ query: e.target.value })}
            aria-label="Search sanitized doc summaries"
          />
        </label>
        <label className="doc-filter-field">
          <span className="k">Category</span>
          <select
            value={value.category}
            onChange={(e) => set({ category: e.target.value as DocCategory | "" })}
            aria-label="Filter by category"
          >
            <option value="">All categories</option>
            {DOC_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="doc-filter-field">
          <span className="k">Gate status</span>
          <select
            value={value.gateStatus}
            onChange={(e) => set({ gateStatus: e.target.value as GateStatusLabel | "" })}
            aria-label="Filter by gate status"
          >
            <option value="">All gate statuses</option>
            {GATE_STATUS_OPTIONS.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </label>
        <label className="doc-filter-check">
          <input
            type="checkbox"
            checked={value.unresolvedOnly}
            onChange={(e) => set({ unresolvedOnly: e.target.checked })}
          />
          <span>Show unresolved only</span>
        </label>
        <button
          type="button"
          className="doc-filter-clear"
          onClick={() => onChange({ ...EMPTY_DOC_SUMMARY_FILTER })}
        >
          Clear filters
        </button>
      </div>
      <p className="mono muted" style={{ marginBottom: 0 }}>
        Showing {resultCount} sanitized excerpt(s)
      </p>
    </section>
  );
}
