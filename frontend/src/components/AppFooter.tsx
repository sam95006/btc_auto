import { NEXUS_UI_BUILD_INFO } from "../demo/buildInfo";



/** Compact product footer — no top legal wall. */

export function AppFooter() {

  const b = NEXUS_UI_BUILD_INFO;

  return (

    <footer className="app-footer nx-footer-member v1828-footer v1829-footer" aria-label="Product footer">

      <span>NEXUS · 全市場情報 · 非投資建議 · 不下單</span>

      <span className="sr-only">{b.buildMarker}</span>

      <span className="sr-only">

        {b.uiVersion} · {b.backendState} · member-platform

      </span>

    </footer>

  );

}

