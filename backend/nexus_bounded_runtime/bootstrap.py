"""Install certified bounded runtime wiring at process startup."""
from __future__ import annotations


def install_certified_bounded_runtime() -> None:
    import backend.nexus_demo_execution.bounded_6h_session as bounded_6h_module
    from backend.nexus_bounded_runtime.certified_session import CertifiedBounded6HSession

    bounded_6h_module.Bounded6HSession = CertifiedBounded6HSession
