import { Link } from "react-router-dom";
import {
  FLEET_INTELLIGENCE,
  SYSTEM_GATE_STRIP,
  type FleetIntel,
} from "../demo/marketIntelligence";
import { AIPromptChipStrip } from "./AIPromptChipStrip";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

function FleetIntelCard({ fleet }: { fleet: FleetIntel }) {
  const confLabel =
    fleet.confidence > 0 ? `${Math.round(fleet.confidence * 100)}%` : "—";
  return (
    <article className="fleet-intel-card panel-card dense-card">
      <div className="fleet-card-head">
        <h3 className="fleet-symbol">{fleet.symbol}</h3>
        <StatusBadge tone={fleet.riskGate === "WAIT" ? "wait" : "hold"}>
          {fleet.riskGate}
        </StatusBadge>
      </div>
      <dl className="fleet-summary">
        <div>
          <dt>AI stance</dt>
          <dd>{fleet.stance}</dd>
        </div>
        <div>
          <dt>Latest intent</dt>
          <dd>{fleet.latestIntent}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd className="mono">{confLabel}</dd>
        </div>
        <div>
          <dt>Graduation</dt>
          <dd>{fleet.graduationStatus}</dd>
        </div>
        <div className="fleet-next">
          <dt>Next</dt>
          <dd>
            <ReadOnlyNavChip
              label={
                fleet.nextAction as
                  | "View Evidence"
                  | "View Gate"
                  | "Ask AI"
                  | "Open Risk Card"
              }
            />
          </dd>
        </div>
      </dl>
      <div className="ro-nav-row fleet-drill">
        {fleet.drillLinks.map((l) => (
          <Link key={l.to + l.label} className="ro-nav-chip ghost" to={l.to}>
            {l.label}
          </Link>
        ))}
      </div>
    </article>
  );
}

/** Market Command Center — polished trading-summary density (MVP-20). */
export function MarketCommandCenter() {
  const g = SYSTEM_GATE_STRIP;
  return (
    <section id="market-command" className="mcc-root" aria-label="Market Command Center">
      <div className="section-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          Market Command
        </h2>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <StatusBadge tone="blocked">Stage 4.19 BLOCKED</StatusBadge>
      </div>
      <p className="muted section-lede">
        Market Intelligence · read-only navigation · NOT INVESTMENT ADVICE
      </p>

      <section className="panel-card dense-card system-gate-strip" id="system-gate-strip">
        <h3 className="dense-subtitle" style={{ marginTop: 0 }}>
          System gate
        </h3>
        <div className="gate-strip-row">
          <span>
            Backend:{" "}
            <Link className="tone-hold deep-link" to="/evidence#artifact-4-18-p2h-rel">
              <strong>{g.backendState}</strong>
            </Link>
          </span>
          <span>
            Release:{" "}
            <Link className="deep-link" to="/evidence#artifact-4-18-p2h-rel">
              <strong>{g.releaseCheckpoint}</strong>
            </Link>
          </span>
          <span>
            Stage 4.19:{" "}
            <Link className="tone-blocked deep-link" to="/overview#checklist-stage-419-dossier">
              <strong>{g.stage419}</strong>
            </Link>
          </span>
          <span>
            Next: <strong>{g.nextAction}</strong>
          </span>
        </div>
        <div className="ro-nav-row" style={{ marginTop: "0.55rem" }}>
          <ReadOnlyNavChip label="View Runbook" to="/evidence#artifact-4-18-p2h-ops" />
          <ReadOnlyNavChip label="View Gate" to="/overview#checklist-stage-419-dossier" />
          <ReadOnlyNavChip label="View Evidence" to="/evidence?q=HOLD" />
        </div>
      </section>

      <div className="fleet-intel-grid" aria-label="Fleet summary">
        {FLEET_INTELLIGENCE.map((f) => (
          <FleetIntelCard key={f.symbol} fleet={f} />
        ))}
      </div>

      <div className="mcc-quick-nav">
        <ReadOnlyNavChip label="View Evidence" />
        <ReadOnlyNavChip label="Open Risk Card" />
        <ReadOnlyNavChip label="View Gate" />
        <ReadOnlyNavChip label="View Runbook" />
        <ReadOnlyNavChip label="View Provider History" />
        <ReadOnlyNavChip label="Ask AI" />
      </div>

      {/* Main: compact chips only — full AI Commander is right rail (MVP-20) */}
      <AIPromptChipStrip />
    </section>
  );
}
