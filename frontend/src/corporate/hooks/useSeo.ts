/**
 * Client-side SEO for the SPA. Sets per-page <title>, meta description,
 * OpenGraph/Twitter tags, canonical, and JSON-LD. Business-content SEO values
 * come from the backend CMS `seo` section (never fabricated); page-specific
 * overrides are passed in. Essential text also lives in the DOM (headings/
 * copy), never only inside canvas.
 */
import { useEffect } from "react";

type SeoInput = {
  title?: string;
  description?: string;
  path?: string;
  ogType?: string;
  robots?: string;
  jsonLd?: Record<string, unknown> | null;
};

function upsertMeta(selector: string, attr: "name" | "property", key: string, content: string) {
  if (!content) return;
  let el = document.head.querySelector<HTMLMetaElement>(selector);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertLink(rel: string, href: string) {
  if (!href) return;
  let el = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

export function useSeo(input: SeoInput) {
  const { title, description, path, ogType = "website", robots, jsonLd } = input;
  useEffect(() => {
    if (title) document.title = title;
    if (description) {
      upsertMeta('meta[name="description"]', "name", "description", description);
      upsertMeta('meta[property="og:description"]', "property", "og:description", description);
      upsertMeta('meta[name="twitter:description"]', "name", "twitter:description", description);
    }
    if (title) {
      upsertMeta('meta[property="og:title"]', "property", "og:title", title);
      upsertMeta('meta[name="twitter:title"]', "name", "twitter:title", title);
    }
    upsertMeta('meta[property="og:type"]', "property", "og:type", ogType);
    upsertMeta('meta[name="twitter:card"]', "name", "twitter:card", "summary_large_image");
    if (robots) upsertMeta('meta[name="robots"]', "name", "robots", robots);

    const origin = typeof location !== "undefined" ? location.origin : "";
    const url = origin + (path ?? (typeof location !== "undefined" ? location.pathname : "/"));
    upsertLink("canonical", url);
    upsertMeta('meta[property="og:url"]', "property", "og:url", url);

    // JSON-LD structured data (managed node — replaced per page).
    let script = document.getElementById("corp-jsonld") as HTMLScriptElement | null;
    if (jsonLd) {
      if (!script) {
        script = document.createElement("script");
        script.type = "application/ld+json";
        script.id = "corp-jsonld";
        document.head.appendChild(script);
      }
      script.textContent = JSON.stringify(jsonLd);
    } else if (script) {
      script.remove();
    }
  }, [title, description, path, ogType, robots, jsonLd]);
}
