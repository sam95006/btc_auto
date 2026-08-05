import { Link } from "react-router-dom";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { MEMBER_ACCOUNT_SUBNAV } from "../../member/routes";

export function MemberAccountPage() {
  return (
    <MemberPageChrome
      title="Account"
      subtitle="Public identity realm stub · no shared private JWT · no production customer DB"
    >
      <section className="member-panel">
        <h2 className="nx-sec-title">Profile (DEMO)</h2>
        <dl className="member-dl">
          <div>
            <dt>Display name</dt>
            <dd>Member Preview</dd>
          </div>
          <div>
            <dt>Realm</dt>
            <dd>public_member_staging</dd>
          </div>
          <div>
            <dt>Role</dt>
            <dd>FREE_PREVIEW</dd>
          </div>
          <div>
            <dt>Consent</dt>
            <dd>Research / Decision Support · not investment advice</dd>
          </div>
        </dl>
      </section>
      <section className="member-panel">
        <h2 className="nx-sec-title">Account links</h2>
        <ul className="member-link-grid">
          {MEMBER_ACCOUNT_SUBNAV.map((item) => (
            <li key={item.to}>
              <Link to={item.to}>{item.label}</Link>
            </li>
          ))}
        </ul>
      </section>
    </MemberPageChrome>
  );
}
