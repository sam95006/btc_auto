/**
 * Personal ↔ Enterprise branching. Product cards and per-feature availability
 * come from the backend CMS `products` content — the frontend never invents a
 * feature or claims Enterprise capability that the backend has not marked
 * available. Truthful AVAILABLE / PLANNED / CONTACT states are shown.
 */
import { Link } from "react-router-dom";
import { getContent } from "../../api/client";
import { useResource, useReveal } from "../../hooks/useCorporate";
import { track } from "../../lib/analytics";
import type { ContentEnvelope, ProductFeature, ProductItem, ProductsContent } from "../../types";

function featLabel(f: ProductFeature): string {
  return typeof f === "string" ? f : f.label;
}
function featState(f: ProductFeature, fallback?: string): string | undefined {
  return typeof f === "string" ? fallback : f.state ?? fallback;
}
function availClass(state?: string): string {
  const s = (state || "").toLowerCase();
  return s === "available" ? "available" : s === "contact" ? "contact" : s === "planned" ? "planned" : "";
}

function ProductCard({ p }: { p: ProductItem }) {
  const isPersonal = p.key === "personal";
  return (
    <div className="corp-branch-card" data-testid={`branch-${p.key}`}>
      <div className="corp-eyebrow">{isPersonal ? "FOR INDIVIDUALS" : "FOR ORGANIZATIONS"}</div>
      <h3>{p.title}</h3>
      <p className="sub">{p.summary}</p>
      {p.features && p.features.length ? (
        <ul className="corp-feat">
          {p.features.map((f, i) => {
            const st = featState(f, p.availability);
            return (
              <li key={i}>
                {st ? <span className={`corp-avail ${availClass(st)}`}>{st}</span> : null}
                <span>{featLabel(f)}</span>
              </li>
            );
          })}
        </ul>
      ) : null}
      <div className="corp-scene-cta" style={{ marginTop: "0.9rem" }}>
        <Link
          to={p.to}
          className={isPersonal ? "corp-btn corp-btn-sm" : "corp-btn-ghost corp-btn-sm"}
          onClick={() => track(isPersonal ? "personal_interest" : "enterprise_interest", p.key)}
        >
          {isPersonal ? "了解個人版 / Explore Personal" : "了解企業版 / Explore Enterprise"}
        </Link>
      </div>
    </div>
  );
}

export function PersonalEnterpriseBranch() {
  const state = useResource<ContentEnvelope<ProductsContent>>(() => getContent<ProductsContent>("products"), []);
  const { ref, shown } = useReveal<HTMLDivElement>();
  const items = state.status === "READY" ? state.data.data?.items ?? [] : [];

  return (
    <section className="corp-section" aria-labelledby="corp-branch-h">
      <div className="corp-section-inner" ref={ref}>
        <div className={`corp-reveal ${shown ? "is-shown" : ""}`} style={{ ["--p" as string]: shown ? "1" : "0" }}>
          <div className="corp-eyebrow">ONE CORE · TWO PRODUCTS</div>
          <h2 className="corp-h2" id="corp-branch-h">同一情報核心，兩種產品 / One intelligence core, two products</h2>
          <p className="corp-lead">
            The same deterministic intelligence engine powers a product for individuals and a separate product for
            organizations. Availability is shown honestly — nothing is implied before it ships.
          </p>
        </div>
        {items.length ? (
          <div className="corp-branch" style={{ marginTop: "1.75rem" }}>
            {items.map((p) => <ProductCard key={p.key} p={p} />)}
          </div>
        ) : state.status === "LOADING" ? (
          <div className="corp-state corp-state-loading" role="status">載入中… / loading…</div>
        ) : (
          <div className="corp-state corp-state-unavailable" role="status">產品資料暫不可用 / product data unavailable</div>
        )}
      </div>
    </section>
  );
}
