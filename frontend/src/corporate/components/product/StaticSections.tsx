/**
 * Simplified static sections (CORPORATE-4): Personal/Enterprise choice, a compact
 * Trust section with a progressive-disclosure "technical details" drawer, and the
 * closing CTA. Product/trust content is backend/CMS-driven and locale-aware;
 * availability states come from the CMS — never implying an unshipped capability.
 */
import { Link } from "react-router-dom";
import { getContent } from "../../api/client";
import { useResource } from "../../hooks/useCorporate";
import { useLocale } from "../../i18n";
import { track } from "../../lib/analytics";
import type { ContentEnvelope, ProductFeature, ProductItem, ProductsContent, SecurityContent } from "../../types";

function featLabel(f: ProductFeature): string { return typeof f === "string" ? f : f.label; }
function featState(f: ProductFeature, fb?: string): string | undefined { return typeof f === "string" ? fb : f.state ?? fb; }
function avCls(s?: string): string { const x = (s || "").toLowerCase(); return x === "available" ? "available" : x === "contact" ? "contact" : x === "planned" ? "planned" : ""; }

function ChoiceCard({ p, primary }: { p: ProductItem; primary?: boolean }) {
  const { t } = useLocale();
  const isPersonal = p.key === "personal";
  const AV: Record<string, string> = { available: t("av_available"), planned: t("av_planned"), contact: t("av_contact") };
  return (
    <div className={`corp-fs-choice-card ${primary ? "primary" : ""}`} data-testid={`choice-${p.key}`}>
      <div className="corp-fs-eyebrow">{isPersonal ? t("choose_personal") : t("choose_enterprise")}</div>
      <h3>{p.title}</h3>
      <div className="corp-fs-choice-for">{isPersonal ? t("choose_personal_for") : t("choose_enterprise_for")}</div>
      <ul className="corp-fs-choice-feats">
        {(p.features ?? []).slice(0, 4).map((f, i) => {
          const st = featState(f, p.availability); const cls = avCls(st);
          return <li key={i}>{st ? <span className={`corp-fs-av ${cls}`}>{AV[cls] || st}</span> : null}<span>{featLabel(f)}</span></li>;
        })}
      </ul>
      <div style={{ marginTop: "0.7rem" }}>
        <Link to={p.to} className={isPersonal ? "corp-fs-btn" : "corp-fs-btn-ghost"}
          onClick={() => track(isPersonal ? "personal_interest" : "enterprise_interest", p.key)}>
          {isPersonal ? t("choose_personal_cta") : t("choose_enterprise_cta")}
        </Link>
      </div>
    </div>
  );
}

export function ProductChoice() {
  const { locale, t } = useLocale();
  const state = useResource<ContentEnvelope<ProductsContent>>(() => getContent<ProductsContent>("products", locale), [locale]);
  const items = state.status === "READY" ? state.data.data?.items ?? [] : [];
  const personal = items.find((i) => i.key === "personal");
  const enterprise = items.find((i) => i.key === "enterprise");
  return (
    <section className="corp-fs-section corp-fs-band" aria-labelledby="fs-choice">
      <div className="corp-fs-inner">
        <div className="corp-fs-head"><div><div className="corp-fs-eyebrow">FOR YOU</div>
          <h2 className="corp-fs-h2" id="fs-choice">{t("choose_title")}</h2></div></div>
        {items.length ? (
          <div className="corp-fs-choice">
            {personal ? <ChoiceCard p={personal} primary /> : null}
            {enterprise ? <ChoiceCard p={enterprise} /> : null}
          </div>
        ) : state.status === "LOADING" ? <div className="corp-fs-loading">{t("st_loading")}</div> : <div className="corp-fs-unavail">{t("st_unavailable")}</div>}
      </div>
    </section>
  );
}

function Shield() {
  return <svg className="corp-fs-trust-ico" width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
    <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export function TrustCompact() {
  const { locale, t } = useLocale();
  const state = useResource<ContentEnvelope<SecurityContent>>(() => getContent<SecurityContent>("security", locale), [locale]);
  const points = state.status === "READY" ? state.data.data?.points ?? [] : [];
  const top = points.slice(0, 3);
  const rest = points.slice(3);
  return (
    <section className="corp-fs-section" aria-labelledby="fs-trust">
      <div className="corp-fs-inner">
        <div className="corp-fs-head"><div><div className="corp-fs-eyebrow">TRUST</div>
          <h2 className="corp-fs-h2" id="fs-trust">{t("trust_title")}</h2>
          <p className="corp-fs-sub">{t("trust_sub")}</p></div></div>
        {top.length ? (
          <div className="corp-trust-compact">
            {top.map((p, i) => <div className="corp-trust-mini" key={i} data-testid="trust-item"><h4><Shield />{p.title}</h4><p>{p.body}</p></div>)}
          </div>
        ) : <div className="corp-fs-loading">{t("st_loading")}</div>}
        {rest.length ? (
          <details className="corp-disclose">
            <summary>{t("trust_more")}</summary>
            <div className="corp-disclose-body">
              {rest.map((p, i) => <div key={i}><strong>{p.title}</strong> — {p.body}</div>)}
            </div>
          </details>
        ) : null}
      </div>
    </section>
  );
}

export function ClosingCta() {
  const { t } = useLocale();
  return (
    <section className="corp-fs-section" aria-labelledby="fs-cta">
      <div className="corp-fs-inner">
        <div className="corp-fs-cta">
          <h2 id="fs-cta">{t("cta_title")}</h2>
          <p>{t("cta_sub")}</p>
          <div className="corp-fs-hero-cta" style={{ justifyContent: "center" }}>
            <Link to="/personal" className="corp-fs-btn" onClick={() => track("cta_primary", "closing")}>{t("cta_button")}</Link>
            <Link to="/products" className="corp-fs-hero-link">{t("cta_view")} →</Link>
          </div>
        </div>
      </div>
    </section>
  );
}
