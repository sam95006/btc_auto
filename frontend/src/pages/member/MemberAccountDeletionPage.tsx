import { useState } from "react";
import { MemberPageChrome } from "../../member/MemberPageChrome";

export function MemberAccountDeletionPage() {
  const [armed, setArmed] = useState(false);
  const [done, setDone] = useState(false);

  return (
    <MemberPageChrome
      title="Account Deletion"
      subtitle="Staging stub · no production customer database · irreversible only after real auth lane"
    >
      <section className="member-panel">
        <p>
          Requesting deletion will remove public-realm Decision Graph data associated with your
          member identity once the auth foundation is wired. This DEMO does not call production
          APIs.
        </p>
        <label className="member-check">
          <input type="checkbox" checked={armed} onChange={(e) => setArmed(e.target.checked)} /> I
          understand this is a LOCAL/STAGING stub and does not delete production data.
        </label>
        <div className="member-cta-row">
          <button
            type="button"
            className="member-btn warn"
            disabled={!armed || done}
            onClick={() => setDone(true)}
          >
            Request deletion (DEMO)
          </button>
        </div>
        {done ? (
          <p className="member-ok" role="status">
            DEMO request recorded locally in UI state only · no backend mutation.
          </p>
        ) : null}
      </section>
    </MemberPageChrome>
  );
}
