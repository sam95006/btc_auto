import { NEXUS_UI_BUILD_INFO } from "../demo/buildInfo";
import { DemoDataBadge } from "./DemoDataBadge";

/**
 * Top bar display chips only — not controls (MVP-17).
 * Includes UI-DEPLOY-1 build marker · READ ONLY · NOT INVESTMENT ADVICE
 */
export function TopStatusBar() {
  const b = NEXUS_UI_BUILD_INFO;
  return (
    <header className="top-status-bar" role="status">
      <div className="brand-mark">
        NEXUS / <span>EATI</span>
      </div>
      <span className="status-chip tone-hold">
        Backend State: <strong>HOLD</strong>
      </span>
      <span className="status-chip">
        Release: <strong>P2H</strong>
      </span>
      <span className="status-chip tone-blocked">
        Stage 4.19: <strong>BLOCKED</strong>
      </span>
      <span className="status-chip">Runtime: paused</span>
      <span className="status-chip mode">Mode: READ ONLY</span>
      <span className="status-chip">No auto-run</span>
      <span className="status-chip disclaimer">NOT INVESTMENT ADVICE</span>
      <span className="status-chip mono" title={b.buildMarker}>
        UI Build: {b.uiVersion} · {b.latestCommit} · {b.uiStyle} · {b.backendState}
      </span>
      <DemoDataBadge />
    </header>
  );
}
