import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { getSite } from "../api/client";
import { useResource } from "../hooks/useCorporate";
import type { ContentEnvelope, SiteContent } from "../types";

/** Nav + footer, driven by the backend `site` CMS content. Brand is a
 * backend-configurable placeholder (rename-safe). */
export function Chrome({ children }: { children: ReactNode }) {
  const state = useResource<ContentEnvelope<SiteContent>>(getSite, []);
  const site = state.status === "READY" ? state.data.data : undefined;
  const brand = site?.brand?.name ?? "NEXUS";
  return (
    <div className="corp-root">
      <header className="corp-nav">
        <Link to="/" className="corp-brand" data-testid="brand">{brand}</Link>
        <nav aria-label="corporate">
          {(site?.nav ?? []).map((n) => (
            <Link key={n.to} to={n.to}>{n.label}</Link>
          ))}
        </nav>
        <div className="corp-nav-cta">
          {site?.cta?.personal ? <a href={site.cta.personal.href} data-testid="login-personal">{site.cta.personal.label}</a> : null}
          {site?.cta?.enterprise ? <a href={site.cta.enterprise.href} data-testid="login-enterprise" className="corp-btn-ghost">{site.cta.enterprise.label}</a> : null}
        </div>
      </header>
      <main>{children}</main>
      <footer className="corp-footer">
        <div className="corp-footer-cols">
          {(site?.footer?.columns ?? []).map((col) => (
            <div key={col.title}>
              <h4>{col.title}</h4>
              {col.links.map((l) => <Link key={l.to} to={l.to}>{l.label}</Link>)}
            </div>
          ))}
        </div>
        <p className="corp-footer-note">{site?.footer?.note ?? "READ-ONLY · research platform · not investment advice"}</p>
      </footer>
    </div>
  );
}
