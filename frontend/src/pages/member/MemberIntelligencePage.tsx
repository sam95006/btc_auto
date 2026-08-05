import { useEffect, useState } from "react";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import {
  IntelligenceExperiencePanel,
  IntelligenceStateChip,
  LIFECYCLE_STATES,
  MEMBER_INTEL_FIXTURES,
  type MemberIntelExperience,
} from "../../member/intel";

type FeedResponse = {
  ok?: boolean;
  experiences?: MemberIntelExperience[];
};

export function MemberIntelligencePage() {
  const [rows, setRows] = useState<MemberIntelExperience[]>(MEMBER_INTEL_FIXTURES);
  const [source, setSource] = useState<"api" | "fixture">("fixture");
  const [error, setError] = useState<string | null>(null);

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
          setSource("api");
          setError(null);
        }
      } catch (err) {
        if (!alive) return;
        setSource("fixture");
        setError(err instanceof Error ? err.message : "api_unavailable");
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  return (
    <MemberPageChrome
      titleKey="pages.intel.title"
      subtitleKey="pages.intel.subtitle"
      chromeMode={source === "api" ? "DEMO_DATA" : "DEMO_DATA"}
    >
      <div className="member-intel-page" data-testid="member-intel-page" data-source={source}>
        <p className="muted sm">
          Source: <strong>{source === "api" ? "API" : "DEMO_DATA fixture fallback"}</strong>
          {error ? ` · API note: ${error}` : null}
          {" · "}Fixtures never labeled LIVE · AI suggestion ≠ filled order · no 60% guarantee
        </p>

        <section className="member-panel" aria-label="Lifecycle state matrix">
          <h2 className="nx-sec-title">Lifecycle states</h2>
          <ul className="member-intel-state-matrix" data-testid="member-intel-state-matrix">
            {LIFECYCLE_STATES.map((s) => (
              <li key={s}>
                <IntelligenceStateChip state={s} showHint />
              </li>
            ))}
          </ul>
        </section>

        <section className="member-intel-feed" aria-label="Intelligence experiences">
          {rows.map((exp) => (
            <IntelligenceExperiencePanel key={exp.case_id} experience={exp} />
          ))}
        </section>
      </div>
    </MemberPageChrome>
  );
}
