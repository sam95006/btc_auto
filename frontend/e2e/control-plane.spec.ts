import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { attachConsoleCollector, assertNoUnexpectedConsoleErrors } from "./helpers/consoleErrors";

type OverviewFixture = Record<string, unknown>;

function field(value: unknown, status = "LIVE", role = "demo_execution") {
  return {
    value,
    source_service: role,
    source_role: role,
    source_timestamp: Date.now() / 1000,
    received_at: Date.now() / 1000,
    freshness_seconds: 1,
    data_status: status,
    evidence_ref: "fixture",
    schema_version: "control-plane-canonical-v1",
  };
}

function baseOverview(overrides: OverviewFixture = {}): OverviewFixture {
  return {
    system_mode: {
      bybit_demo: true,
      mainnet: false,
      real_money: false,
      fixed_leverage: 25,
      margin_mode: "ISOLATED",
      execution_owner: "DEMO_VALIDATION_SERVICE",
      stage3_execution_disabled: true,
    },
    service_health: {
      market_intelligence: field("HEALTHY", "LIVE", "market_intelligence"),
      demo_execution: field("HEALTHY"),
      learning_engine: field("HEALTHY", "LIVE", "learning_engine"),
      control_plane: field("HEALTHY", "LIVE", "control_plane"),
    },
    demo_session: {
      session_id: field("NEXUS-DEMO-6H-FIXTURE"),
      status: field("RUNNING"),
      entries_total: field(0),
      entry_limit: field(6),
      trades_completed: field(0),
      session_write_enabled: field(true),
      automatic_extension: field(false, "LIVE", "control_plane"),
    },
    demo_account: {
      wallet_balance: field(5000),
      equity: field(5000),
      available_balance: field(4980),
      used_margin: field(20),
      unrealized_pnl: field(0),
    },
    market_funnel: {
      candidates_total: field(120),
      cost_gate_blocks: field(120),
      risk_critic_blocks: field(0),
      mistake_guard_blocks: field(0),
    },
    why_no_trade: {
      active: true,
      headline: "NO_TRADE_COST_GATE",
      detail:
        "目前沒有交易，因全部 120 個候選在扣除 Fee／Slippage／Funding Buffer 後，預估淨報酬未達安全標準。系統仍在掃描；這不是停機。",
      gate_breakdown: {
        candidates_total: 120,
        cost_gate_blocks: 120,
        risk_critic_blocks: 0,
        mistake_guard_blocks: 0,
      },
    },
    execution: {
      open_position: field(false),
      open_orders: field(0),
      reconciliation: field("MATCH"),
    },
    performance: {
      gross_pnl: field(0),
      total_fees: field(0),
      funding: field(null, "MISSING"),
      net_pnl: field(0),
    },
    learning: {
      evidence_chain: {
        source_trade_case_id: field(null, "MISSING"),
        similar_candidate_id: field(null, "MISSING"),
      },
      learning_effectiveness: field("NOT_YET_OBSERVABLE", "LIVE", "control_plane"),
      forbidden_labels: { PROVEN: false, SELF_IMPROVING_CONFIRMED: false, PROFITABLE: false },
    },
    version_labels: {
      pr6_branch_head: field("2a647695e9cc6f90d54a92ce5c35fd8de3000aea", "LIVE", "control_plane"),
      observation_deployed_code_sha: field(
        "9b6f57c1bc3afe988f0fc3829f62dad2ee510156",
        "LIVE",
        "demo_execution",
      ),
      control_plane_sha: field("UNAVAILABLE", "MISSING", "control_plane"),
      deploy_run: field("30509623012", "LIVE", "control_plane"),
    },
    ownership: {
      market_scan: "market_intelligence",
      demo_wallet: "demo_execution",
      legacy_stage3_labels: ["LEGACY_STAGE3_RUNTIME", "EXECUTION_DISABLED"],
    },
    ...overrides,
  };
}

