/**
 * First-screen Decision Integrity answers (functional baseline).
 * Answers: market state · best focus · largest risk · missing confirmation · when not to chase.
 * DEMO-bound only — never fabricates LIVE metrics.
 */

import {
  alerts,
  decisions,
  marketOverviewCards,
  thesisMonitors,
} from "./demoCatalog";
import type { PublicDecisionDetail, RiskCondition } from "./types";
import {
  displayValueForState,
  freshnessToUxState,
  type MemberUxState,
} from "./uxStates";

export type FirstScreenAnswer = {
  id:
    | "market_state"
    | "best_focus"
    | "largest_risk"
    | "missing_confirmation"
    | "when_not_to_chase";
  question: string;
  answer: string;
  detail: string;
  state: MemberUxState;
  href?: string;
};

export type FirstScreenModel = {
  answers: FirstScreenAnswer[];
  shellState: MemberUxState;
  dataMode: "DEMO";
  openDecisionCount: number;
  highRiskCount: number;
  pendingOutcomeCount: number;
  focusDecisionId: string | null;
  note: string;
};

export type FirstScreenInput = {
  decisions: Array<PublicDecisionDetail & { demo?: boolean }>;
  marketCards: typeof marketOverviewCards;
  alerts: typeof alerts;
  thesisMonitors: typeof thesisMonitors;
  /** Override shell presentation for state demos / loading / error. */
  forceShellState?: MemberUxState;
};

const SEV_RANK: Record<RiskCondition["severity"], number> = {
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
};

function standAsideOrHold(
  list: Array<PublicDecisionDetail>,
): PublicDecisionDetail | undefined {
  return (
    list.find((d) => d.posture === "STAND_ASIDE") ||
    list.find((d) => d.posture === "HOLD") ||
    list.find((d) => d.outcomeClass === "PENDING") ||
    list[0]
  );
}

function largestOpenRisk(
  list: Array<PublicDecisionDetail>,
): { risk: RiskCondition; decision: PublicDecisionDetail } | null {
  let best: { risk: RiskCondition; decision: PublicDecisionDetail } | null = null;
  for (const d of list) {
    for (const r of d.risks) {
      if (r.status !== "OPEN" && r.status !== "TRIGGERED") continue;
      if (
        !best ||
        SEV_RANK[r.severity] > SEV_RANK[best.risk.severity] ||
        (SEV_RANK[r.severity] === SEV_RANK[best.risk.severity] &&
          r.status === "TRIGGERED" &&
          best.risk.status !== "TRIGGERED")
      ) {
        best = { risk: r, decision: d };
      }
    }
  }
  return best;
}

function missingConfirmationText(d: PublicDecisionDetail | undefined): {
  answer: string;
  detail: string;
  state: MemberUxState;
} {
  if (!d) {
    return {
      answer: "No open Decision to confirm",
      detail: "Empty Decision scope · record Context → Thesis before chasing price.",
      state: "empty",
    };
  }
  const dualCal = /dual-calibration pending|pending/i.test(d.confidenceLabel);
  const counter = d.counterEvidenceCount > 0;
  const openRisks = d.risks.filter((r) => r.status === "OPEN").length;
  if (dualCal) {
    return {
      answer: "Dual-calibration still pending",
      detail: `${d.symbol} confidence label awaits second-pass confirmation · ${d.confidenceLabel}`,
      state: "pending",
    };
  }
  if (counter && d.posture !== "STAND_ASIDE") {
    return {
      answer: "Counter-evidence unresolved",
      detail: `${d.counterEvidenceCount} contradicting item(s) need explicit human disposition`,
      state: "pending",
    };
  }
  if (openRisks > 0) {
    return {
      answer: "Open invalidation not cleared",
      detail: `${openRisks} risk condition(s) still OPEN on ${d.symbol}`,
      state: "pending",
    };
  }
  if (d.freshness === "DEMO" || d.freshness === "STALE" || d.freshness === "DEGRADED") {
    return {
      answer: "Fresher public lineage confirmation",
      detail: `Decision freshness is ${d.freshness} · do not treat as LIVE confirmation`,
      state: freshnessToUxState(d.freshness),
    };
  }
  return {
    answer: "Thesis time-stop / review commitment",
    detail: "Confirm review window before escalating posture",
    state: "pending",
  };
}

