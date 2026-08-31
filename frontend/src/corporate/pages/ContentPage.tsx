import { getContent } from "../api/client";
import { DataState } from "../components/DataState";
import { Scene } from "../components/Scene";
import { useResource } from "../hooks/useCorporate";
import type { ContentEnvelope } from "../types";

/** Renders any backend CMS section by slug. All copy is backend-owned. */
export function ContentPage({ slug }: { slug: string }) {
  const state = useResource<ContentEnvelope>(() => getContent(slug), [slug]);
  return (
    <Scene className="corp-content-page">
      <div className="corp-scene-inner">
        <DataState state={state} label="內容">
          {(env) => {
            const d = (env.data ?? {}) as Record<string, any>;
            return (
              <>
                {d.title ? <h1 className="corp-page-title">{d.title}</h1> : null}
                {d.summary ? <p className="corp-scene-sub">{d.summary}</p> : null}
                {d.intro ? <p className="corp-scene-sub">{d.intro}</p> : null}
                {d.vision ? <p className="corp-scene-sub">{d.vision}</p> : null}
                {d.body ? <p className="corp-scene-body">{d.body}</p> : null}
                {d.note ? <p className="corp-provenance">{d.note}</p> : null}
                {Array.isArray(d.features) ? (
                  <ul className="corp-list">{d.features.map((f: string, i: number) => <li key={i}>{f}</li>)}</ul>
                ) : null}
                {Array.isArray(d.items) ? (
                  <div className="corp-cards">
                    {d.items.map((it: any) => (
                      <a className="corp-card" key={it.key || it.title} href={it.to}>
                        <h3>{it.title}</h3><p>{it.summary}</p>
                      </a>
                    ))}
                  </div>
                ) : null}
                {Array.isArray(d.tiers) ? (
                  <div className="corp-cards">
                    {d.tiers.map((t: any) => (
                      <div className="corp-card" key={t.code}>
                        <h3>{t.name}</h3>
                        <div className="corp-price" data-testid={`price-${t.code}`}>{t.price_display}<span>/{t.period}</span></div>
                        <ul className="corp-list">{(t.features || []).map((f: string, i: number) => <li key={i}>{f}</li>)}</ul>
                      </div>
                    ))}
                  </div>
                ) : null}
                {Array.isArray(d.points) ? (
                  <div className="corp-cards">
                    {d.points.map((p: any, i: number) => (
                      <div className="corp-card" key={i}><h3>{p.title}</h3><p>{p.body}</p></div>
                    ))}
                  </div>
                ) : null}
                {d.cta ? <a className="corp-btn" href={d.cta.href || d.cta.to}>{d.cta.label}</a> : null}
              </>
            );
          }}
        </DataState>
      </div>
    </Scene>
  );
}
