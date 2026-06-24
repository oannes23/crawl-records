# SERVICE-RESPONSE.md — the Embassy service is built (handshake back to SET.core)

> Addressed to the SET.core maintainers/agent, in answer to `SERVICE.md` §10. The Embassy
> service exists, runs on SQLite out of the box, and meets every `SERVICE.md` §8 acceptance
> criterion (checklist in §5 below). This document is the contract the client work (§6 of
> the spec) can now build against. Terse + factual, house style.

## 1. Repo location + how to run

- **Location:** this same repository (`crawl-records`, working name `set-embassy`). The
  service lives under `app/`; it is self-contained and open-source / self-hostable.
- **Run locally (SQLite, zero external services):**
  ```bash
  uv venv && uv pip install -e ".[dev]"
  make migrate        # alembic upgrade head — creates ./embassy.db
  make dev            # uvicorn on http://127.0.0.1:8000
  ```
- **Run tests:** `make test` (pytest — 26 tests, all green).
- **Browse the data:** http://127.0.0.1:8000/admin (operator panel, HTTP Basic; separate
  from the game client's Embassy — `make seed` drops a synthetic corpus in to look at).
- **Postgres:** set `EMBASSY_DATABASE_URL=postgresql+psycopg://…` and `make migrate`. No
  code/SQL changes — the MVP uses only portable SQLAlchemy constructs.

## 2. The committed OpenAPI schema + client codegen

- **Schema artifact:** `openapi.json` at the repo root (regenerate with `make openapi`;
  CI fails on drift). Covers exactly the 7 §4 endpoints; **admin routes are excluded.**
- **Client codegen command** (run in the game-client repo):
  ```bash
  npx openapi-typescript ./openapi.json -o src/net/embassy-types.ts
  ```
  Verified clean with `openapi-typescript` 7.x — no hand-edits needed. `make codegen-hint`
  prints this.

## 3. The final contract — deviations from SERVICE.md §5

The server is the contract source of truth. Field **names match the §5 sketch** (camelCase
on the wire); the deviations are additive/clarifying, none breaking. **`schemaVersion` = 1.**

1. **`/ingest` envelope.** The batch is wrapped: `POST /ingest` takes
   `{ "records": [ <runRecord>, … ] }` (not a bare array) and returns
   `{ "accepted": [eventId…], "rejected": [{ "eventId", "reason" }] }`. The §5 sketch named
   the unit record and the idempotent-batch behavior but not the wrapper; this makes the
   accepted/rejected reporting explicit (criterion 3).
2. **`terms` defined.** `outcome.terms` = **"sets matched to clear" (minimize)** — the
   `fewest-terms` criterion. `SERVICE.md` used `terms` without a unit; this is the binding
   definition. All `outcome` numbers are nullable (a `flee`/`loss` may lack a clear time).
3. **Version strings are opaque tokens.** `rulesetVersion` / `contentVersion` are stored and
   **equality-compared**, never parsed. The client may use any stable scheme; the daily
   folds them into the seed so cross-version board-equality is impossible by construction.
4. **`instruments` is an open object.** Stored verbatim, interior never validated — the
   client may add keys without a schema bump. Documented seed keys (from `TUNING.md`):
   `reshareSharePlayer`, `trapSpringRate`, `setsPerRound`, `setsMatched`,
   `tacticsUsage`, `abilityActivations`, `transmutes`. The admin instruments dashboard
   averages the first four against their TUNING targets.
5. **`actions` is opaque + append-only.** Stored as a JSON array; nothing in the MVP parses
   it. It is the replay-ready substrate for phase-2 verification.
6. **`integrity`** kept as `{ modded: bool, manifestHash: string|null }` exactly — the
   `manifestHash` slot is reserved so the future content-hash gate is not a schema break.
7. **Bests entry** carries an explicit `dailyDate` (null for delve slices, set for daily
   slices) in addition to §5's fields — makes the daily slice self-describing.
8. **Handle uniqueness is case-insensitive** (first-come on the case-folded handle); the
   original casing is preserved for display.

## 4. Endpoint reference (final)

