import { Link } from "react-router-dom";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { MEMBER_NAV } from "../../member/routes";
import { BoundLiveValue, useLiveBindings } from "../../public_v2_live_binding";

export function MemberHomePage() {
  const { slot, loading } = useLiveBindings();
  const hero = slot("home.hero_decision_summary", "posture");
  const market = slot("home.market_context_card", "btc");
  const fresh = slot("home.freshness_chip", "freshness");
  const risk = slot("home.risk_open_chip", "qual");

  return (
    <MemberPageChrome
      title="NEXUS Member Home"
      subtitle="Crypto Decision Integrity Platform · Decision Operating System for serious crypto investors"
    >
      <section className="member-hero-card" aria-label="Home summary">
        <p className="member-kicker">Public Member Platform</p>
        <h2 className="member-hero-title">Decision Integrity · not automated trading</h2>
        <p className="muted">
          Record Context to Thesis to Evidence to Decision to Monitor to Outcome to Review. You
          remain the final decision-maker. No exchange orders from this product.
        </p>
        <div className="member-cta-row">
          <Link className="member-btn primary" to="/decisions">
            Open Decision Feed
          </Link>
          <Link className="member-btn" to="/thesis-monitor">
            Thesis Monitor
          </Link>
          <Link className="member-btn" to="/outcome-review">
            Outcome Review
          </Link>
        </div>
      </section>

      <section className="member-stat-grid" aria-label="Home live bindings">
        {loading ? <p className="muted">Loading live bindings...</p> : null}
        <BoundLiveValue binding={hero} label="Decision cloud" />
        <BoundLiveValue binding={market} label="BTC last" />
        <BoundLiveValue binding={fresh} label="Freshness" />
        <BoundLiveValue binding={risk} label="Qualification" />
      </section>

      <section className="member-panel" aria-label="Navigate">
        <h2 className="nx-sec-title">Navigate</h2>
        <ul className="member-link-grid">
          {MEMBER_NAV.map((item) => (
            <li key={item.to}>
              <Link to={item.to}>{item.label}</Link>
            </li>
          ))}
        </ul>
      </section>
    </MemberPageChrome>
  );
}
