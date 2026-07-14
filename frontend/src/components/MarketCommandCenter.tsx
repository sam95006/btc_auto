import {
  FLEET_INTELLIGENCE,
  SYSTEM_GATE_STRIP,
  type FleetIntel,
} from "../demo/marketIntelligence";
import { DemoDataBadge } from "./DemoDataBadge";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";
import { AICopilotPanel } from "./AICopilotPanel";

function FleetIntelCard({ fleet }: { fleet: FleetIntel }) {
  return (
    <article className="fleet-intel-card panel-card dense-card">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>{fleet.symbol}</h3>
        <StatusBadge tone={fleet.riskGate === "WAIT" ? "wait" : "hold"}>{fleet.riskGate}</StatusBadge>
      </div>
      <div className="dense-kv">
        <div>
          <span className="k">AI stance</span>
          <span className="v">{fleet.stance}</span>
        </div>
        <div>
          <span className="k">Intent</span>
          <span className="v mono">{fleet.latestIntent}</span>
        </div>
        <div>
          <span className="k">valid_watch</span>
          <span className="v mono">{fleet.validWatchCount}</span>
        </div>
        <div>
          <span className="k">Graduation</span>
          <span className="v">{fleet.graduationStatus}</span>
        </div>
        <div>
          <span className="k">Confidence</span>
          <span className="v mono">{fleet.confidence}</span>
        </div>
        <div>
          <span className="k">Next</span>
          <span className="v">{fleet.nextAction}</span>
        </div>
      </div>
    </article>
  );
}

/** Market Command Center — DataHunterX-inspired denser financial layout (MVP-17). */
export function MarketCommandCenter() {
  const g = SYSTEM_GATE_STRIP;
  return (
    <section id="market-command" className="mcc-root" aria-label="Market Command Center">
      <div className="meta-row" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
        <h2 className="section-title" style={{ margin: 0 }}>
          Market Command Center
        </h2>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <StatusBadge tone="blocked">Stage 4.19 BLOCKED</StatusBadge>
        <span className="demo-badge">READ ONLY</span>
        <DemoDataBadge />
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Market Intelligence layout · NOT INVESTMENT ADVICE · no trading controls · sanitized static
        data
      </p>

      <div className="mcc-grid">
        <div className="mcc-left">
          <section className="panel-card dense-card system-gate-strip" id="system-gate-strip">
            <h3 style={{ margin: 0, fontSize: "0.9rem" }}>System Gate Strip</h3>
            <div className="gate-strip-row">
              <span>
                Backend State: <strong className="tone-hold">{g.backendState}</strong>
              </span>
              <span>
                Release: <strong>{g.releaseCheckpoint}</strong>
              </span>
              <span>
                Stage 4.19: <strong className="tone-blocked">{g.stage419}</strong>
              </span>
              <span>
                Next: <strong>{g.nextAction}</strong>
              </span>
              <span className="mono">30m now: {String(g.thirtyMNow)}</span>
              <span className="mono">60m: {String(g.sixtyM)}</span>
              <span className="mono">Auto-run: {String(g.autoRun)}</span>
            </div>
          </section>

          <div className="fleet-intel-grid" aria-label="Fleet Intelligence Grid">
            {FLEET_INTELLIGENCE.map((f) => (
              <FleetIntelCard key={f.symbol} fleet={f} />
            ))}
          </div>

          <div className="mcc-quick-nav">
            <ReadOnlyNavChip label="View Evidence" />
            <ReadOnlyNavChip label="Open Risk Card" />
            <ReadOnlyNavChip label="View Gate" />
            <ReadOnlyNavChip label="View Runbook" />
            <ReadOnlyNavChip label="Ask AI" />
          </div>
        </div>

        <aside className="mcc-right">
          <AICopilotPanel compact />
        </aside>
      </div>
    </section>
  );
}
