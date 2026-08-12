# Zeabur service: nexus-autonomy-worker
# In Zeabur UI: set Dockerfile path to Dockerfile.autonomy (or this package's Dockerfile)
# Mount persistent volume at /data
# Start command (if overriding):
#   python -m backend.nexus_research_ai_autonomy.research_autonomy_service --run --campaign-root /data/campaigns/research_v18_2_30 --cycle-sleep-sec 120

FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NEXUS_RUNTIME_LOCATION=ZEABUR \
    NEXUS_DATA_ROOT=/data \
    NEXUS_CAMPAIGN_ROOT=/data/campaigns/research_v18_2_30 \
    EXCHANGE_WRITE=true \
    MAINNET=false \
    REAL_MONEY=false \
    NEXUS_RESEARCH_AUTONOMY=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build context = repo root (phase_cd_campaign). Copy full tree for backend + tools.
COPY . .

RUN mkdir -p /data/campaigns/research_v18_2_30/autonomy \
             /data/campaigns/research_v18_2_30/checkpoints \
             /data/autonomy/locks

CMD ["python", "-m", "backend.nexus_research_ai_autonomy.research_autonomy_service", \
     "--run", \
     "--campaign-root", "/data/campaigns/research_v18_2_30", \
     "--cycle-sleep-sec", "120"]
