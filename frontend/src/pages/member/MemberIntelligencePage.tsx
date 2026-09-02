import { useEffect, useState } from "react";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import {
  IntelligenceExperiencePanel,
  IntelligenceStateChip,
  LIFECYCLE_STATES,
  type MemberIntelExperience,
} from "../../member/intel";

type FeedResponse = {
  ok?: boolean;
  experiences?: MemberIntelExperience[];
};

// NEXUS-EXPERIENCE-1B: no demo/fixture fallback. Real backend data or an honest
// COMING_SOON state (news/social intelligence is not yet licensed).
export function MemberIntelligencePage() {
  const [rows, setRows] = useState<MemberIntelExperience[]>([]);
  const [state, setState] = useState<"loading" | "api" | "unavailable">("loading");

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const res = await fetch("/api/public/member-intel/experiences", {
          headers: { Accept: "application/json" },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as FeedResponse;
        if (!alive) return;
        if (body.ok && Array.isArray(body.experiences) && body.experiences.length > 0) {
          setRows(body.experiences);
          setState("api");
        } else {
          setState("unavailable");
        }
      } catch {
        if (alive) setState("unavailable");
      }
    })();
    return () => { alive = false; };
  }, []);

  return (
    <MemberPageChrome titleKey="pages.intel.title" subtitleKey="pages.intel.subtitle">
      <div className="member-intel-page" data-testid="member-intel-page" data-source={state}>
        <section className="member-panel" aria-label="Lifecycle state matrix">
          <h2 className="nx-sec-title">Lifecycle states</h2>
          <ul className="member-intel-state-matrix" data-testid="member-intel-state-matrix">
            {LIFECYCLE_STATES.map((s) => (
              <li key={s}><IntelligenceStateChip state={s} showHint /></li>
            ))}
          </ul>
        </section>

        {state === "api" && rows.length ? (
          <section className="member-intel-feed" aria-label="Intelligence experiences">
            {rows.map((exp) => <IntelligenceExperiencePanel key={exp.case_id} experience={exp} />)}
          </section>
        ) : (
          <section className="member-panel" data-testid="member-intel-unavailable">
            <h2 className="nx-sec-title">情報動態 / Intelligence feed</h2>
            <p className="muted">
              {state === "loading"
                ? "載入中… / loading…"
                : "新聞與社群情報即將推出（尚未取得授權資料）。COMING SOON — no licensed news/social data yet; nothing is fabricated."}
            </p>
          </section>
        )}
      </div>
    </MemberPageChrome>
  );
}
