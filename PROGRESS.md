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

## SERVICE-REPLY.md follow-ups (answered 2026-06-23 — see `SERVICE-REPLY-RESPONSE.md`)
- ✅ Item 1: optional authored-daily `spec` on `/daily` (path b shape shipped; path a default) — `EMBASSY_DAILY_FILE`; `test_reply_followups.py`
- ✅ Item 2: version source = operator env config; publish = bump+redeploy; "don't bump mid-day" documented (README/.env.example)
- ✅ Item 3: `/recover` re-issues a token for the original fingerprint (token-only loss) — confirmed + tested
- ✅ Item 4: `rejected` entries carry `terminal: bool`; the three MVP reasons are terminal — `test_reply_followups.py`
- ⏸️ Item 5 (phase-2): `fastest-clear` not replay-verifiable — logged in phase-2 ledger
- ⏸️ Item 6 (phase-2): `consentVersion` bump → re-prompt on next visit — spec line when consent text changes

## Pre-public hardening (tracked; not blocking client handoff)
- ⬜ Recovery-code entropy + rate-limit + KDF (current: 4 words, unsalted sha256, O(n) scan)
- ⬜ Per-request payload-size cap + rate limiting on `/ingest`
- ⬜ Concurrency test for parallel handle claims (Postgres)
- ⬜ Token expiry/rotation; structured logging + metrics

## Phase-2 seam (NOT built)
Cross-player leaderboards · content/asset download · server-side replay verification ·
signed-content anti-cheat · social/accounts. Data is captured replay-ready; the bests query
is the leaderboard read-model seed.

---

# FABLE roadmap (post-MVP hardening & depth)

Derived from `FABLE.md` (Fable 5 review, 2026-07-01 @ `9d95dd8`). Each item is one
agent-sized task; the ID (B/S/C/D/A/G/O) points at the FABLE.md section with the full
analysis, repro, and fix sketch. **Do phases in order; do items within a phase in order.**

**Standing rules for every item:** run `make test && make lint && make openapi && git diff
--exit-code openapi.json` before calling it done · new gates land with a proving test in the
matching `tests/test_*.py` (acceptance criteria map 1:1 to tests) · update this file as items
land · items tagged **[SEAM]** need the mirrored change (or explicit ack) in
`set-core/src/net/contract.ts` + the handshake docs before merge. Validation-only and additive
changes keep `schemaVersion` at 1 — do not break it in phase R1/R2.

## Phase R1 — correctness of what exists (validation-only; no wire break)
- ✅ **B5** (P1) String bounds on every wire field + handle charset/min-length/trim — unblocks
  the Postgres one-var-swap claim; biggest blast radius. `test_validation.py`. **[SEAM]** the
  client caps handle length only (`maxlength=18`, min 2) — it must adopt the charset rule
  `^[A-Za-z0-9][A-Za-z0-9 _\-]{0,31}$` or a valid client handle can 422. **Client mirror pending.**
- ✅ **B2** (P1) Outcome bounds — `Field(ge=0)` + sane upper caps on `terms`/`realTimeMs`/
  `depthReached`; negatives no longer become personal bests. `test_validation.py`.
- ✅ **B4** (P1) `kind`/`dailyDate` cross-validation — `model_validator`: `daily` ⇔ dated,
  `delve` ⇒ null; a null-dated daily no longer pollutes the delve bests slice. `test_validation.py`.
- ✅ **B1** (P1) Fingerprint-scoped idempotency + `event-id-conflict` terminal reject — a
  cross-player `eventId` collision now rejects instead of silently reporting `accepted`.
  `test_idempotency.py`. New terminal reason documented in `RejectedRecord`.
- ⬜ **B6** (P2) Assert `schemaVersion` — reject unsupported versions terminal; today `999` is accepted.
  Document the new reason in SERVICE-RESPONSE.md. Test: `schemaVersion:2` → terminal reject; `1` passes.
- ⬜ **B3** (P2) `/daily` date normalization — `strptime`→`strftime` round-trip so `2026-7-1` ==
  `2026-07-01` (same seed + same bests slice). Test: `?date=2026-7-1` returns padded date + matching seed.
- ⬜ **C1** (P2) Per-record `IntegrityError` handling — `begin_nested()` per insert so a raced
  first-time `eventId` is treated as duplicate-accepted, not a 500 that drops the whole batch.
- ⬜ **Cleanup bundle** (one PR): **D1** align "upsert"→first-write-wins wording (CLAUDE.md/
  SERVICE-RESPONSE.md/docstring) · **D2** use-or-delete `_TERMINAL_REASONS` · **C6** dedupe the
  `accepted` list (`dict.fromkeys`) + tighten test to `== 1` · **C5** 401-not-403 on missing bearer
  (`auto_error=False` + `WWW-Authenticate`) · **A1** move `_auth` helper to `conftest.py` · **A2**
  `RunSummary` schema for `api_runs` camelCase · **A3** `false()` sentinel · **A4** carry `_Criterion` in bests key.

