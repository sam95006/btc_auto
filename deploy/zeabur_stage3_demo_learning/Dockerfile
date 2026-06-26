FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEXUS_DATA_DIR=/data \
    STAGE3_STARTUP_MODE=idle \
    STAGE3_OUTPUT_DIR=/data/stage3_demo_learning \
    RESEARCH_ONLY=true \
    BYBIT_DEMO_LEARNING_MODE=true \
    BYBIT_SHADOW_MODE=false \
    PAPER_ONLY=false \
    BYBIT_ORDER_ALLOWED=true \
    BYBIT_ORDER_SCOPE=demo_or_testnet_only \
    BYBIT_MAINNET_ALLOWED=false \
    BYBIT_M0_BASE_URL=https://api-demo.bybit.com \
    EXCHANGE_WRITE_ALLOWED=true \
    EXCHANGE_WRITE_SCOPE=bybit_demo_or_testnet_only \
    REAL_MONEY=false \
    LIVE_TRADING=false \
    PRODUCTION_PROMOTION_ALLOWED=false \
    ARM_ALLOWED=false \
    MAX_MARGIN_USD=20 \
    MAX_LEVERAGE=3 \
    MAX_OPEN_POSITIONS=1 \
    REQUIRE_STOP_LOSS=true \
    REQUIRE_MAX_HOLD=true \
    REQUIRE_REFLECTION_ON_LOSS=true \
    REQUIRE_PATCH_BEFORE_NEXT_SAME_SETUP=true \
    ZEABUR_PRODUCTION_RUNNER_ALLOWED=false \
    PORT=8080

WORKDIR /app
RUN mkdir -p /data/data/external_alpha/demo_learning /data/logs /data/exports /data/stage3_demo_learning

COPY . .
RUN chmod +x entrypoint.sh run_stage3_demo_order_background.sh run_stage3_24h_demo_learning_background.sh
EXPOSE 8080
# STAGE3_STARTUP_MODE=idle: read-only Web UI; runner mode spawns 24h runner then same UI
CMD ["/bin/sh", "./entrypoint.sh"]
