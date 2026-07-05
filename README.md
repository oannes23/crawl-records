# set-embassy — the Embassy service

The online backend for **SET.crawl**: an opt-in, fully self-hostable HTTP/JSON API that

1. **ingests gameplay run records** for balance analysis,
2. serves a deterministic **daily challenge**, and
3. returns a player's **personal bests**.

It is the foundation the eventual leaderboards / daily-content download / cross-player
records grow from — but those are **out of scope for the MVP**. See `SERVICE.md` for the
full seed spec and `CLAUDE.md` for the working orientation.

> **Status:** 🟡 in development. Built to the acceptance criteria in `SERVICE.md` §8.

## Quick start (SQLite, zero external services)

```bash
uv venv && uv pip install -e ".[dev]"   # or: python -m venv .venv && pip install -e ".[dev]"
make migrate                            # apply Alembic migrations to a fresh SQLite db
make dev                                # uvicorn on http://127.0.0.1:8000
```

- API docs (Swagger UI): http://127.0.0.1:8000/docs
- Admin panel: http://127.0.0.1:8000/admin (HTTP Basic — see config below)

## Configuration

All config is environment-driven (see `app/config.py`). Defaults run a local SQLite instance.

| Env var | Default | Meaning |
|---|---|---|
| `EMBASSY_DATABASE_URL` | `sqlite:///./embassy.db` | DB connection. **Swap to Postgres by setting this alone**, e.g. `postgresql+psycopg://user:pass@host/db`. |
| `EMBASSY_ADMIN_USER` | `admin` | Admin-panel HTTP Basic user. |
| `EMBASSY_ADMIN_PASSWORD` | `changeme` | Admin-panel HTTP Basic password. **Change in any real deployment.** |
| `EMBASSY_RULESET_VERSION` | `0.0.0-dev` | Advertised game-rules/engine version (opaque token). |
| `EMBASSY_CONTENT_VERSION` | `0.0.0-dev` | Advertised content-registry version (opaque token). |
| `EMBASSY_CONSENT_VERSION` | `1` | Current consent-text version. |
| `EMBASSY_ENABLE_INGEST` | `true` | Master switch for accepting run uploads. |
| `EMBASSY_MAX_BATCH` | `100` | Max run records per `/ingest` call. |
| `EMBASSY_DAILY_FILE` | `None` | Optional path to a `{ "YYYY-MM-DD": {classId, foeId, dungeonId, params} }` JSON map for **authored** dailies. Unset ⇒ clients derive the daily from the seed alone. |

### Publishing new content/ruleset versions

The server learns the "current official" versions only from `EMBASSY_RULESET_VERSION` /
`EMBASSY_CONTENT_VERSION`. **The publish workflow is: bump those env vars and redeploy** when
new client content ships. There is no server-side content store. Because the daily seed folds
in the versions, **bumping a version mid-day silently re-rolls that date's board** — bump at
the UTC day boundary, not mid-day.

### Switching to Postgres

Set `EMBASSY_DATABASE_URL` to a Postgres URL and run `make migrate`. No code or SQL changes —
the MVP uses only portable SQLAlchemy constructs (JSON columns included).

## What is stored (privacy posture)

Collection is **opt-in and disableable client-side**. The server stores **no PII beyond the
handle the player chooses**. Per run it stores: a client-generated `eventId`, the player's
fingerprint (an anonymous UUID with zero gameplay coupling), version pins, the run outcome
numbers, an opaque ordered action log (for future replay verification), and an open
dev-instrument summary. Recovery codes are stored **hashed**. Declining consent closes the
Embassy entirely; the game remains fully playable offline.

## Testing

```bash
make test     # pytest
```

## Self-hosting

A fresh clone runs with the Quick-start commands above on SQLite with no external services.
Point a game client at your instance via its server-URL config. This is open source; the
official instance is just the default.

## Running in a container

The repo ships a `Dockerfile`. The image runs `alembic upgrade head` (idempotent) on start,
then serves uvicorn on `0.0.0.0:8000`. It carries **no database and no secrets** — persist
the SQLite file on a volume and pass config as `EMBASSY_*` env vars.

```bash
docker build -t crawl-records:dev .
docker run --rm -p 8000:8000 \
  -v "$PWD/data:/data" \
  -e EMBASSY_DATABASE_URL=sqlite:////data/embassy.db \
  -e EMBASSY_ADMIN_PASSWORD=change-me \
  crawl-records:dev
# liveness probe (contract-free): curl -fsS localhost:8000/healthz  ->  {"status":"ok"}
```

`GET /healthz` is a liveness probe for the container `HEALTHCHECK` and uptime monitoring —
distinct from `GET /health`, which is the versioned client handshake in the contract.

**Any real deployment must set** `EMBASSY_ADMIN_PASSWORD` (never ship `changeme`) and add the
deployed game-client origin to `EMBASSY_CORS_ORIGINS`.

## Releases

Images are published to GitHub Container Registry by tag-triggered CI
(`.github/workflows/release.yml`). Cutting a numbered tag is the build signal:

```bash
git tag v0.1.0 && git push origin v0.1.0
# CI builds and pushes ghcr.io/<owner>/crawl-records:0.1.0  (+ :latest)
```

Deployment onto home infra is a separate, deliberate step that pins the exact version — see
the `local-infra` repo (`hosts/bob/compose/crawl-records/`). Keep this repo's `pyproject.toml`
`version` roughly in step with the tags.

## Regenerating the API contract

```bash
make openapi          # writes openapi.json
make codegen-hint     # prints the client-side openapi-typescript command
```

The committed `openapi.json` is the contract source of truth; the game client generates its
TypeScript network types from it. Admin routes are excluded from this artifact.
