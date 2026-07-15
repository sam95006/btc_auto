import { CANDIDATE_ROWS } from "../demo/marketIntelligence";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

/** Candidate table — trading-dashboard density (MVP-20 visual polish). */
export function CandidateBoard() {
  const longRows = CANDIDATE_ROWS.filter((r) => r.bucket === "long");
  const shortRows = CANDIDATE_ROWS.filter((r) => r.bucket === "short");
  const waiting = CANDIDATE_ROWS.filter((r) => r.bucket === "waiting");

  const sections: { title: string; rows: typeof CANDIDATE_ROWS; empty: string }[] = [
    { title: "Long Candidates", rows: longRows, empty: "None under HOLD" },
    { title: "Short Candidates", rows: shortRows, empty: "None under HOLD" },
    { title: "Waiting / Blocked", rows: waiting, empty: "—" },
  ];

  return (
    <section id="candidate-board" className="operator-section board-section">
      <div className="section-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          Candidate Board
        </h2>
        <StatusBadge tone="hold">HOLD</StatusBadge>
      </div>
      <p className="muted section-lede">
        Evidence / Gate / Provider / Risk links only · no Buy / Sell / Quick Order
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
                  <th>Conf</th>
                  <th>MAE</th>
                  <th>Trigger</th>
                  <th>Invalidation</th>
                  <th>Gate</th>
                  <th>Note</th>
                  <th>Actions</th>
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
                      <td className="mono sym-cell">{r.symbol}</td>
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
                      <td className="muted note-cell">{r.evidenceNote}</td>
                      <td>
                        <div className="ro-nav-row">
                          <ReadOnlyNavChip label="Evidence" to={r.links.evidence} />
                          <ReadOnlyNavChip label="Gate" to={r.links.gate} />
                          <ReadOnlyNavChip label="Provider" to={r.links.provider} />
                          <ReadOnlyNavChip label="Risk" to={r.links.risk} />
                        </div>
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