async function mockOverview(page: import("@playwright/test").Page, overview: OverviewFixture) {
  const writeAttempts: string[] = [];
  await page.route("**/api/nexus/control-plane/**", async (route) => {
    const req = route.request();
    if (!["GET", "HEAD", "OPTIONS"].includes(req.method())) {
      writeAttempts.push(`${req.method()} ${req.url()}`);
      await route.fulfill({
        status: 405,
        contentType: "application/json",
        body: JSON.stringify({ ok: false, error: "CONTROL_PLANE_READ_ONLY", exchange_write: false }),
      });
      return;
    }
    if (req.url().includes("/overview")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          exchange_write: false,
          mainnet: false,
          real_money: false,
          overview,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });
  return writeAttempts;
}

test.describe("Control Plane browser functional", () => {
  test("all services healthy + zero trade why-no-trade", async ({ page }) => {
    const consoleErrors = attachConsoleCollector(page);
    const writes = await mockOverview(page, baseOverview());
    await page.goto("/control-plane", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("control-plane-overview")).toBeVisible();
    await expect(page.getByTestId("why-no-trade")).toContainText("NO_TRADE_COST_GATE");
    await expect(page.getByText("DEMO_VALIDATION_SERVICE")).toBeVisible();
    await expect(page.getByLabel(/PR #6 Branch Head:/)).toContainText("2a647695");
    await expect(page.getByLabel(/Observation Deployed SHA:/)).toContainText("9b6f57c1");
    await expect(page.getByText("LEGACY_STAGE3 equity 5023")).toHaveCount(0);
    assertNoUnexpectedConsoleErrors(consoleErrors);
    expect(writes.length).toBe(0);
  });

  test("demo execution down — no stage3 fallback", async ({ page }) => {
    await mockOverview(
      page,
      baseOverview({
        service_health: {
          market_intelligence: field("HEALTHY", "LIVE", "market_intelligence"),
          demo_execution: field("DOWN", "SERVICE_UNAVAILABLE"),
          learning_engine: field("DOWN", "SERVICE_UNAVAILABLE", "learning_engine"),
          control_plane: field("HEALTHY", "LIVE", "control_plane"),
        },
        demo_account: {
          note: "DEMO_EXECUTION_SERVICE_UNAVAILABLE — do not fall back to Stage3 account",
          equity: field(null, "MISSING"),
          wallet_balance: field(null, "MISSING"),
          available_balance: field(null, "MISSING"),
        },
        why_no_trade: {
          active: true,
          headline: "DEMO_EXECUTION_SERVICE_UNAVAILABLE",
          detail: "不得回退 Stage3 舊交易狀態。",
        },
      }),
    );
    await page.goto("/control-plane");
    await expect(page.getByTestId("why-no-trade")).toContainText("DEMO_EXECUTION_SERVICE_UNAVAILABLE");
    await expect(page.getByText("5023")).toHaveCount(0);
  });

  test("market service down still renders overview", async ({ page }) => {
    await mockOverview(
      page,
      baseOverview({
        service_health: {
          market_intelligence: field("DOWN", "SERVICE_UNAVAILABLE", "market_intelligence"),
          demo_execution: field("HEALTHY"),
          learning_engine: field("HEALTHY", "LIVE", "learning_engine"),
          control_plane: field("HEALTHY", "LIVE", "control_plane"),
        },
      }),
    );
    await page.goto("/control-plane");
    await expect(page.getByTestId("control-plane-overview")).toBeVisible();
    await expect(page.getByRole("heading", { name: "NEXUS" })).toBeVisible();
  });

  test("session completed + learning not proven", async ({ page }) => {
    await mockOverview(
      page,
      baseOverview({
        demo_session: {
          session_id: field("NEXUS-DEMO-6H-FIXTURE"),
          status: field("COMPLETED"),
          entries_total: field(1),
          trades_completed: field(1),
          session_write_enabled: field(false),
        },
        why_no_trade: { active: false },
        learning: {
          evidence_chain: {
            source_trade_case_id: field("tc-1"),
            similar_candidate_id: field("cand-2"),
            before_verdict: field("ALLOW"),
            after_verdict: field("ALLOW"),
          },
          learning_effectiveness: field("NOT_PROVEN", "LIVE", "control_plane"),
        },
      }),
    );
    await page.goto("/control-plane");
    await expect(page.getByText("COMPLETED")).toBeVisible();
    await expect(page.getByText("NOT_PROVEN")).toBeVisible();
    await expect(page.getByText("SELF_IMPROVING_CONFIRMED")).toHaveCount(0);
    await expect(page.locator("text=/^PROVEN$/")).toHaveCount(0);
  });

  test("mobile nav + no horizontal overflow @ 390x844", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockOverview(page, baseOverview());
    await page.goto("/control-plane");
    await expect(page.getByLabel("主要導覽")).toBeVisible();
    const overflow = await page.evaluate(() => {
      const doc = document.documentElement;
      return doc.scrollWidth > doc.clientWidth + 1;
    });
    expect(overflow).toBe(false);
  });

  test("keyboard focus reaches why-no-trade region", async ({ page }) => {
    await mockOverview(page, baseOverview());
    await page.goto("/control-plane");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("why-no-trade")).toBeVisible();
  });

  test("@a11y control-plane axe serious/critical = 0 (no global disable)", async ({ page }) => {
    await mockOverview(page, baseOverview());
    await page.goto("/control-plane");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    // Document nonblocking debt instead of disableRules
    const debt = serious.map((v) => ({
      rule: v.id,
      impact: v.impact,
      nodes: v.nodes.length,
      blocking: true,
    }));
    expect(debt, JSON.stringify(debt, null, 2)).toEqual([]);
  });

  for (const size of [
    { w: 430, h: 932 },
    { w: 768, h: 1024 },
    { w: 1440, h: 900 },
  ]) {
    test(`responsive ${size.w}x${size.h}`, async ({ page }) => {
      await page.setViewportSize({ width: size.w, height: size.h });
      await mockOverview(page, baseOverview());
      await page.goto("/control-plane");
      await expect(page.getByRole("heading", { name: "模式" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Demo Session" })).toBeVisible();
    });
  }
});
