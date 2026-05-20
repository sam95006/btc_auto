"""
Zeabur / Gunicorn entrypoint.

Zeabur auto-detects app.py or main.py (not run.py). This module re-exports the
Flask application built in run.py so the platform can start the web service.
"""
import os

from run import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
