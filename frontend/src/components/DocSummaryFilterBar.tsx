import type { DocCategory, DocSummaryFilterState, GateStatusLabel } from "../demo/docSummaries";
import { DOC_CATEGORIES, EMPTY_DOC_SUMMARY_FILTER, GATE_STATUS_OPTIONS } from "../demo/docSummaries";
import { DemoDataBadge } from "./DemoDataBadge";

/** Static sanitized-metadata search / filter (MVP-16/18) — URL sync · no backend · no /data. */
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
        <span className="demo-badge">URL QUERY</span>
        <span className="demo-badge">LOCAL METADATA</span>
        <DemoDataBadge />
      </div>
      <p className="muted" style={{ marginTop: "0.35rem" }}>
        Filter state in URL (q · category · gateStatus · unresolved · tag) · share/reload keeps
        filters · no backend · no /data · no localStorage secrets · NOT INVESTMENT ADVICE
      </p>
      <div className="doc-filter-grid mi18-filter-grid">
        <label className="doc-filter-field">
          <span className="k">Search (q)</span>
          <input
            type="search"
            value={value.query}
            placeholder="P2D · ETH · HOLD · Stage 4.19 · no 60m · prompt repair"
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
        <label className="doc-filter-field">
          <span className="k">Tag</span>
          <input
            type="search"
            value={value.tag}
            placeholder="HOLD · ETH · BTC · Stage 4.19"
            onChange={(e) => set({ tag: e.target.value })}
            aria-label="Filter by tag"
          />
        </label>
        <label className="doc-filter-check">
          <input
            type="checkbox"
            checked={value.unresolvedOnly}
            onChange={(e) => set({ unresolvedOnly: e.target.checked })}
          />
          <span>Unresolved only</span>
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
        Showing {resultCount} sanitized excerpt(s) · example{" "}
        <code>/evidence?q=ETH&amp;category=backend-gate&amp;gateStatus=HOLD&amp;unresolved=true</code>
      </p>
    </section>
  );
}
