import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { AuthRequiredBlocker } from "./AuthRequiredBlocker";
import {
  completeOnboardingStep,
  dismissOnboarding,
  fetchOnboarding,
  isAuthRequired,
} from "./retentionApi";

type Step = { id: string; title: string; href: string; done?: boolean };

/** Max 3 steps: Market State / Live Radar / Watchlist+Alerts. */
export function OnboardingWizard() {
  const [authRequired, setAuthRequired] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [complete, setComplete] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const { res, body } = await fetchOnboarding();
        if (!alive) return;
        if (res.status === 401 || isAuthRequired(body)) {
          setAuthRequired(true);
          setComplete(true);
          return;
        }
        setSteps((body.steps as Step[]) || []);
        setComplete(Boolean(body.complete));
      } catch {
        if (alive) setComplete(true);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (loading || complete) return null;
  if (authRequired) {
    return (
      <div style={{ marginBottom: 16 }} data-testid="onboarding-auth-gate">
        <AuthRequiredBlocker
          title="Onboarding 需要登入"
          detail="三步驟導覽（Market State / Live Radar / Watchlist+Alerts）僅在真實工作階段下保存進度。"
        />
      </div>
    );
  }

  return (
    <section className="mp2-onboarding" data-testid="paid-beta-onboarding" aria-label="Onboarding">
      <header>
        <h2 className="mp2-page-title" style={{ fontSize: "1.05rem" }}>
          開始使用（最多 3 步）
        </h2>
        <p className="mp2-page-sub">Market State → Live Radar → Watchlist + Alerts</p>
      </header>
      <ol className="mp2-onboard-steps">
        {steps.slice(0, 3).map((s) => (
          <li key={s.id} className={s.done ? "done" : undefined}>
            <Link to={s.href}>{s.title}</Link>
            {!s.done ? (
              <button
                type="button"
                className="mp2-btn mp2-btn-ghost"
                style={{ padding: "2px 8px", marginLeft: 8 }}
                onClick={() =>
                  void completeOnboardingStep(s.id).then(({ body }) => {
                    setSteps((body.steps as Step[]) || steps);
                    setComplete(Boolean(body.complete));
                  })
                }
              >
                完成
              </button>
            ) : (
              <span className="muted" style={{ marginLeft: 8 }}>
                ✓
              </span>
            )}
          </li>
        ))}
      </ol>
      <button
        type="button"
        className="mp2-btn mp2-btn-ghost"
        onClick={() =>
          void dismissOnboarding().then(() => {
            setComplete(true);
          })
        }
      >
        略過
      </button>
    </section>
  );
}