Auth: write/`/me` endpoints require `Authorization: Bearer <token>` (issued at
register/recover, bound to the fingerprint). `/health`, `/handle/available`, `/register`,
`/recover`, `/daily` are unauthenticated.

| Method | Path | Auth | Request → Response | Errors |
|---|---|---|---|---|
| GET | `/health` | none | → `{status, schemaVersion, rulesetVersion, contentVersion, consentVersion}` | — |
| GET | `/handle/available?name=` | none | → `{name, available}` | 422 (bad query) |
| POST | `/register` | none | `{fingerprint, handle, consentVersion, client:{rulesetVersion, contentVersion}}` → `{token, recoveryCode, handle}` (201) | 409 (handle taken / fingerprint already registered) |
| POST | `/recover` | none | `{recoveryCode, fingerprint}` → `{token, handle}` | 404 (bad code), 409 (new fingerprint already registered) |
| POST | `/ingest` | bearer | `{records:[runRecord…]}` → `{accepted:[id…], rejected:[{eventId,reason}]}` | 401 (no/invalid token), 413 (batch > `max_batch`), 503 (ingest disabled) |
| GET | `/me/bests` | bearer | → `{bests:[{criterion, classId, foeId, dailyDate, value, eventId, achievedAt}…]}` | 401 |
| GET | `/daily?date=` | none | → `{date, seed, specRef, rulesetVersion, contentVersion, criteria}` | 400 (malformed date) |

- **`rejected` reasons** from `/ingest`: `modded`, `fingerprint-mismatch`, `missing-version`.
  An already-stored or in-batch-duplicate `eventId` is reported in **`accepted`** (idempotent),
  never double-stored.
- **Bests criteria:** `fewest-terms` (min terms, wins only), `fastest-clear` (min realTimeMs,
  wins only), `deepest-delve` (max depthReached, counts losses too). Sliced per
  `(classId × foeId)`; daily runs slice additionally by `dailyDate`.
- **Tie-break (documented rule):** better raw value wins; exact tie → earliest `achievedAt`;
  further tie → lexically smallest `eventId`. Deterministic and stable across calls.

## 5. §8 acceptance-criteria checklist

| # | Criterion | Status | Proving test |
|---|---|---|---|
| 1 | Stack on SQLite; one-config Postgres; no PG-only SQL | ✅ | runs on SQLite; `EMBASSY_DATABASE_URL` swap; bests computed in Python to stay portable |
| 2 | OpenAPI + clean `openapi-typescript`; committed + regenerable | ✅ | `openapi.json` + `make openapi`; codegen verified 7.x |
| 3 | Idempotent `/ingest` (dup + partial converge; reports accepted) | ✅ | `tests/test_idempotency.py` |
| 4 | Versioning persisted; `/daily` refuses cross-version; `/health` advertises | ✅ | `tests/test_versioning.py` |
| 5 | Handle uniqueness (concurrent-safe); `/recover` rebinds; codes hashed | ✅ | `tests/test_identity.py` |
| 6 | Consent gate; `modded:true` rejected | ✅ | `tests/test_consent_modgate.py` |
| 7 | Bests per criterion sliced per (foe×class) + daily slice; tie-break | ✅ | `tests/test_bests.py` |
| 8 | Daily determinism (pure fn of date + versions) | ✅ | `tests/test_daily.py` |
| 9 | Self-host: fresh clone, one command, SQLite, no external services | ✅ | README quick-start |
| 10 | Tests green; migrations apply-from-empty + reversible; CI present | ✅ | `tests/test_migrations.py`; `.github/workflows/ci.yml` |
| 11 | Privacy posture: no PII beyond handle; README states storage + opt-in | ✅ | README "What is stored" |
| 12 | No content leakage: references by id+version only | ✅ | `tests/test_admin.py` (admin excluded from contract); no balance numbers shipped |

Concurrent handle-claim safety (crit 5) rests on the `UNIQUE(handle_lower)` index + an
`IntegrityError`→409 translation, which is correct on both SQLite and Postgres.

## 6. Integration steps for the client

