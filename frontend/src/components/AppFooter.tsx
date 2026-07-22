import { NEXUS_UI_BUILD_INFO } from "../demo/buildInfo";

/** Phase 4 product footer — engineering strings only in System Status / sr-only. */
export function AppFooter() {
  const b = NEXUS_UI_BUILD_INFO;
  return (
    <footer className="app-footer nx-footer-p4" aria-label="Product footer">
      <span>NEXUS Market Intelligence · Live public market data for research use</span>
      <span className="sr-only">{b.buildMarker}</span>
      <span className="sr-only">{b.phase4LegacyMarker}</span>
      <span className="sr-only">{b.phase3LegacyMarker}</span>
      <span className="sr-only">{b.phase2LegacyMarker}</span>
      <span className="sr-only">{b.phase1LegacyMarker}</span>
      <span className="sr-only">{b.mvp22dLegacyMarker}</span>
      <span className="sr-only">{b.mvp22cLegacyMarker}</span>
      <span className="sr-only">{b.mvp22bLegacyMarker}</span>
      <span className="sr-only">{b.mvp22aLegacyMarker}</span>
      <span className="sr-only">{b.syncCompatibilityMarker}</span>
      <span className="sr-only">
        {b.uiVersion} · {b.backendState} · {b.stage419}
      </span>
    </footer>
  );
}
