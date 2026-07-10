import { DemoDataBadge } from "../components/DemoDataBadge";

export function CalculatorPage() {
  return (
    <div>
      <header className="page-header">
        <h1>Risk Calculator</h1>
        <DemoDataBadge />
        <p className="page-sub">
          Educational sizing stub. Does not place orders or change live risk limits.
        </p>
      </header>
      <div className="panel-card" style={{ maxWidth: 480 }}>
        <div className="flag-grid">
          <div className="flag-item">
            <div className="k">account size (demo)</div>
            <div className="v">10,000</div>
          </div>
          <div className="flag-item">
            <div className="k">max risk / trade</div>
            <div className="v">0.5%</div>
          </div>
          <div className="flag-item">
            <div className="k">max daily loss</div>
            <div className="v">1.5%</div>
          </div>
          <div className="flag-item">
            <div className="k">stop distance</div>
            <div className="v">1.2%</div>
          </div>
          <div className="flag-item">
            <div className="k">leverage warning</div>
            <div className="v">keep low</div>
          </div>
          <div className="flag-item">
            <div className="k">suggested size</div>
            <div className="v">observe only</div>
          </div>
        </div>
        <p className="muted" style={{ marginTop: "1rem" }}>
          Guidance: stop after 3 consecutive losses (educational). NOT INVESTMENT ADVICE.
        </p>
      </div>
    </div>
  );
}
