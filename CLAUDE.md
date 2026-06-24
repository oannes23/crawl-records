# CLAUDE.md — guidance for Claude Code sessions on set-embassy

Read `SERVICE.md` first — it is the seed spec from the SET.crawl game client, and its
**§8 acceptance criteria are the build target**. This file is the fast orientation.
`PROGRESS.md` is the live todo/progress tracker — update it as work lands.

## What this is

The **Embassy service** — the online backend for **SET.crawl**. An opt-in, fully
self-hostable HTTP/JSON API that (a) **ingests gameplay run records** for balance
analysis, (b) serves a deterministic **daily challenge**, and (c) returns a player's
**personal bests**. It is the foundation leaderboards / daily-content download / replay
verification grow from later — all **phase 2+, out of the MVP**.

**Stack:** FastAPI + pydantic v2 + SQLAlchemy 2 + Alembic, **SQLite-first**, Postgres-ready.
Env/packages via **`uv`**. The server emits **OpenAPI**; the game client codegens its
TypeScript network types from the committed `openapi.json` — the **server is the contract
source of truth**.

## The one insight (don't lose this)

The game core is a **pure deterministic generator from a seed/spec**. Therefore:
- The daily challenge ships as a **tiny seed + version pins**, never a content payload —
  the client regenerates the identical board locally.
- A run's **ordered action stream + seed + versions** is **deterministically replayable**.
  The same event log that feeds balance analysis is the future leaderboard's anti-cheat
  substrate — so the schema is **replay-ready now**, even though replay verification is
  deferred. `run.actions` is stored opaque + append-only; nothing in the MVP parses it.

## Hard invariants (assert in any change)

1. **Server is the contract source of truth.** Any change to a wire shape (`app/schemas/`)
   must keep `openapi.json` regenerable (`make openapi`) and bump `schemaVersion` on a
   breaking change. The client builds against this artifact.
2. **Opaque store-and-forward.** The server interprets only: `eventId` (dedupe), version
   strings (equality compare for daily), and `outcome` numbers (bests). `seed`, `specRef`,
   `actions`, `instruments`, and every id string are stored verbatim and never parsed.
3. **SQLite-first / Postgres-ready.** No dialect-specific SQL. Switching DB is one env var
   (`EMBASSY_DATABASE_URL`). Bests are computed in Python (compute-on-read) precisely to
   avoid `DISTINCT ON`/window-function portability traps.
4. **Idempotency.** `/ingest` is an idempotent batch upsert keyed on `eventId`;
   re-uploading never double-counts. The client prunes only acked IDs.
5. **Versioning asserted on every record** (`schemaVersion`, `rulesetVersion`,
   `contentVersion`); never inferred. `/daily` folds versions into the seed so it can't
   assert board-equality across a mismatch.
6. **Consent + mod gate.** No run is accepted without a registered identity (bearer token);
   a `modded: true` record is rejected. Consent is the registration.
7. **Ships no game content.** References content by id + version only. `TUNING.md`/`MODDING.md`
   (in the game repo) stay the single authoring home; this repo carries `TUNING.md` only as
   a read-only reference for the dev-instrument field names.

## Architecture map

- `app/config.py` — env-driven settings (`EMBASSY_` prefix); the DB-swap + version source.
- `app/db.py` — engine/session; `Base` for models. Portable connect args.
- `app/models/` — ORM: `identity` (fingerprint PK, unique handle, hashed recovery, token),
  `run` (eventId PK, version pins, sliced context/outcome cols, JSON `actions`/`instruments`).
- `app/schemas/contract.py` — **the published wire contract** (camelCase aliases). Stable.
- `app/services/` — `identity` (register/recover), `ingest` (idempotent), `bests`
  (compute-on-read + documented tie-break), `daily` (deterministic), `admin` (read queries).
- `app/routers/public.py` — the §4 MVP endpoints (these ARE the contract).
- `app/routers/admin.py` — operator panel under `/admin` (HTTP Basic, **separate** from
  player tokens), `include_in_schema=False` so it never leaks into the client contract.
- `app/auth.py` — player bearer (bound to fingerprint) + admin Basic + recovery-code hashing.
- `alembic/` — migrations (env reads URL from `app.config`; `render_as_batch` for SQLite).

## Working style

- **Run via `uv`.** `make dev` (server), `make test` (pytest), `make migrate`,
  `make openapi` (regen contract), `make codegen-hint` (prints the client TS command),
  `make seed` (synthetic corpus for the admin UI).
- **Tests are the proof of §8.** Each acceptance criterion has a proving test
  (`tests/test_*.py`); keep them green and keep them mapped (see `PROGRESS.md` checklist).
  New endpoints/logic land already-tested.
- **Regenerate `openapi.json` whenever a wire shape changes**, and re-check the codegen
  still produces a clean client.
- **Migrations stay reversible** (a test asserts apply-from-empty + downgrade-to-base).
- Keep docs terse + factual in the SET house style.

## Repo / workflow

- Open-source + self-hostable: a fresh clone runs on SQLite with `uv pip install -e ".[dev]"`
  → `make migrate` → `make dev`, no external services.
- **The deliverable handshake:** when the service meets §8, write/maintain
  `SERVICE-RESPONSE.md` at the repo root (per SERVICE.md §10) — the contract doc the game
  client builds its Embassy integration against. Keep it in sync with the real API.

## Phase-2 seam (do not build in the MVP)

Cross-player leaderboards · content/asset download · server-side replay verification ·
real anti-cheat / signed content · social/accounts. The data is captured replay-ready and
the bests query is the leaderboard read-model seed; that's where phase 2 plugs in.