## Phase R2 — pre-public hardening (before any non-friends deployment)
- ⬜ **S1** (P1) Recovery-code scheme — real entropy (EFF long list), handle-scoped `/recover`
  (kills the O(n) scan + cross-account collision), per-identity salted hash. **[SEAM]** add
  `handle` to `RecoverRequest` (optional now → required later) ↔ recover UX. Test: handle+code
  succeeds; wrong handle + valid code fails; two identities forced onto one code each recover only self.
- ⬜ **S2** (P1) Rate limiting — `/register` & `/recover` 5/hr/IP, `/ingest` 60/min/token → 429
  (+`Retry-After`); in-app token bucket preferred over a dep. Test: N+1th in window → 429; expiry restores.
- ⬜ **S3** (P2) Body-size caps — ASGI middleware rejects `Content-Length` > ~10 MB (413) + pydantic
  `actions max_length` + per-record serialized-size cap. **[SEAM]** confirm worst-case delve action count.
- ⬜ **S4** (P2) Hash bearer tokens at rest — store `sha256(token)`, look up by hash; no wire change.
  Test: register → token authenticates; DB row has no raw token.
- ⬜ **O1** SQLite WAL + `busy_timeout` PRAGMA on connect + README "SQLite = single process" note.
- ⬜ **O4** Postgres CI job — service container + `alembic upgrade head` + pytest against
  `EMBASSY_DATABASE_URL`; mechanical guard for the B5/C2/C3 portability class.
- ⬜ **S5** (P3) `changeme` guard — loud warning or refuse `/admin` when default password + non-local bind; HTTPS note.
- ⬜ **G7** (P2) `DELETE /me` — bearer-authed erasure of identity + all runs (or handle tombstone);
  admin per-identity delete. **[SEAM]** "Leave the Embassy" UX. Fold in **D5** README data-deletion wording.

## Phase R3 — product depth (coordinate with the set-core session)
- ⬜ **G1** (P2) Daily streaks — additive read-model (`daily:{streak,bestStreak,playedToday}` on
  `/me/bests` or new `GET /me/daily`); strongest cheap retention add. **[SEAM]** Daily Dispatch UI.
- ⬜ **G2** (P2) Bests filtering params — additive `?kind=` / `?since=`; `/me/bests` grows unbounded
  (a year of dailies ≈ 1000+ entries). **[SEAM]** decide client display needs first.
- ⬜ **G5** (P2) Real version tokens — build/content hash from the client release pipeline injected
  into the Embassy deploy env (one artifact, two consumers); server side is already env-ready. **[SEAM]** client-driven.
- ⬜ **G3** (design) `deepest-delve` slicing — depth is a run property; today sharded per (class×foe).
  Likely per-**class** only. Read-model change, no wire break — **game-design ratification (set-core) first**. **[SEAM]**
- ⬜ **C2** (P3) Timezone-aware datetimes — `DateTime(timezone=True)` + UTC-suffixed ISO responses;
  fold into any migration R2/R3 already requires. **[SEAM]** confirm client date parsing (should be a no-op).
- ⬜ **S6 + G6** Daily secret + persisted roll — fold `EMBASSY_DAILY_SECRET` into the seed hash,
  clamp served dates to `today ± 1`, persist first roll to a `daily_roll` table. **Prerequisite for leaderboards.**
  **[SEAM]** verify the client never recomputes the seed (only derives selections from it).
- ⬜ **Doc/DX bundle**: **D3** reshape-typo decision (lockstep rename vs. canonize; **[SEAM]**) · **D4**
  handle-change deferral note (or `POST /me/handle`) · **C7** consentVersion check at register (**[SEAM]**
  client reads `/health` first) · **C3** admin date-filter fix/removal · **C4** malformed `EMBASSY_DAILY_FILE`
  fallback · **C8** document the manual `run.fingerprint`↔`identity` invariant · **C9** escape `%` in Alembic URL ·
  **G4** `featuredCriterion` daily convention (**[SEAM]**) · **G8** `GET /me` · **O2** structured logging/metrics ·
  **O3** deploy doc (HTTPS, body cap, CORS origin, backup).

## Cross-repo coordination ledger (workspace-level; see FABLE.md §10)
Two items cannot be resolved in this repo alone — surface to the set-core session:
- **D3** `reshareSharePlayer` fossilized typo lives in BOTH repos (client `capture.ts:132` +
  server `admin.py:110`/`seed_demo.py`). They agree today; a unilateral rename silently zeroes the
  aggregate. **Decision needed:** lockstep rename (dual-emit transition) or canonize the typo.
- **G3** `deepest-delve` per-(class×foe) slicing is a game-design call about what a "best" means —
  owned by set-core; server change is a small read-model rekey once ratified.
