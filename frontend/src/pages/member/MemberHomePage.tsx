import { Link } from "react-router-dom";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { alerts, decisions, marketOverviewCards } from "../../member/demoCatalog";
import { MEMBER_NAV } from "../../member/routes";

export function MemberHomePage() {
  const open = decisions.filter((d) => d.outcomeClass === "PENDING").length;
  const warn = alerts.filter((a) => a.severity !== "INFO").length;

  return (
    <MemberPageChrome
      title="NEXUS Member Home"
      subtitle="Crypto Decision Integrity Platform · Decision Operating System for serious crypto investors"
    >
      <section className="member-hero-card" aria-label="Home summary">
        <p className="member-kicker">Public Member Platform</p>
        <h2 className="member-hero-title">Decision Integrity · not automated trading</h2>
        <p className="muted">
          Record Context → Thesis → Evidence → Decision → Monitor → Outcome → Review. You remain the
          final decision-maker. No exchange orders from this product.
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

      <section className="member-stat-grid" aria-label="Home metrics">
        <article className="member-stat">
          <strong>{open}</strong>
          <span>Open Decisions</span>
        </article>
        <article className="member-stat">
          <strong>{warn}</strong>
          <span>Active alerts</span>
        </article>
        <article className="member-stat">
          <strong>{marketOverviewCards.length}</strong>
          <span>Market context cards</span>
        </article>
        <article className="member-stat">
          <strong>DEMO</strong>
          <span>Data mode</span>
        </article>
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
