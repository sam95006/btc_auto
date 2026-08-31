import { Link } from "react-router-dom";
import { getHome } from "../api/client";
import { DataState } from "../components/DataState";
import { IntelligenceField } from "../components/IntelligenceField";
import { LiveMarket } from "../components/LiveMarket";
import { Scene } from "../components/Scene";
import { useResource } from "../hooks/useCorporate";
import type { ContentEnvelope, HomeContent, HomeScene } from "../types";

function Cta({ cta, primary }: { cta?: { label: string; to: string }; primary?: boolean }) {
  if (!cta) return null;
  return (
    <Link to={cta.to} className={primary ? "corp-btn" : "corp-btn-ghost"}>{cta.label}</Link>
  );
}

function SceneBlock({ s }: { s: HomeScene }) {
  // The live market showcase scene renders REAL backend data.
  const isShowcase = s.id === "showcase";
  return (
    <Scene id={s.id} className={`corp-scene-${s.id}`}>
      <div className="corp-scene-inner">
        {s.kicker ? <div className="corp-kicker">{s.kicker}</div> : null}
        <h2 className="corp-scene-title">{s.title}</h2>
        {s.subtitle ? <p className="corp-scene-sub">{s.subtitle}</p> : null}
        {s.body ? <p className="corp-scene-body">{s.body}</p> : null}
        {isShowcase ? <LiveMarket /> : null}
        <div className="corp-scene-cta">
          <Cta cta={s.primary_cta} primary />
          <Cta cta={s.cta} />
        </div>
      </div>
    </Scene>
  );
}

export function Home() {
  const state = useResource<ContentEnvelope<HomeContent>>(getHome, []);
  return (
    <div className="corp-home">
      <div className="corp-hero-field"><IntelligenceField /></div>
      <DataState state={state} label="首頁內容">
        {(env) => (
          <div className="corp-scenes">
            {(env.data?.scenes ?? []).map((s) => <SceneBlock key={s.id} s={s} />)}
          </div>
        )}
      </DataState>
    </div>
  );
}
