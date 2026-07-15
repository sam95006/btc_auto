import { FleetCard } from "../components/FleetCard";
import { StatusBadge } from "../components/StatusBadge";
import { getFleetStatus } from "../demo/nexusDataAdapter";

export function FleetsPage() {
  const fleets = getFleetStatus();

  return (
    <div className="page-stack">
      <header className="page-header">
        <h1>Fleets</h1>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <p className="page-sub">
          Per-symbol trading summary · READ ONLY · NOT INVESTMENT ADVICE
        </p>
      </header>
      <div className="fleet-intel-grid fleets-page-grid">
        {fleets.map((f) => (
          <FleetCard key={f.fleetId} fleet={f} />
        ))}
      </div>
    </div>
  );
}
