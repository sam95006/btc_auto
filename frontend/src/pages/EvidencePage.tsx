import { DemoDataBadge } from "../components/DemoDataBadge";
import { EvidenceItemCard } from "../components/EvidenceItemCard";
import { EvidenceZoneTabs } from "../components/EvidenceZoneTabs";
import { OperatorBreadcrumbs } from "../components/OperatorBreadcrumbs";
import { ReleaseHealthBadge } from "../components/CheckpointHealthCard";
import { StatusBadge } from "../components/StatusBadge";
import { useHashScroll } from "../hooks/useHashScroll";
import { getEvidence } from "../demo/nexusDataAdapter";

export function EvidencePage() {
  useHashScroll();
  const items = getEvidence();

  return (
    <div className="page-stack">
      <OperatorBreadcrumbs
        crumbs={[
          { label: "Operator Console", to: "/overview" },
          { label: "Evidence" },
        ]}
      />
      <header className="page-header">
        <h1>Evidence Center</h1>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <ReleaseHealthBadge />
        <DemoDataBadge />
        <p className="page-sub">
          Traceable reports and gates · Start Here first · READ ONLY · NOT INVESTMENT ADVICE · no
          trading controls
        </p>
      </header>

      <EvidenceZoneTabs />

      <div className="operator-section desk-secondary">
        <h2 className="section-title">Recent decision evidence</h2>
        <div className="list-stack">
          {items.map((item) => (
            <EvidenceItemCard key={item.id} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}
