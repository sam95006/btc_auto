import type { ChecklistRefId } from "../demo/docSummaries";
import { getChecklistRefs } from "../demo/docSummaries";
import { Link } from "react-router-dom";

/** Documentation-only links from summary cards to gate / runbook checklists (MVP-16). */
export function ChecklistReferenceLinks({
  refs,
  label = "Related checklist",
}: {
  refs: ChecklistRefId[];
  label?: string;
}) {
  const items = getChecklistRefs(refs);
  if (items.length === 0) return null;

  return (
    <div className="checklist-ref-links" style={{ marginTop: "0.65rem" }}>
      <div className="k" style={{ marginBottom: "0.35rem" }}>
        {label}
      </div>
      <div className="report-stage-chips">
        {items.map((r) => (
          <Link key={r.id} className="report-stage-chip present deep-link" to={r.href} title={r.description}>
            {r.label}
          </Link>
        ))}
      </div>
      <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.75rem" }}>
        Checklist links are documentation anchors only · no Start Stage 4.19 · no Run 30m / 60m
      </p>
    </div>
  );
}
