# syntax=docker/dockerfile:1.7

FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

ARG CAMOUFOX_VERSION=135.0.1
ARG CAMOUFOX_RELEASE=beta.24

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    APP_CONDA_ENV=docker \
    APP_RELOAD=0 \
    APP_RUNTIME_DIR=/runtime \
    APP_ENABLE_SOLVER=1 \
    SOLVER_PORT=8889 \
    SOLVER_BIND_HOST=0.0.0.0 \
    LOCAL_SOLVER_URL=http://127.0.0.1:8889 \
    SOLVER_BROWSER_TYPE=camoufox

WORKDIR /app

COPY requirements.txt ./
COPY scripts/install_camoufox.py /tmp/install_camoufox.py

RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && installed=0 \
    && for attempt in 1 2 3; do \
         if python -m playwright install --with-deps chromium; then \
           installed=1; \
           break; \
         fi; \
         if [ "$attempt" -eq 3 ]; then break; fi; \
         echo "playwright browser install failed, retrying ($attempt/3)..." >&2; \
         sleep 5; \
       done \
    && [ "$installed" -eq 1 ] \
    && CAMOUFOX_VERSION="$CAMOUFOX_VERSION" CAMOUFOX_RELEASE="$CAMOUFOX_RELEASE" python /tmp/install_camoufox.py

COPY . .
COPY --from=frontend-builder /app/static /app/static

RUN chmod +x /app/docker/entrypoint.sh \
    && mkdir -p /runtime /runtime/logs /runtime/smstome_used /app/_ext_targets

EXPOSE 8000 8889

VOLUME ["/runtime", "/app/_ext_targets"]

ENTRYPOINT ["/app/docker/entrypoint.sh"]
