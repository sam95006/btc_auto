"""CLI wrapper for performance report (implementation lives in backend)."""

from backend.analytics.performance_report import build_performance_report

__all__ = ["build_performance_report"]

if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from backend.services.runtime_store import runtime_store

    print(json.dumps(build_performance_report(runtime_store), ensure_ascii=False, indent=2))
