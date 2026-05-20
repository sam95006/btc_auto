"""Flags set when the NEXUS runtime is started inside the web process (Zeabur single-service)."""

embedded_worker_started = False
embedded_worker_error = None


def set_embedded_worker_status(started: bool, error: str | None = None):
    global embedded_worker_started, embedded_worker_error
    embedded_worker_started = bool(started)
    embedded_worker_error = error
