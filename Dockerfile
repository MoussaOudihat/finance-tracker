# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────
#  Fintrack web — image de l'interface web (FastAPI + uvicorn)
#  Build :  docker build -t fintrack-web .
#  Run   :  voir docker-compose.yml / deploy/k8s/
# ─────────────────────────────────────────────────────────────

FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements-web.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements-web.txt

FROM python:3.12-slim
ARG VERSION=dev
LABEL org.opencontainers.image.title="fintrack-web" \
      org.opencontainers.image.description="Interface web de Fintrack (suivi financier personnel)" \
      org.opencontainers.image.source="https://github.com/MoussaOudihat/finance-tracker" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FINTRACK_DATA_DIR=/data

# Utilisateur non-root à UID fixe (runAsUser Kubernetes / volumes)
RUN groupadd --system --gid 10001 fintrack \
 && useradd --system --uid 10001 --gid fintrack --home-dir /app --shell /usr/sbin/nologin fintrack \
 && mkdir -p /data && chown fintrack:fintrack /data

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
# Uniquement les modules nécessaires au web (pas d'UI desktop)
COPY config.py logger.py utils.py database.py sync_supabase.py cloud_auth.py ./
COPY web/ ./web/
RUN echo "${VERSION}" > VERSION && python -m compileall -q /app

USER 10001:10001
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-m", "web.healthcheck", "/healthz"]

# 1 seul worker : les espaces utilisateurs (session Supabase + base SQLite)
# vivent en mémoire du processus. --proxy-headers : IP client réelle derrière
# l'Ingress (limitation des tentatives de connexion) et schéma https.
CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--no-server-header"]
