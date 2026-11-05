# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────
#  Image commune aux 4 microservices Fintrack.
#    docker build -f services/Dockerfile --build-arg SERVICE=web services/
#  SERVICE ∈ web | finance_api | ai_service | notifier
#
#  Bonnes pratiques : image de base épinglée par digest, build multi-étapes
#  (aucun outil de build dans l'image finale), utilisateur non-root à UID
#  fixe, système de fichiers prévu en lecture seule, healthcheck sans curl.
# ─────────────────────────────────────────────────────────────
ARG PYTHON_IMAGE=docker.io/library/python:3.12-slim@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b

# Image épinglée par digest via ARG PYTHON_IMAGE (DL3006 = faux positif)
# hadolint ignore=DL3006
FROM ${PYTHON_IMAGE} AS builder
ARG SERVICE
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements-common.txt ./
COPY ${SERVICE}/requirements.txt ./${SERVICE}/
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install --require-virtualenv -r ${SERVICE}/requirements.txt \
 && /opt/venv/bin/pip uninstall -y pip

# hadolint ignore=DL3006
FROM ${PYTHON_IMAGE}
ARG SERVICE
ARG VERSION=dev
LABEL org.opencontainers.image.title="fintrack-${SERVICE}" \
      org.opencontainers.image.source="https://github.com/MoussaOudihat/finance-tracker" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    FINTRACK_VERSION=${VERSION} \
    PORT=8000 \
    FORWARDED_ALLOW_IPS=127.0.0.1

# Correctifs de sécurité Debian appliqués au build : couvre le délai entre la
# publication d'un correctif (ex. apt CVE-2026-109518) et la reconstruction de
# l'image officielle. Le scan Trivy de la CI vérifie le résultat.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Pas de gestionnaire de paquets Python dans l'image finale : on retire pip
# (et le setuptools qu'il embarque, signalé CVE-2025-47273) de l'interpréteur système.
RUN groupadd --system --gid 10001 fintrack \
 && useradd --system --uid 10001 --gid fintrack --home-dir /app --shell /usr/sbin/nologin fintrack \
 && mkdir -p /data && chown fintrack:fintrack /data \
 && rm -rf /usr/local/lib/python3.12/site-packages/pip /usr/local/lib/python3.12/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.12/ensurepip /usr/local/bin/pip /usr/local/bin/pip3*

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY common/fintrack_common ./fintrack_common
COPY ${SERVICE}/app ./app
RUN python -m compileall -q /app

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-m", "fintrack_common.healthcheck", "/healthz"]

# --proxy-headers : X-Forwarded-For n'est cru que depuis FORWARDED_ALLOW_IPS
# (à régler sur l'adresse du reverse proxy / contrôleur d'Ingress).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips ${FORWARDED_ALLOW_IPS} --no-server-header --timeout-graceful-shutdown 20"]
