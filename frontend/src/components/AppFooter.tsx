import { NEXUS_UI_BUILD_INFO } from "../demo/buildInfo";

/** Member Platform product footer. */
export function AppFooter() {
  const b = NEXUS_UI_BUILD_INFO;
  return (
    <footer className="app-footer nx-footer-member" aria-label="Product footer">
      <span>
        NEXUS Member Platform · Decision Integrity · NOT INVESTMENT ADVICE · NO LIVE TRADING ·
        LOCAL/STAGING
      </span>
      <span className="sr-only">{b.buildMarker}</span>
      <span className="sr-only">
        {b.uiVersion} · {b.backendState} · member-platform
      </span>
    </footer>
  );
}
