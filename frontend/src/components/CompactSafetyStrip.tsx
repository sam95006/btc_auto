/** Single status line — no essay copy on home (MVP-22). */
export function CompactSafetyStrip() {
  return (
    <div className="compact-safety-strip" role="status">
      <span className="css-status-line">
        Status: Backend HOLD · ETH Gate Waiting · Stage 4.19 Blocked · Read-only
      </span>
      <span className="css-safe-badges" aria-label="Safety">
        <span className="css-pill pass">Safe</span>
        <span className="css-pill">No live trading</span>
      </span>
    </div>
  );
}
