import { Link } from "react-router-dom";
import { useT } from "../../i18n";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";
import { MEMBER_ACCOUNT_SUBNAV } from "../../member/routes";

/** Account — PUB2-B live bindings + PUB2-J i18n; no DEMO profile fabrication. */
export function MemberAccountPage() {
  const t = useT();
  const { loading, items } = usePageSlots([
    ["account.profile_card", "runtime", "Profile runtime"],
    ["account.locale_chip", "freshness", "Locale freshness"],
  ]);

  return (
    <MemberPageChrome titleKey="pages.account.title" subtitleKey="pages.account.subtitle">
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <p className="muted sm">
        Profile fields UNAVAILABLE until auth realm binds · no synthetic live profile.
      </p>
      <section className="member-panel">
        <h2 className="nx-sec-title">Account links</h2>
        <ul className="member-link-grid">
          {MEMBER_ACCOUNT_SUBNAV.map((item) => (
            <li key={item.to}>
              <Link to={item.to}>{t(item.labelKey)}</Link>
            </li>
          ))}
        </ul>
      </section>
    </MemberPageChrome>
  );
}
