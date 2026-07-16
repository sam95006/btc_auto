import { NEXUS_UI_BUILD_INFO } from "../demo/buildInfo";

/** Footer with full build marker — keeps top bar quiet (MVP-20 / 22A). */
export function AppFooter() {
  const b = NEXUS_UI_BUILD_INFO;
  return (
    <footer className="app-footer" aria-label="UI build footer">
      <span>
        {b.publicName} · UI Build: {b.uiVersion} · {b.latestCommit} · {b.uiStyle} ·{" "}
        {b.backendState}
      </span>
      <span className="mono footer-marker" title="Deploy marker">
        {b.buildMarker}
      </span>
      <span className="sr-only">{b.syncCompatibilityMarker}</span>
      <span>READ ONLY · NOT INVESTMENT ADVICE</span>
    </footer>
  );
}
