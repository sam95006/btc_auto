import { ReflectionSummaryCard } from "../components/ReflectionSummaryCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { getReflectionSummary } from "../data/nexusDataAdapter";

export function ReflectionPage() {
  const summary = getReflectionSummary();

  return (
    <div>
      <header className="page-header">
        <h1>Reflection Center</h1>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">Mistakes, penalties, patch proposals — display only.</p>
      </header>
      <ReflectionSummaryCard summary={summary} />
    </div>
  );
}
