import { useMarketScannerOverview } from "../market/useMarketScanner";
import { OpportunityCard } from "../components/OpportunityCard";
import { Link } from "react-router-dom";

/** Product 7 — Opportunities hub with evidence cards (no threshold changes). */
export function OpportunitiesPage() {
  const { longs, shorts, loading, error } = useMarketScannerOverview();

  return (
    <div className="page-stack nx-opportunities-p7">
      <header>
        <h1>機會</h1>
        <p className="muted">
          Scanner candidates · evidence / risk / invalidation · production gates unchanged
        </p>
      </header>
      {loading ? <p className="muted">載入中…</p> : null}
      {error ? <div className="nx-banner-warn">掃描器暫不可用：{error}</div> : null}
      <div className="nx-opp-grid nx-opp-grid-p7">
        <section aria-label="Long opportunities">
          <h2>做多</h2>
          {longs.length === 0 && !loading ? (
            <p className="muted">暫無做多機會</p>
          ) : (
            longs.slice(0, 12).map((c) => <OpportunityCard key={c.id} candidate={c} />)
          )}
        </section>
        <section aria-label="Short opportunities">
          <h2>做空</h2>
          {shorts.length === 0 && !loading ? (
            <p className="muted">暫無做空機會</p>
          ) : (
            shorts.slice(0, 12).map((c) => <OpportunityCard key={c.id} candidate={c} />)
          )}
        </section>
      </div>
      <p className="muted sm">
        <Link to="/overview">返回總覽</Link> · <Link to="/trade-plan">交易計畫</Link>
      </p>
    </div>
  );
}
