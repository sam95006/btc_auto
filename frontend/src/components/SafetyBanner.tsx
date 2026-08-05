/**
 * Member Platform safety chrome — public Decision Integrity surface.
 * No live trading · no external reference embed · DEMO mode disclosed when fixtures bound.
 */
export function SafetyBanner() {
  return (
    <div className="safety-banner nx-safety-member" role="status">
      <span className="nx-safety-primary">NEXUS Member · Decision Integrity</span>
      <span className="nx-safety-sep" aria-hidden>
        ·
      </span>
      <span className="nx-safety-secondary">
        READ-ONLY vs exchanges · NOT INVESTMENT ADVICE · NO LIVE TRADING · DEMO DATA when fixtures
        bound · LOCAL/STAGING ONLY
      </span>
    </div>
  );
}
