/**
 * NEXUS-EXPERIENCE-1B.1 — honest Starter-trial foundation.
 *
 * Backend-driven (GET /api/v1/personal/subscription). It renders ONLY truthful
 * states and never fabricates a countdown or an end date:
 *   - TRIAL (active): the real days-remaining and end date.
 *   - UNAVAILABLE: the generic Starter-trial OFFER from the backend contract
 *     (length + "no automatic charge"), with an explicit "status unavailable"
 *     note — never a fake countdown.
 *   - PAID / FREE / TRIAL_EXPIRED: nothing (no trial banner needed).
 */
import { useEffect, useState } from "react";
import { useExperience } from "../context/NexusExperience";
import { getPersonalSubscription, type PersonalSubscription } from "../services/stagingApi";

export function TrialBanner() {
  const { t } = useExperience();
  const [sub, setSub] = useState<PersonalSubscription | null | undefined>(undefined);

  useEffect(() => {
    let on = true;
    getPersonalSubscription()
      .then((s) => { if (on) setSub(s); })
      .catch(() => { if (on) setSub(null); });
    return () => { on = false; };
  }, []);

  // Silent while loading or on error — never guess a trial state.
  if (sub === undefined || sub === null) return null;

  const trial = sub.trial;
  if (trial.state === "PAID" || trial.state === "FREE" || trial.state === "TRIAL_EXPIRED") return null;

  const active = trial.state === "TRIAL" && trial.trial_active === true;
  const days = typeof trial.days_remaining === "number" ? trial.days_remaining : null;
  const ends = trial.trial_ends_at ? new Date(trial.trial_ends_at).toLocaleDateString() : null;

  if (active) {
    return (
      <div className="nx-trial" role="status" data-testid="nx-trial">
        <div className="nx-trial-head">
          <span className="nx-trial-title">{t("trial_title")}</span>
          {days != null ? <span className="nx-badge live">{t("trial_days_left").replace("%d", String(days))}</span> : null}
        </div>
        {ends ? <p className="nx-trial-line">{t("trial_ends")}: {ends}</p> : null}
        <p className="nx-trial-line meta">{t("trial_after")}</p>
        <p className="nx-trial-line no-charge">✓ {t("trial_no_charge")}</p>
      </div>
    );
  }

  // trial.state === "UNAVAILABLE": show the generic, truthful offer only.
  return (
    <div className="nx-trial" role="status" data-testid="nx-trial">
      <div className="nx-trial-head">
        <span className="nx-trial-title">{t("trial_offer")}</span>
        <span className="nx-badge">{`${sub.trial_contract.days} ${t("trial_days_unit")}`}</span>
      </div>
      <p className="nx-trial-line no-charge">✓ {t("trial_no_charge")}</p>
      <p className="nx-trial-line meta">{t("trial_unavailable")}</p>
    </div>
  );
}
