# DEPRECATED as Zeabur canonical path (V18.2.30.1 unified migration)

Founder decision: ONE Zeabur service (`nexus-member-preview-v18-2-1`).

Canonical deploy:
- Root `Dockerfile` → `deploy/zeabur_unified/start.sh`
- Web (Gunicorn) + ResearchAutonomyService in one container

This file remains in git history for reference only.
Do NOT configure Zeabur to build `Dockerfile.autonomy`.
