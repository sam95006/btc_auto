import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { getSite } from "../api/client";
import { useResource } from "../hooks/useCorporate";
import { useLocale } from "../i18n";
import { track } from "../lib/analytics";
import type { ContentEnvelope, SiteContent } from "../types";
import { LocaleControl, ThemeControl } from "./Controls";

/** Minimal localized header (brand + 4 nav items + language/theme/login/CTA) and
 * a compact footer. Brand comes from the backend `site` CMS; nav labels + CTAs
 * are localized chrome (one active language, no bilingual clutter). */
export function Chrome({ children }: { children: ReactNode }) {
  const { locale, t } = useLocale();
  const state = useResource<ContentEnvelope<SiteContent>>(() => getSite(locale), [locale]);
  const site = state.status === "READY" ? state.data.data : undefined;
  const brand = site?.brand?.name ?? "NEXUS";
  const loginHref = site?.cta?.personal?.href ?? "/personal.html";
  const navRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const el = navRef.current;
    if (!el) return;
    const onScroll = () => el.classList.toggle("is-scrolled", window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const nav: [string, string][] = [
    ["/products", t("nav_products")], ["/personal", t("nav_personal")],
    ["/enterprise", t("nav_enterprise")], ["/about", t("nav_about")],
  ];

  return (
    <div className="corp-root corp-fs">
      <a href="#corp-main" className="corp-skip-link">{t("nav_about") ? "跳到主要內容" : "Skip to content"}</a>
      <header className="corp-nav corp-fs-nav" ref={navRef}>
        <Link to="/" className="corp-brand-mark" aria-label={`${brand} home`}>
          <span className="corp-brand-glyph" aria-hidden />
          <span className="corp-brand">{brand}</span>
        </Link>
        <nav aria-label="Primary" className="corp-fs-navlinks">
          {nav.map(([to, label]) => <Link key={to} to={to}>{label}</Link>)}
        </nav>
        <div className="corp-fs-navctrl">
          <LocaleControl />
          <ThemeControl />
          <a href={loginHref} className="corp-fs-navlogin" data-testid="login-personal" onClick={() => track("cta_personal", "nav")}>{t("login")}</a>
          <Link to="/personal" className="corp-fs-btn corp-btn-sm" onClick={() => track("cta_primary", "nav")}>{t("cta_start")}</Link>
          <a href={site?.cta?.enterprise?.href ?? "/enterprise.html"} data-testid="login-enterprise" style={{ display: "none" }} aria-hidden>{t("nav_enterprise")}</a>
        </div>
      </header>
      <main id="corp-main">{children}</main>
      <footer className="corp-footer corp-fs-footer">
        <div className="corp-fs-footer-row">
          <span className="corp-brand">{brand}</span>
          <span className="corp-footer-note">{site?.footer?.note ?? "唯讀市場情報平台 · 非投資建議"}</span>
        </div>
      </footer>
    </div>
  );
}
