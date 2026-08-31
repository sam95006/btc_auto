/**
 * Trust layer — makes "backend is the source of truth" a visual selling point.
 * The pillars come from the backend CMS `security` content (owner-editable);
 * the frontend adds no claims of its own. No secrets are exposed.
 */
import { getContent } from "../../api/client";
import { useResource, useReveal } from "../../hooks/useCorporate";
import type { ContentEnvelope, SecurityContent } from "../../types";

function ShieldIcon() {
  return (
    <svg className="corp-trust-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function TrustLayer() {
  const state = useResource<ContentEnvelope<SecurityContent>>(() => getContent<SecurityContent>("security"), []);
  const { ref, shown } = useReveal<HTMLDivElement>();
  const points = state.status === "READY" ? state.data.data?.points ?? [] : [];

  return (
    <section className="corp-section" aria-labelledby="corp-trust-h">
      <div className="corp-section-inner" ref={ref}>
        <div className={`corp-reveal ${shown ? "is-shown" : ""}`} style={{ ["--p" as string]: shown ? "1" : "0" }}>
          <div className="corp-eyebrow">TRUST · PROVENANCE · ISOLATION</div>
          <h2 className="corp-h2" id="corp-trust-h">信任來自可驗證，而非宣稱 / Trust you can verify, not just claims</h2>
          <p className="corp-lead">
            Every number on this site is backend-owned, sourced and time-stamped. Products are separated by design,
            and private trading is fully isolated from everything shown here.
          </p>
        </div>
        {points.length ? (
          <div className="corp-trust" style={{ marginTop: "1.75rem" }}>
            {points.map((p, i) => (
              <div key={i} className="corp-trust-item" data-testid="trust-item">
                <h3><ShieldIcon />{p.title}</h3>
                <p>{p.body}</p>
              </div>
            ))}
          </div>
        ) : state.status === "LOADING" ? (
          <div className="corp-state corp-state-loading" role="status">載入中… / loading…</div>
        ) : (
          <div className="corp-state corp-state-unavailable" role="status">內容暫不可用 / unavailable</div>
        )}
      </div>
    </section>
  );
}
