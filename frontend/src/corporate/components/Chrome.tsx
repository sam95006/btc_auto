import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { getSite } from "../api/client";
import { useResource } from "../hooks/useCorporate";
import { track } from "../lib/analytics";
import type { ContentEnvelope, SiteContent } from "../types";

/** Nav + footer, driven by the backend `site` CMS content. Brand is a
 * backend-configurable placeholder (rename-safe). Adds a skip link, a semantic
 * <main> landmark, and a scroll-state on the nav for the cinematic chrome. */
export function Chrome({ children }: { children: ReactNode }) {
  const state = useResource<ContentEnvelope<SiteContent>>(getSite, []);
  const site = state.status === "READY" ? state.data.data : undefined;
  const brand = site?.brand?.name ?? "NEXUS";
  const navRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const el = navRef.current;
    if (!el) return;
    const onScroll = () => el.classList.toggle("is-scrolled", window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="corp-root">
      <a href="#corp-main" className="corp-skip-link">跳到主要內容 / Skip to content</a>
      <header className="corp-nav" ref={navRef}>
        <Link to="/" className="corp-brand-mark" data-testid="brand" aria-label={`${brand} home`}>
          <span className="corp-brand-glyph" aria-hidden />
          <span className="corp-brand">{brand}</span>
        </Link>
        <nav aria-label="Primary">
          {(site?.nav ?? []).map((n) => (
            <Link key={n.to} to={n.to}>{n.label}</Link>
          ))}
        </nav>
        <div className="corp-nav-cta">
          {site?.cta?.personal ? (
            <a href={site.cta.personal.href} data-testid="login-personal" onClick={() => track("cta_personal", "nav")}>
              {site.cta.personal.label}
            </a>
          ) : null}
          {site?.cta?.enterprise ? (
            <a href={site.cta.enterprise.href} data-testid="login-enterprise" className="corp-btn-ghost corp-btn-sm"
               onClick={() => track("cta_enterprise", "nav")}>
              {site.cta.enterprise.label}
            </a>
          ) : null}
        </div>
      </header>
      <main id="corp-main">{children}</main>
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
