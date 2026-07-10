import { ProviderComparisonCard } from "../components/ProviderComparisonCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { getProviderShadowSummary } from "../data/nexusDataAdapter";

export function ProviderShadowPage() {
  const summary = getProviderShadowSummary();

  return (
    <div>
      <header className="page-header">
        <h1>Provider Shadow Center</h1>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Elite" currentTier="Free" />
        <p className="page-sub">
          Shadow excluded from paper / calibration / graduation. No routing edit.
        </p>
      </header>
      <ProviderComparisonCard summary={summary} />
    </div>
  );
}
