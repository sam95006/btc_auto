import { EvidenceItemCard } from "../components/EvidenceItemCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { getEvidence } from "../data/nexusDataAdapter";

export function EvidencePage() {
  const items = getEvidence();

  return (
    <div>
      <header className="page-header">
        <h1>Evidence Vault</h1>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">Recent AI decisions with stage markers (demo).</p>
      </header>
      <div className="list-stack">
        {items.map((item) => (
          <EvidenceItemCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
