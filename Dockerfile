# NEXUS V18.2.30.1 Unified Zeabur Runtime
# ONE service: Web (Gunicorn) + ResearchAutonomyService (24/7)
# Canonical deploy path for nexus-member-preview-v18-2-1
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NEXUS_RUNTIME_LOCATION=ZEABUR \
    NEXUS_DATA_ROOT=/data \
    NEXUS_CAMPAIGN_ROOT=/data/campaigns/research_v18_2_30 \
    NEXUS_EVIDENCE_COORDINATOR=/data/evidence_coordinator \
    NEXUS_ZEABUR_AUTONOMY_DEPLOYED=true \
    NEXUS_WEB_ONLY=true \
    NEXUS_EMBEDDED_WORKER=false \
    NEXUS_LEGACY_WORKER_DISABLED=true \
    NEXUS_AUTONOMOUS_DEMO_AUTO_SEND=false \
    EXCHANGE_WRITE=true \
    MAINNET=false \
    REAL_MONEY=false \
    PORT=8080

WORKDIR /app

RUN set -eux; \
    if [ -f /etc/dpkg/dpkg.cfg.d/docker ]; then \
      sed -i '/^path-exclude/s!^path-exclude /usr/share/man!path-include /usr/share/man!' /etc/dpkg/dpkg.cfg.d/docker; \
    fi; \
    mkdir -p /usr/share/man/man1; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN test -f static/nexus/assets/nexus_overview.png \
 && test -f static/nexus/assets/hq_roundtable.png \
 || (echo "MISSING console assets in build context"; ls -la static/nexus/assets || true; exit 1)

RUN test -f deploy/zeabur_unified/start.sh \
 && test -f backend/nexus_research_ai_autonomy/research_autonomy_service.py \
 || (echo "MISSING unified autonomy runtime"; exit 1)

RUN chmod +x deploy/zeabur_unified/start.sh \
 && mkdir -p \
      /data/campaigns/research_v18_2_30/autonomy \
      /data/campaigns/research_v18_2_30/checkpoints \
      /data/evidence_coordinator \
      /data/autonomy/locks \
      /tmp/nexus_demo_validation

EXPOSE 8080

# Unified supervisor — NOT bare gunicorn, NOT Dockerfile.autonomy alone.
CMD ["sh", "deploy/zeabur_unified/start.sh"]
