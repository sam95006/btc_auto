import { CANDIDATE_ROWS } from "../demo/marketIntelligence";
import { DemoDataBadge } from "./DemoDataBadge";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

/** Candidate table — trading-platform density, read-only nav only (MVP-17). */
export function CandidateBoard() {
  const longRows = CANDIDATE_ROWS.filter((r) => r.bucket === "long");
  const shortRows = CANDIDATE_ROWS.filter((r) => r.bucket === "short");
  const waiting = CANDIDATE_ROWS.filter((r) => r.bucket === "waiting");

  const sections: { title: string; rows: typeof CANDIDATE_ROWS; empty: string }[] = [
    { title: "Long Candidates", rows: longRows, empty: "None under HOLD (sanitized)" },
    { title: "Short Candidates", rows: shortRows, empty: "None under HOLD (sanitized)" },
    { title: "Waiting / Blocked", rows: waiting, empty: "—" },
  ];

  return (
    <section id="candidate-board" className="operator-section">
      <div className="meta-row" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
        <h2 className="section-title" style={{ margin: 0 }}>
          Candidate Board
        </h2>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <span className="demo-badge">READ ONLY</span>
        <DemoDataBadge />
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        No Buy / Sell / Quick Order · next actions are View Evidence / Open Risk Card / Ask AI / View
        Gate only · NOT INVESTMENT ADVICE
      </p>

      {sections.map((sec) => (
        <div key={sec.title} className="candidate-section">
          <h3 className="dense-subtitle">{sec.title}</h3>
          <div className="table-scroll">
            <table className="intel-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Direction</th>
                  <th>Confidence</th>
                  <th>MAE risk</th>
                  <th>Entry trigger</th>
                  <th>Invalidation</th>
                  <th>Gate</th>
                  <th>Evidence</th>
                  <th>Next action</th>
                </tr>
              </thead>
              <tbody>
                {sec.rows.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="muted">
                      {sec.empty}
                    </td>
                  </tr>
                ) : (
                  sec.rows.map((r) => (
                    <tr key={r.id}>
                      <td className="mono">{r.symbol}</td>
                      <td>{r.direction}</td>
                      <td className="mono">{r.confidence ?? "—"}</td>
                      <td>{r.maeRisk}</td>
                      <td>{r.entryTrigger}</td>
                      <td>{r.invalidation}</td>
                      <td>
                        <StatusBadge tone={r.gateStatus === "WAIT" ? "wait" : "hold"}>
                          {r.gateStatus}
                        </StatusBadge>
                      </td>
                      <td className="muted">{r.evidenceNote}</td>
                      <td>
                        <ReadOnlyNavChip label={r.nextAction} />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}
