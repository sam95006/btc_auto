import { useMemo, useState } from "react";
import type { DocSummary } from "../demo/docSummaries";
import { getOperatorDocSummaries } from "../demo/docSummaries";
import { EVIDENCE_ZONES, type EvidenceZoneId } from "../demo/productUx";
import { PRIVATE_OPERATOR_RUNBOOKS } from "../demo/reportIndex";
import { CheckpointHealthCard } from "./CheckpointHealthCard";
import { DocSummaryList } from "./DocSummaryList";
import { OperatorRunbookCard } from "./OperatorRunbookCard";
import { OperatorWorkspacePins } from "./OperatorWorkspacePins";
import { UnresolvedGateCard } from "./UnresolvedGateCard";

function filterByZone(docs: DocSummary[], id: EvidenceZoneId): DocSummary[] {
  if (id === "start-here") {
    return docs.filter((d) => d.unresolvedGate || /p2f|p2h|hold|gate/i.test(`${d.stage} ${d.title}`)).slice(0, 8);
  }
  if (id === "gate-reports") {
    return docs.filter((d) => /p2f|p2g|4\.18-p2h(?!-)/i.test(`${d.stage} ${d.id}`));
  }
  if (id === "evidence-regression") {
    return docs.filter((d) =>
      /p2d|p2e|regression|r1|prompt/i.test(`${d.stage} ${d.id} ${d.category}`),
    );
  }
  return docs.filter((d) =>
    /p2h-qa|p2h-rel|p2h-ops|release|checkpoint|runbook/i.test(
      `${d.stage} ${d.id} ${d.category} ${d.title}`,
    ),
  );
}

/** Evidence Center four clear zones — MVP-16 search/filter retained (MVP-21). */
export function EvidenceZoneTabs() {
  const [zone, setZone] = useState<EvidenceZoneId>("start-here");
  const all = getOperatorDocSummaries();
  const zoneDocs = useMemo(() => filterByZone(all, zone), [all, zone]);

  return (
    <section id="evidence-zones" className="operator-section">
      <div className="section-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          Evidence zones
        </h2>
      </div>
      <p className="muted section-lede">
        Four clear entries · search/filter retained · READ ONLY · NOT INVESTMENT ADVICE
      </p>
      <div className="evidence-zone-tabs" role="tablist" aria-label="Evidence zones">
        {EVIDENCE_ZONES.map((z) => (
          <button
            key={z.id}
            type="button"
            role="tab"
            id={z.id === "start-here" ? "start-here" : undefined}
            aria-selected={zone === z.id}
            className={`evidence-zone-tab${zone === z.id ? " active" : ""}`}
            onClick={() => setZone(z.id)}
          >
            {z.label}
          </button>
        ))}
      </div>
      <p className="muted">{EVIDENCE_ZONES.find((z) => z.id === zone)?.blurb}</p>

      {zone === "start-here" ? (
        <div className="evidence-start-here">
          <UnresolvedGateCard />
          <OperatorWorkspacePins />
        </div>
      ) : null}

      {zone === "release-runbook" ? (
        <div>
          <CheckpointHealthCard />
          <OperatorRunbookCard runbooks={PRIVATE_OPERATOR_RUNBOOKS} />
        </div>
      ) : null}

      <DocSummaryList
        summaries={zone === "start-here" ? all : zoneDocs}
        title={
          zone === "start-here"
            ? "Recommended + searchable summaries"
            : `${EVIDENCE_ZONES.find((z) => z.id === zone)?.label ?? "Zone"} summaries`
        }
        enableFilter={zone === "start-here"}
      />
    </section>
  );
}
