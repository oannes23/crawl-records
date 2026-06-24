# PROGRESS.md — Embassy service build tracker

Single source of truth for project todo + progress. Update as work lands. Build target:
the acceptance criteria in `SERVICE.md` §8. Companion: `CLAUDE.md` (orientation).

**Legend:** ✅ done · 🔄 in progress · ⬜ todo · ⏸️ deferred (phase 2+)

**MVP status (2026-06-23): ✅ COMPLETE — all §8 criteria met, 26 tests green, `SERVICE-RESPONSE.md` written.**

---

## Milestones

### 1. Scaffolding & tooling
- ✅ `pyproject.toml` (FastAPI + pydantic + SQLAlchemy + Alembic; `uv` for env/packages)
- ✅ `uv` venv + deps installed
- ✅ Package structure (`app/{models,schemas,routers,services,templates}`, `alembic/`, `tests/`, `scripts/`)
- ✅ `README.md` (quick start, config, privacy posture, self-host, codegen)
- ✅ `PROGRESS.md` (this file)
- ✅ `Makefile` (`dev`/`test`/`migrate`/`revision`/`openapi`/`codegen-hint`/`seed`/`lint`)
- ✅ `.env.example`

### 2. CLAUDE.md (repo orientation)
- ✅ `CLAUDE.md` in the SET house style (what this is, the insight, invariants, arch map, working style)

### 3. Config & DB
- ✅ `app/config.py` (env-driven settings; SQLite→Postgres one-var swap)
- ✅ `app/db.py` (engine/session, portable connect args)

### 4. Data model + migrations
- ✅ `app/models/identity.py` (fingerprint PK, unique handle_lower, recovery hash, token, consent)
- ✅ `app/models/run.py` (eventId PK, version pins, integrity, sliced context/outcome cols, JSON actions/instruments)
- ✅ Alembic initial migration (applies from empty + reversible — verified by test + manually)

### 5. Wire schemas (pydantic — the published contract)
- ✅ `app/schemas/contract.py` mirroring SERVICE.md §5 with locked deviations (camelCase aliases)
- ✅ `terms` defined ("sets matched to clear"); `instruments` open object; opaque version strings

### 6. Endpoints (§4 MVP) + logic
- ✅ `GET /health`
- ✅ `GET /handle/available`
- ✅ `POST /register` (+ recovery code, hashed)
- ✅ `POST /recover` (rebinds + carries run history)
- ✅ `POST /ingest` (idempotent batch upsert; consent + mod gate; batch cap)
- ✅ `GET /me/bests` (compute-on-read; deterministic tie-break)
- ✅ `GET /daily` (pure fn of date + versions)
- ✅ `app/auth.py` (bearer token bound to fingerprint; admin Basic; recovery hashing)

### 7. Admin web UI (Jinja2 + vanilla JS; `/admin`, excluded from client OpenAPI)
- ✅ Admin auth gate (HTTP Basic, separate from player tokens)
- ✅ Runs browser (filters + sort + drill-down to raw actions/instruments)
- ✅ Identities view
- ✅ Bests explorer
- ✅ Daily inspector
- ✅ Instruments dashboard (aggregate dev-instrument targets)
- ✅ Health/versions panel

### 8. Tests (pytest — one proving test per §8 criterion + admin smoke) — 26 passing
- ✅ Idempotency (crit 3) — `test_idempotency.py`
- ✅ Versioning (crit 4) — `test_versioning.py`
- ✅ Identity / recovery / hashed codes (crit 5) — `test_identity.py`
- ✅ Consent + mod gate (crit 6) — `test_consent_modgate.py`
- ✅ Bests correctness + tie-break (crit 7) — `test_bests.py`
- ✅ Daily determinism (crit 8) — `test_daily.py`
- ✅ Migrations apply-from-empty + reversible (crit 10) — `test_migrations.py`
- ✅ Admin smoke + contract-isolation (crit 12) — `test_admin.py`

### 9. OpenAPI artifact + codegen
- ✅ `scripts/export_openapi.py` + committed `openapi.json` (7 paths, admin excluded)
- ✅ Verified `openapi-typescript` 7.x produces a clean client (541-line TS, exit 0)

### 10. CI + docs
- ✅ GitHub Actions workflow (`.github/workflows/ci.yml`: lint + migrations + pytest + openapi-drift)
- ✅ README + `.env.example`; deploy-target left as an open question

### 11. SERVICE-RESPONSE.md (the §10 handshake)
- ✅ Written to repo root — repo/run/test, OpenAPI + codegen, contract deviations, endpoint
  reference, §8 checklist with proving tests, client integration sequence, resolved questions, phase-2 seam

---

## §8 acceptance-criteria checklist (proving test cited)
1. ✅ Stack: FastAPI+pydantic+SQLAlchemy+Alembic on SQLite; one-env Postgres path; no PG-only SQL
2. ✅ OpenAPI emitted + clean `openapi-typescript` client; committed + regenerable (`make openapi`)
3. ✅ Idempotent `/ingest` — `test_idempotency.py`
4. ✅ Versioning persisted; `/daily` refuses cross-version equality; `/health` advertises — `test_versioning.py`
5. ✅ Handle uniqueness (concurrent-safe); `/recover` rebinds; recovery codes hashed — `test_identity.py`
6. ✅ Consent gate; `modded:true` rejected — `test_consent_modgate.py`
7. ✅ Bests per criterion sliced per (foe×class) + daily slice; documented tie-break — `test_bests.py`
8. ✅ Daily determinism; pinned test — `test_daily.py`
9. ✅ Self-host: fresh clone, one command, SQLite, no external services — README
10. ✅ Tests green (26); migrations apply-from-empty + reversible — `test_migrations.py`; CI present
11. ✅ Privacy posture: no PII beyond handle; README states what's stored + opt-in
12. ✅ No content leakage: references by id+version only; admin excluded from contract — `test_admin.py`

---

## Open questions (SERVICE.md §9 — resolved here; see SERVICE-RESPONSE.md §7)
- ✅ Bearer token → opaque random token bound to fingerprint, no rotation in MVP
- ✅ Daily seed → sha256(date | rulesetVersion | contentVersion)[:16]; UTC-midnight rollover
- ✅ Bests → compute-on-read for the MVP
- ✅ `terms` → "sets matched to clear" (minimize)
- ✅ Payload caps → `max_batch` (default 100) + `enable_ingest` master switch
- ⬜ Hosting target + deploy doc → STILL OPEN (recommend Fly/Railway-class; not blocking)

## Phase-2 seam (NOT built)
Cross-player leaderboards · content/asset download · server-side replay verification ·
signed-content anti-cheat · social/accounts. Data is captured replay-ready; the bests query
is the leaderboard read-model seed.
