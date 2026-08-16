# nexus-api-staging — product API only (no ResearchAutonomyService / Shadow runtime).
# Build context: repository root (btc_bot).
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    NEXUS_ENV=STAGING \
    EXCHANGE_WRITE=false \
    MAINNET=false \
    REAL_MONEY=false \
    NEXUS_MEMBER_EXECUTION=false \
    NEXUS_PRODUCTION_BILLING=false \
    NEXUS_WEB_ONLY=true \
    NEXUS_EMBEDDED_WORKER=false \
    NEXUS_ZEABUR_AUTONOMY_DEPLOYED=false \
    NEXUS_RUNTIME_BINDING=UNAVAILABLE \
    NEXUS_PG_RUNTIME_ENABLED=true \
    NEXUS_PG_EVIDENCE_MIRROR_ENABLED=false

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api_staging_app.py gunicorn.conf.py ./
COPY backend/ backend/
COPY config/ config/
COPY static/ static/
COPY templates/ templates/
COPY deploy/zeabur_api_staging/start.sh deploy/zeabur_api_staging/start.sh
RUN chmod +x deploy/zeabur_api_staging/start.sh

EXPOSE 8080
CMD ["sh", "deploy/zeabur_api_staging/start.sh"]
