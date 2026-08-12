"""6H V2 evidence export schema — no secrets."""
from __future__ import annotations

EVIDENCE_FILES = (
    "session_summary.json",
    "runtime_identity.json",
    "account_snapshots.jsonl",
    "market_cycles.jsonl",
    "universe_scans.jsonl",
    "candidates.jsonl",
    "geometry_results.jsonl",
    "role_reviews.jsonl",
    "risk_critic.jsonl",
    "mistake_guard.jsonl",
    "portfolio_verdicts.jsonl",
    "cost_gates.jsonl",
    "order_intents.jsonl",
    "orders.jsonl",
    "fills.jsonl",
    "positions.jsonl",
    "protection_events.jsonl",
    "supervisor_cycles.jsonl",
    "exits.jsonl",
    "outcomes.jsonl",
    "process_quality.jsonl",
    "reflections.jsonl",
    "counterfactuals.jsonl",
    "learning_proposals.jsonl",
    "similar_case_matches.jsonl",
    "decision_deltas.jsonl",
    "worker_health.jsonl",
    "reconciliation.jsonl",
    "evidence_manifest.json",
)

FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "apisecret",
        "authorization",
        "signature",
        "zeabur_token",
        "password",
        "private_key",
    }
)


def evidence_manifest(*, session_id: str, policy_version: str, dry_run: bool) -> dict:
    return {
        "schema": "demo_6h_v2_evidence_manifest_v1",
        "session_id": session_id,
        "policy_version": policy_version,
        "dry_run": dry_run,
        "files": list(EVIDENCE_FILES),
        "forbidden_secret_keys": sorted(FORBIDDEN_SECRET_KEYS),
        "exchange_write": False,
    }


def contains_forbidden_secrets(payload: dict) -> list[str]:
    hits: list[str] = []

    def walk(obj, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower()
                p = f"{path}.{k}" if path else str(k)
                if key in FORBIDDEN_SECRET_KEYS or any(s in key for s in ("api_key", "api_secret", "authorization")):
                    hits.append(p)
                walk(v, p)
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:50]):
                walk(v, f"{path}[{i}]")

    walk(payload)
    return hits
