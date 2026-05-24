FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Debian slim strips /usr/share/man; xz/lzma packages then emit harmless
# update-alternatives warnings during apt. Restore man path + pre-create dirs.
RUN set -eux; \
    if [ -f /etc/dpkg/dpkg.cfg.d/docker ]; then \
      sed -i '/^path-exclude/s!^path-exclude /usr/share/man!path-include /usr/share/man!' /etc/dpkg/dpkg.cfg.d/docker; \
    fi; \
    mkdir -p /usr/share/man/man1; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
    ; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
