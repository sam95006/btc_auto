import { Link } from "react-router-dom";
import {
  artifactHref,
  findArtifact,
  type PrivateReportMeta,
} from "../demo/reportIndex";

/** Related report / runbook / checkpoint links for an artifact (docs only). */
export function RelatedArtifactLinks({
  artifact,
  stages,
  label = "Related artifacts",
}: {
  artifact?: PrivateReportMeta;
  stages?: string[];
  label?: string;
}) {
  const relatedStages =
    stages ??
    (artifact
      ? [
          ...artifact.relatedReports,
          ...artifact.relatedRunbooks,
          artifact.relatedCheckpoint,
        ].filter(Boolean)
      : []);
  const uniq = [...new Set(relatedStages)];
  if (uniq.length === 0) return null;

  return (
    <div className="related-links" aria-label={label}>
      <div className="related-links-label">{label}</div>
      <div className="related-links-row">
        {uniq.map((stage) => {
          const meta = findArtifact(stage);
          const page = meta?.uiTargetPage ?? "/evidence";
          return (
            <Link key={stage} className="deep-link chip-link" to={artifactHref(stage, page)}>
              {stage.replace("4.18-", "")}
            </Link>
          );
        })}
      </div>
      {artifact?.relatedCheckpoint ? (
        <p className="muted" style={{ marginTop: "0.35rem", marginBottom: 0 }}>
          Checkpoint:{" "}
          <Link
            className="deep-link"
            to={artifactHref(artifact.relatedCheckpoint, "/evidence")}
          >
            {artifact.relatedCheckpoint}
          </Link>
          {artifact.nextActionAnchor ? (
            <>
              {" "}
              · next anchor:{" "}
              <Link className="deep-link" to={`/evidence#${artifact.nextActionAnchor}`}>
                {artifact.nextActionAnchor}
              </Link>
            </>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
