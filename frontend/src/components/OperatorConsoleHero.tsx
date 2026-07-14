import { DemoDataBadge } from "./DemoDataBadge";
import { ReleaseHealthBadge } from "./CheckpointHealthCard";
import { StatusBadge } from "./StatusBadge";

/** First-screen Private Operator console summary (MVP-13). */
export function OperatorConsoleHero({
  nextAllowedAction = "wait for ETH watch conditions",
}: {
  nextAllowedAction?: string;
}) {
  return (
    <section className="panel-card operator-console-hero" role="status" aria-label="Operator console">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.15rem" }}>Operator Console</h2>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <StatusBadge tone="blocked">Stage 4.19 BLOCKED</StatusBadge>
        <StatusBadge tone="wait">WAIT</StatusBadge>
        <ReleaseHealthBadge />
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · Private Operator total console · no
        auto-run
      </p>
      <div className="flag-grid console-hero-grid" style={{ marginTop: "0.85rem" }}>
        <div className="flag-item">
          <div className="k">Backend State</div>
          <div className="v">
            <StatusBadge tone="hold">HOLD</StatusBadge>
          </div>
        </div>
        <div className="flag-item">
          <div className="k">Release Checkpoint</div>
          <div className="v">
            <StatusBadge tone="pass">P2H</StatusBadge>
          </div>
        </div>
        <div className="flag-item">
          <div className="k">Stage 4.19</div>
          <div className="v">
            <StatusBadge tone="blocked">BLOCKED</StatusBadge>
          </div>
        </div>
        <div className="flag-item">
          <div className="k">Next Allowed Action</div>
          <div className="v">{nextAllowedAction}</div>
        </div>
        <div className="flag-item">
          <div className="k">30m now</div>
          <div className="v">false</div>
        </div>
        <div className="flag-item">
          <div className="k">60m</div>
          <div className="v">false</div>
        </div>
        <div className="flag-item">
          <div className="k">Auto-run</div>
          <div className="v">false</div>
        </div>
        <div className="flag-item">
          <div className="k">UI mode</div>
          <div className="v">
            <StatusBadge tone="ready">READ ONLY</StatusBadge>
          </div>
        </div>
      </div>
    </section>
  );
}
