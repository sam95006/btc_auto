import { NEXUS_UI_BUILD_INFO } from "../demo/buildInfo";

/** Footer with full build marker — keeps top bar quiet (MVP-20). */
export function AppFooter() {
  const b = NEXUS_UI_BUILD_INFO;
  return (
    <footer className="app-footer" aria-label="UI build footer">
      <span>
        UI Build: {b.uiVersion} · {b.latestCommit} · {b.uiStyle} · {b.backendState}
      </span>
      <span className="mono footer-marker" title="Deploy marker">
        {b.buildMarker}
      </span>
      <span>READ ONLY · NOT INVESTMENT ADVICE</span>
    </footer>
  );
}