function whenNotToChase(
  list: Array<PublicDecisionDetail>,
  highRiskCount: number,
  shell: MemberUxState,
): { answer: string; detail: string; state: MemberUxState } {
  if (shell === "loading") {
    return {
      answer: "Do not chase while loading",
      detail: "Hold judgment until first-screen state resolves",
      state: "loading",
    };
  }
  if (shell === "error" || shell === "unavailable") {
    return {
      answer: "Do not chase while data is unavailable",
      detail: "Missing confirmation beats price impulse · no fabricated fallback",
      state: shell,
    };
  }
  if (shell === "blocked") {
    return {
      answer: "Gate blocked — do not chase",
      detail: "Decision Integrity gate closed · observation only",
      state: "blocked",
    };
  }
  const aside = list.filter((d) => d.posture === "STAND_ASIDE");
  if (aside.length) {
    return {
      answer: `Do not chase ${aside.map((d) => d.symbol).join(", ")} initiative`,
      detail:
        "Stand-aside posture means missing confirmation outweighs momentum narratives",
      state: "blocked",
    };
  }
  if (highRiskCount > 0) {
    return {
      answer: "Do not chase high-severity open risks",
      detail: `${highRiskCount} HIGH risk condition(s) open · reduce impulse, raise evidence`,
      state: "blocked",
    };
  }
  if (!list.length) {
    return {
      answer: "Do not chase an empty book",
      detail: "No Decisions recorded · start with Market Observation, not price chase",
      state: "empty",
    };
  }
  return {
    answer: "Do not chase without Outcome Review discipline",
    detail: "If evidence freshness degrades or counter-evidence clusters, wait",
    state: "pending",
  };
}

