import { FleetCard } from "../components/FleetCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { getFleetStatus } from "../demo/nexusDataAdapter";

export function FleetsPage() {
  const fleets = getFleetStatus();

  return (
    <div>
      <header className="page-header">
        <h1>AI Fleet Center</h1>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Standard" currentTier="Free" />
        <p className="page-sub">
          Per-fleet intent, watch state, MAE, invalidation. UI lock stub only.
        </p>
      </header>
      <div className="card-grid">
        {fleets.map((f) => (
          <FleetCard key={f.fleetId} fleet={f} />
        ))}
      </div>
    </div>
  );
}
