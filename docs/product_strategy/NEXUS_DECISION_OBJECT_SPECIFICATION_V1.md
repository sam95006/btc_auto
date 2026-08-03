# NEXUS Decision Object Specification V1

Product specification only. Do not implement the database in this track.

## Atomic object

**Decision Object** — the durable unit of Decision Integrity.

## Core parts

### Context Snapshot
Point-in-time market/context package: symbols, regime labels (if any), data freshness, source list, uncertainty notes.

### Thesis
Falsifiable statement of belief, horizon, catalysts, and what would change the mind.

### Evidence
Cited items with source, timestamp, freshness, supporting vs contradicting polarity. Invention forbidden at product policy level.

### Decision
Chosen action posture (e.g., initiate / hold / reduce / stand aside). Public product records intent; it does **not** place exchange orders.

### Risk and Invalidation
Invalidation conditions, risk notes, max loss framing, time stops as user-defined rules — advisory, user-owned.

### Human and AI Record
Separate human rationale and AI challenge/assist traces with model/provider metadata (sanitized). Dual calibration inputs.

### Outcome
Observed result fields after user-confirmed outcome entry (or read-only linked public marks). No private account ingestion required.

### Review
Process-vs-outcome review, calibration notes, lessons that stay in the **public** Decision Graph (never private Founder Lesson Memory).

## Versioning

- Schema version on every Decision Object
- Immutable event log; edits create new versions
- Soft delete / withdrawal via correction events, not silent mutation

## Permissions

- Owner user
- Optional shared read for Concierge facilitators
- No Founder Private Core access from public tenants

## Relations

- Thesis ↔ Evidence many-to-many
- Decision ↔ Risk/Invalidation 1-to-many
- Decision ↔ Outcome 1-to-0..1 (then Review)
- Decision Graph edges for supersession and related theses

## Replay

Decision Time Machine can reconstruct Context + Evidence + Decision + AI/Human records as of event versions.

## Append-only events

`context_recorded`, `thesis_updated`, `evidence_added`, `decision_committed`, `invalidation_triggered`, `outcome_recorded`, `review_completed`, `correction_issued`
