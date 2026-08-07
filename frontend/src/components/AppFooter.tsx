import { NEXUS_UI_BUILD_INFO } from "../demo/buildInfo";

/** Member Platform product footer — legal strip, not dominant chrome. */
export function AppFooter() {
  const b = NEXUS_UI_BUILD_INFO;
  return (
    <footer className="app-footer nx-footer-member" aria-label="Product footer">
      <span>NEXUS · 全市場情報 · 非投資建議 · 不下單 · LOCAL/STAGING</span>
      <span className="sr-only">{b.buildMarker}</span>
      <span className="sr-only">
        {b.uiVersion} · {b.backendState} · member-platform
      </span>
    </footer>
  );
}