export function buildFirstScreenModel(input: FirstScreenInput): FirstScreenModel {
  const list = input.decisions;
  const open = list.filter((d) => d.outcomeClass === "PENDING");
  const highRisks = list.flatMap((d) =>
    d.risks.filter((r) => r.severity === "HIGH" && r.status !== "CLEARED"),
  );
  const focus = standAsideOrHold(open.length ? open : list);
  const topRisk = largestOpenRisk(list);
  const confirm = missingConfirmationText(focus);

  const cardStates = input.marketCards.map((c) => freshnessToUxState(c.freshness));
  let shell: MemberUxState =
    input.forceShellState ||
    (list.length === 0
      ? "empty"
      : cardStates.includes("unavailable")
        ? "unavailable"
        : cardStates.every((s) => s === "fresh")
          ? "fresh"
          : cardStates.includes("stale")
            ? "stale"
            : "degraded");

  // DEMO catalog is never presented as LIVE fresh.
  if (!input.forceShellState && list.some((d) => d.demo === true || d.freshness === "DEMO")) {
    if (shell === "fresh") shell = "degraded";
  }

  const chase = whenNotToChase(list, highRisks.length, shell);

  const marketAnswer = (() => {
    if (shell === "loading") {
      return {
        answer: "Loading market context…",
        detail: "First screen holds judgment until context arrives",
        state: "loading" as const,
      };
    }
    if (shell === "error") {
      return {
        answer: "Market context error",
        detail: "Context package failed · unavailable — not shown as zero",
        state: "error" as const,
      };
    }
    if (shell === "unavailable") {
      return {
        answer: displayValueForState("unavailable", null, "Unavailable"),
        detail: "No public context package · not fabricated",
        state: "unavailable" as const,
      };
    }
    if (!input.marketCards.length) {
      return {
        answer: "Empty market context",
        detail: "No overview cards bound",
        state: "empty" as const,
      };
    }
    const postures = Array.from(new Set(list.map((d) => d.posture)));
    const primary = input.marketCards[0];
    return {
      answer: `${primary.value} · postures ${postures.join("/") || "—"}`,
      detail: input.marketCards
        .slice(0, 3)
        .map((c) => `${c.label}: ${c.value}`)
        .join(" · "),
      state: shell,
    };
  })();

  const answers: FirstScreenAnswer[] = [
    {
      id: "market_state",
      question: "Market state",
      answer: marketAnswer.answer,
      detail: marketAnswer.detail,
      state: marketAnswer.state,
      href: "/market",
    },
    {
      id: "best_focus",
      question: "Best focus",
      answer: focus
        ? `${focus.symbol} · ${focus.posture} · ${focus.title}`
        : shell === "loading"
          ? "Resolving focus…"
          : "No focus Decision",
      detail: focus
        ? focus.thesis
        : "Empty or unavailable Decision scope — do not invent a chase target",
      state: focus ? freshnessToUxState(focus.freshness) : shell === "loading" ? "loading" : "empty",
      href: focus ? `/decisions/${focus.id}` : "/decisions",
    },
    {
      id: "largest_risk",
      question: "Largest risk",
      answer: topRisk
        ? `${topRisk.risk.severity} · ${topRisk.risk.label}`
        : highRisks.length === 0 && list.length
          ? "No open HIGH risk in scope"
          : "Risk package unavailable",
      detail: topRisk
        ? `${topRisk.decision.symbol}: ${topRisk.risk.note}`
        : "Empty risk list is not a green light to chase",
      state: topRisk
        ? topRisk.risk.severity === "HIGH"
          ? "blocked"
          : "pending"
        : list.length
          ? "empty"
          : shell,
      href: topRisk ? `/decisions/${topRisk.decision.id}` : "/risk-conditions",
    },
    {
      id: "missing_confirmation",
      question: "Missing confirmation",
      answer: confirm.answer,
      detail: confirm.detail,
      state: confirm.state,
      href: focus ? `/decisions/${focus.id}` : "/evidence",
    },
    {
      id: "when_not_to_chase",
      question: "When not to chase",
      answer: chase.answer,
      detail: chase.detail,
      state: chase.state,
      href: "/thesis-monitor",
    },
  ];

  return {
    answers,
    shellState: shell,
    dataMode: "DEMO",
    openDecisionCount: open.length,
    highRiskCount: highRisks.length,
    pendingOutcomeCount: list.filter((d) => d.outcomeClass === "PENDING").length,
    focusDecisionId: focus?.id ?? null,
    note: "DEMO DATA · READ ONLY · NOT INVESTMENT ADVICE · no exchange orders from this screen",
  };
}

export function buildDemoFirstScreen(
  forceShellState?: MemberUxState,
): FirstScreenModel {
  return buildFirstScreenModel({
    decisions,
    marketCards: marketOverviewCards,
    alerts,
    thesisMonitors,
    forceShellState,
  });
}

/** Deterministic fixtures for every required UX state (Pass 2 coverage). */
export function buildStateMatrixModels(): Record<MemberUxState, FirstScreenModel> {
  const base = {
    decisions,
    marketCards: marketOverviewCards,
    alerts,
    thesisMonitors,
  };
  return {
    fresh: buildFirstScreenModel({
      ...base,
      decisions: decisions.map((d) => ({ ...d, freshness: "FRESH", demo: true })),
      marketCards: marketOverviewCards.map((c) => ({ ...c, freshness: "FRESH" })),
      forceShellState: "fresh",
    }),
    stale: buildFirstScreenModel({ ...base, forceShellState: "stale" }),
    degraded: buildDemoFirstScreen("degraded"),
    pending: buildFirstScreenModel({ ...base, forceShellState: "pending" }),
    unavailable: buildFirstScreenModel({ ...base, forceShellState: "unavailable" }),
    blocked: buildFirstScreenModel({ ...base, forceShellState: "blocked" }),
    empty: buildFirstScreenModel({
      decisions: [],
      marketCards: [],
      alerts: [],
      thesisMonitors: [],
      forceShellState: "empty",
    }),
    error: buildFirstScreenModel({ ...base, forceShellState: "error" }),
    loading: buildFirstScreenModel({ ...base, forceShellState: "loading" }),
  };
}
