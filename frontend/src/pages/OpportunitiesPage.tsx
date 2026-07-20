import { useMarketScannerOverview } from "../market/useMarketScanner";
import { Link } from "react-router-dom";

/** Phase 6.5 — Opportunities hub (scanner-derived, no threshold changes). */
export function OpportunitiesPage() {
  const { longs, shorts, loading } = useMarketScannerOverview();

  return (
    <div className="page-stack">
      <header>
        <h1>機會</h1>
        <p className="muted">Scanner candidates — production gates unchanged.</p>
      </header>
      {loading ? <p className="muted">Loading…</p> : null}
      <div className="nx-opp-grid">
        <section>
          <h2>Long</h2>
          {longs.slice(0, 8).map((c) => (
            <Link key={c.id} to={`/market/${c.symbol}`} className="nx-opp-row">
              {c.symbol} · opp {Math.round(c.opportunityScore)} · {c.freshness ?? "—"}
            </Link>
          ))}
        </section>
        <section>
          <h2>Short</h2>
          {shorts.slice(0, 8).map((c) => (
            <Link key={c.id} to={`/market/${c.symbol}`} className="nx-opp-row">
              {c.symbol} · opp {Math.round(c.opportunityScore)} · {c.freshness ?? "—"}
            </Link>
          ))}
        </section>
      </div>
    </div>
  );
}
