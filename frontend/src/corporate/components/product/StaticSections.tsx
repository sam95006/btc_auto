/**
 * Product-first static sections: How it works, Personal/Enterprise choice,
 * Trust/provenance, closing CTA. Product/trust content is backend/CMS-driven;
 * availability states (available/planned/contact) come from the CMS `products`
 * content — the frontend never implies an unshipped capability is live.
 */
import { Link } from "react-router-dom";
import { getContent } from "../../api/client";
import { useResource } from "../../hooks/useCorporate";
import { track } from "../../lib/analytics";
import type { ContentEnvelope, ProductFeature, ProductItem, ProductsContent, SecurityContent } from "../../types";

const STEPS = [
  { n: "01", t: "掃描即時市場", d: "BTC / ETH / SOL 的價格、波動與區間，一眼掃完。" },
  { n: "02", t: "讀取市場情報", d: "後端計算市場狀態與風險，直接給你判讀。" },
  { n: "03", t: "看見需要注意的", d: "情報事件與關注清單，告訴你現在該看哪裡。" },
  { n: "04", t: "選擇你的產品", d: "個人研究或企業工作區，進入更深的情報。" },
];

export function HowItWorks() {
  return (
    <section className="corp-fs-section corp-fs-band" aria-labelledby="fs-how">
      <div className="corp-fs-inner">
        <div className="corp-fs-head"><div><div className="corp-fs-eyebrow">HOW IT WORKS</div><h2 className="corp-fs-h2" id="fs-how">四步，讀懂市場情報</h2></div></div>
        <div className="corp-fs-steps">
          {STEPS.map((s) => (
            <div className="corp-fs-step" key={s.n}><div className="n">{s.n}</div><h4>{s.t}</h4><p>{s.d}</p></div>
          ))}
        </div>
      </div>
    </section>
  );
}

function featLabel(f: ProductFeature): string { return typeof f === "string" ? f : f.label; }
function featState(f: ProductFeature, fb?: string): string | undefined { return typeof f === "string" ? fb : f.state ?? fb; }
function avCls(s?: string): string { const x = (s || "").toLowerCase(); return x === "available" ? "available" : x === "contact" ? "contact" : x === "planned" ? "planned" : ""; }
const AV_ZH: Record<string, string> = { available: "已上線", planned: "即將推出", contact: "聯絡我們" };

function ChoiceCard({ p, primary }: { p: ProductItem; primary?: boolean }) {
  const isPersonal = p.key === "personal";
  return (
    <div className={`corp-fs-choice-card ${primary ? "primary" : ""}`} data-testid={`choice-${p.key}`}>
      <div className="corp-fs-eyebrow">{isPersonal ? "PERSONAL" : "ENTERPRISE"}</div>
      <h3>{p.title}</h3>
      <div className="corp-fs-choice-for">適合：{isPersonal ? "個人投資研究" : "團隊、研究部門、企業"}</div>
      <ul className="corp-fs-choice-feats">
        {(p.features ?? []).map((f, i) => {
          const st = featState(f, p.availability);
          const cls = avCls(st);
          return (
            <li key={i}>
              {st ? <span className={`corp-fs-av ${cls}`}>{AV_ZH[cls] || st}</span> : null}
              <span>{featLabel(f)}</span>
            </li>
          );
        })}
      </ul>
      <div style={{ marginTop: "0.6rem" }}>
        <Link to={p.to} className={isPersonal ? "corp-fs-btn" : "corp-fs-btn-ghost"}
          onClick={() => track(isPersonal ? "personal_interest" : "enterprise_interest", p.key)}>
          {isPersonal ? "進入個人版" : "了解企業版"}
        </Link>
      </div>
    </div>
  );
}

export function ProductChoice() {
  const state = useResource<ContentEnvelope<ProductsContent>>(() => getContent<ProductsContent>("products"), []);
  const items = state.status === "READY" ? state.data.data?.items ?? [] : [];
  const personal = items.find((i) => i.key === "personal");
  const enterprise = items.find((i) => i.key === "enterprise");
  return (
    <section className="corp-fs-section" aria-labelledby="fs-choice">
      <div className="corp-fs-inner">
        <div className="corp-fs-head"><div><div className="corp-fs-eyebrow">CHOOSE YOUR LAYER</div><h2 className="corp-fs-h2" id="fs-choice">選擇你需要的情報層級</h2></div></div>
        {items.length ? (
          <div className="corp-fs-choice">
            {personal ? <ChoiceCard p={personal} primary /> : null}
            {enterprise ? <ChoiceCard p={enterprise} /> : null}
          </div>
        ) : state.status === "LOADING" ? <div className="corp-fs-loading">載入產品…</div> : <div className="corp-fs-unavail">產品資料暫不可用</div>}
      </div>
    </section>
  );
}

function Shield() {
  return <svg className="corp-fs-trust-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
    <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export function TrustFlagship() {
  const state = useResource<ContentEnvelope<SecurityContent>>(() => getContent<SecurityContent>("security"), []);
  const points = state.status === "READY" ? state.data.data?.points ?? [] : [];
  return (
    <section className="corp-fs-section corp-fs-band" aria-labelledby="fs-trust">
      <div className="corp-fs-inner">
        <div className="corp-fs-head"><div><div className="corp-fs-eyebrow">TRUST · PROVENANCE</div>
          <h2 className="corp-fs-h2" id="fs-trust">每個數字都可以追溯來源</h2>
          <p className="corp-fs-sub">所有數據由後端提供、標註來源與時間；私有交易與網站完全隔離。</p></div></div>
        {points.length ? (
          <div className="corp-fs-trust-grid">
            {points.map((p, i) => <div className="corp-fs-trust-card" key={i} data-testid="trust-item"><h4><Shield />{p.title}</h4><p>{p.body}</p></div>)}
          </div>
        ) : <div className="corp-fs-loading">載入中…</div>}
      </div>
    </section>
  );
}

export function ClosingCta() {
  return (
    <section className="corp-fs-section" aria-labelledby="fs-cta">
      <div className="corp-fs-inner">
        <div className="corp-fs-cta">
          <h2 id="fs-cta">把市場資料，變成可以判讀的情報</h2>
          <p>即時、可追溯、唯讀的市場情報層。現在開始。</p>
          <div className="corp-fs-hero-cta" style={{ justifyContent: "center" }}>
            <Link to="/personal" className="corp-fs-btn" onClick={() => track("cta_primary", "closing")}>進入個人版</Link>
            <Link to="/enterprise" className="corp-fs-btn-ghost" onClick={() => track("cta_enterprise", "closing")}>了解企業版</Link>
          </div>
        </div>
      </div>
    </section>
  );
}
