/** Tiny home safety strip — details live on Risk Center (MVP-22). */
export function CompactSafetyStrip() {
  return (
    <div className="compact-safety-strip" role="status">
      <span className="css-pill pass">Safe</span>
      <span className="css-pill">Read-only</span>
      <span className="css-pill">No live trading</span>
      <span className="css-pill hold">HOLD</span>
      <span className="css-pill blocked">4.19 BLOCKED</span>
      <span className="muted css-next">Next: Wait for ETH Gate</span>
    </div>
  );
}
