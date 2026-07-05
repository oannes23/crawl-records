# syntax=docker/dockerfile:1
#
# set-embassy container image. Two stages:
#   builder  — resolve + install deps into a venv from the committed uv.lock (reproducible)
#   runtime  — slim, non-root, no build tooling; runs migrations then uvicorn
#
# The image ships app + alembic (migrations run at container start) but NO database and NO
# secrets — config arrives via EMBASSY_* env vars, the SQLite file lives on a mounted volume.
# Build/publish is tag-triggered CI (.github/workflows/release.yml) → ghcr.io.

# ---- builder ---------------------------------------------------------------
FROM python:3.11-slim AS builder

# Pin uv to the version that authored uv.lock (keep in step with the Homebrew uv used locally).
COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Layer 1 — dependencies only, cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Layer 2 — the application (+ alembic migrations, admin templates travel inside app/).
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- runtime ---------------------------------------------------------------
FROM python:3.11-slim AS runtime

# curl for HEALTHCHECK; tini for correct PID-1 signal handling.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

COPY --from=builder /app /app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER app
EXPOSE 8000

# Liveness only — the process is up and serving. Readiness (DB reachable) is not gated here.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
