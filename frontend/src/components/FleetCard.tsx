import type { FleetStatus } from "../types/nexus";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { SignalStatusBadge } from "./SignalStatusBadge";
import { StatusBadge } from "./StatusBadge";

function mapWatchToGate(watch: FleetStatus["watchState"]): "HOLD" | "WAIT" | "PASS" {
  if (watch === "valid_watch") return "WAIT";
  if (watch === "observe") return "WAIT";
  return "HOLD";
}

function stanceLabel(fleet: FleetStatus): string {
  if (fleet.watchState === "valid_watch") return "Valid watch (observe only)";
  if (fleet.watchState === "soft_skip") return "Soft skip";
  if (fleet.watchState === "hard_skip") return "Hard skip";
  return "Observe only";
}

function nextFor(fleet: FleetStatus): "View Evidence" | "View Gate" | "Open Risk Card" {
  if (fleet.symbol === "ETH") return "View Gate";
  if (fleet.mae > 0.02) return "Open Risk Card";
  return "View Evidence";
}

/** Trading-summary style fleet card (MVP-20) — Fleets page. */
export function FleetCard({ fleet }: { fleet: FleetStatus }) {
  const gate = mapWatchToGate(fleet.watchState);
  const next = nextFor(fleet);
  return (
    <article className="fleet-intel-card panel-card dense-card">
      <div className="fleet-card-head">
        <h3 className="fleet-symbol">{fleet.symbol}</h3>
        <StatusBadge tone={gate === "WAIT" ? "wait" : "hold"}>{gate}</StatusBadge>
      </div>
      <dl className="fleet-summary">
        <div>
          <dt>AI stance</dt>
          <dd>{stanceLabel(fleet)}</dd>
        </div>
        <div>
          <dt>Latest intent</dt>
          <dd>{fleet.intent || "None"}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd className="mono">{(fleet.confidence * 100).toFixed(0)}%</dd>
        </div>
        <div>
          <dt>Graduation</dt>
          <dd>{fleet.graduationStatus}</dd>
        </div>
        <div>
          <dt>Watch</dt>
          <dd>
            <SignalStatusBadge status={fleet.watchState} />
          </dd>
        </div>
        <div className="fleet-next">
          <dt>Next</dt>
          <dd>
            <ReadOnlyNavChip label={next} />
          </dd>
        </div>
      </dl>
    </article>
  );
}
