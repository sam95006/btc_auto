import { NEXUS_UI_BUILD_INFO } from "../demo/buildInfo";

/**
 * Compact top bar — high-priority chips only (MVP-20).
 * Secondary details in tooltip / secondary row. No trade controls.
 */
export function TopStatusBar() {
  const b = NEXUS_UI_BUILD_INFO;
  const secondaryTitle = [
    `Release P2H`,
    `Runtime paused`,
    `No auto-run`,
    `NOT INVESTMENT ADVICE`,
    `DEMO DATA`,
    b.buildMarker,
  ].join(" · ");

  return (
    <header className="top-status-bar" role="status">
      <div className="top-status-primary">
        <div className="brand-mark">
          NEXUS / <span>EATI</span>
        </div>
        <span className="status-chip tone-hold compact" title="Backend state">
          Backend: <strong>HOLD</strong>
        </span>
        <span className="status-chip tone-blocked compact" title="Stage 4.19 blocked">
          Stage 4.19: <strong>BLOCKED</strong>
        </span>
        <span className="status-chip mode compact" title="Read-only operator console">
          Mode: <strong>READ ONLY</strong>
        </span>
        <span className="status-chip mono compact" title={b.buildMarker}>
          UI Build: {b.displayLabel}
        </span>
      </div>
      <div className="top-status-secondary" title={secondaryTitle}>
        <span className="top-sec-item">P2H</span>
        <span className="top-sec-sep">·</span>
        <span className="top-sec-item">paused</span>
        <span className="top-sec-sep">·</span>
        <span className="top-sec-item">no auto-run</span>
        <span className="top-sec-sep">·</span>
        <span className="top-sec-item hide-sm">NOT INVESTMENT ADVICE</span>
        <span className="top-sec-sep hide-sm">·</span>
        <span className="top-sec-item hide-sm">DEMO DATA</span>
      </div>
    </header>
  );
}