**Config keys the client needs** (mirror these names or map them):
- `serverUrl` — the Embassy base URL (this service; default-official or a self-host).
- `embassyEnabled` — master enable flag (the §2 consent gate; default off until consented).
- `modded` — when any modded content is loaded, set true and **make no Embassy requests**;
  the server also rejects `modded:true` records.

**Call sequence:**
1. **First visit (registration = consent):** `GET /health` → confirm `rulesetVersion`/
   `contentVersion` match the client; `GET /handle/available?name=` as the player types;
   `POST /register` → store `token` (account-level save key, NOT `SavedChar`) and **surface
   the `recoveryCode` to the player** to write down.
2. **Every run:** append a `runRecord` (with a client-generated `eventId` UUID) to the local
   outbox; `POST /ingest` the batch; **prune only the `accepted` IDs** from the outbox.
3. **Bests UI:** `GET /me/bests`; display best-per-criterion per (class × foe), and the daily
   slice by date.
4. **Daily:** `GET /daily` → if its `rulesetVersion`/`contentVersion` ≠ the client's, show
   **"update to play today"** and do not regenerate; else regenerate the board from `seed` +
   `specRef` locally.
5. **Reinstall/new device:** `POST /recover` with the saved `recoveryCode` + the new
   fingerprint → new `token`; old runs follow the player.

**Behaviors the client must honor:**
- **Version mismatch** → daily unavailable; ingest still allowed (records carry their own
  versions), but bests/daily are only meaningful on matching versions.
- **Mod detected** → Embassy fully disabled client-side (no requests).
- **Decline consent** → Embassy closed; game fully playable offline; re-enter to opt in.
- **Idempotency** → safe to re-`POST` the outbox after a lost ack; prune on `accepted`.

## 7. Open questions — resolved + new

Resolved (SERVICE.md §9):
- **Bearer token shape/rotation:** opaque `secrets.token_urlsafe(32)`, bound to the
  fingerprint, looked up on each request. **No rotation in the MVP** (re-issued on
  `/recover`). Sufficient for single-player; revisit with leaderboards.
- **Daily seed scheme:** `seed = sha256("{date}|{rulesetVersion}|{contentVersion}")[:16]`;
  `specRef = "daily/{date}/{ruleset}+{content}"`. **UTC calendar date** is the rollover
  boundary (`/daily` defaults to today UTC).
- **Bests recompute vs read:** **compute-on-read** for the MVP (single-player volume is
  trivial; keeps SQL portable). Clean seam to materialize a `bests` table later
  (`app/services/bests.py`).
- **Payload caps:** `EMBASSY_MAX_BATCH` (default 100) caps records per `/ingest`;
  `EMBASSY_ENABLE_INGEST` is a master switch. Per-request body-size limits are left to the
  reverse proxy (document at deploy).

New / still open:
- **Hosting target + deploy doc** — not chosen (recommend a Fly/Railway/Render-class PaaS on
  SQLite-on-volume for the official instance; Postgres when leaderboards land). Not blocking.
- **`instruments` key catalog** — the client's recorder defines the real keys; the four
  documented above are seeded from `TUNING.md`. Extend freely (open object).
- **Recovery-code lookup** is currently a hashed scan over identities (fine at single-player
  scale). Revisit (a lookup index / KDF) if the corpus grows large.

## 8. What's stubbed vs real, and the phase-2 seam

**Real:** all 7 endpoints, identity/recovery, idempotent ingest, consent + mod gate,
compute-on-read bests with documented tie-break, deterministic daily, the full admin panel,
migrations (reversible), CI, the committed OpenAPI contract.

**Stubbed / honor-system (by design, per spec):**
- **Mod gate** = honor-system `modded` flag. The `integrity.manifestHash` slot is reserved
  so the future content-hash gate is not a schema break. Self-hosts set their own manifest.
- **`actions`** is captured replay-ready but **not verified** — stored opaque/append-only.

**Phase-2 seam (not built):** cross-player leaderboards plug into the **bests read model**
(`/me/bests` generalizes to a global query). Replay verification consumes the **`actions`**
log + `seed` + version pins (deterministic re-simulation server-side). Content/asset download
is a separate surface; the daily already proves the seed-not-payload pattern. None of these
require a schema break to the run record — that was the point of designing it replay-ready now.
