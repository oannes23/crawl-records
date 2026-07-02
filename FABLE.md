# FABLE.md — deep analysis of `crawl-records` (set-embassy)

> **What this is:** a Claude Fable 5 review of this Opus-built repo (2026-07-01, at commit
> `9d95dd8`), covering bugs, security, portability, design misconceptions, simplification,
> and game/product gaps at the client seam. It is the input to a roadmap; each item is
> written so a smaller agent can execute it without re-deriving the analysis.
>
> **Verdict up front:** the MVP is well-built — clean layering, honest docs, every §8
> criterion genuinely tested, no over-engineering. The findings below are mostly *edges*:
> input validation the contract never states, races the single-writer dev setup hides, and
> a recovery-code scheme that is not safe past a few hundred users. Items marked
> **CONFIRMED** were reproduced live in this session; **PLAUSIBLE** items are reasoned
> from code but not executed.
>
> **Severity:** P1 = fix before any public deployment · P2 = fix soon, low risk today ·
> P3 = roadmap/judgment call.
>
> **Contract discipline reminder for executing agents:** every fix that touches
> `app/schemas/contract.py` must keep `openapi.json` regenerable (`make openapi`, CI
> drift-checks it) and must be **additive or validation-only** to keep `schemaVersion` at 1.
> Wire-shape changes must be mirrored into `set-core/src/net/contract.ts` (hand-maintained;
> codegen exists but is not wired). Items needing the game-client session are tagged
> **[SEAM: set-core]**.

---

## 1. Confirmed bugs (reproduced in this session)

### B1 (P1) — Cross-player `eventId` collision silently destroys a player's run
`app/services/ingest.py:32-37` — the idempotency pre-check
`select(Run.event_id).where(Run.event_id.in_(incoming_ids))` is **not scoped to the
caller's fingerprint**. If player B uploads a record whose `eventId` already exists under
player A, the record is skipped **and reported in `accepted`** — B's client then prunes it
from the outbox. The run is gone forever, with no error anywhere.

Repro (executed): Alice ingests `e1` → `accepted:["e1"]`. Bob ingests his own run as `e1`
→ `accepted:["e1"]`, Bob's `/me/bests` is empty.

With honest UUID clients this needs a collision; but nothing enforces UUIDs (`eventId` is
any string ≤64 chars in practice), so a buggy or malicious client makes this trivial, and
the failure mode is *silent data loss for the victim of the response semantics*.

**Fix:** scope the existing-ID query with `Run.fingerprint == caller.fingerprint`. If an
incoming `event_id` exists under a *different* fingerprint, emit a rejection
`{reason: "event-id-conflict", terminal: true}` (new reason string — additive, the client
already branches on the `terminal` boolean per SERVICE-REPLY-RESPONSE.md §4). Do **not**
report it accepted.
**Test:** two registered identities; same `eventId`; assert second caller gets
`rejected[0].reason == "event-id-conflict"` and their row count is unchanged.

### B2 (P1) — Outcome numbers are unbounded; a negative value becomes a personal best
`app/schemas/contract.py:51-56` (`RunOutcome`) has no bounds. `terms: -999` is accepted
and immediately becomes the `fewest-terms` best (confirmed). Since the bests query is
explicitly the phase-2 leaderboard read-model seed, garbage accepted now is leaderboard
corruption later — and rows are append-only, so it never ages out.

**Fix:** add `Field(ge=0)` to `terms`, `real_time_ms`, `depth_reached`, and sane upper
caps (suggest `terms le=100_000`, `real_time_ms le=7*24*3600*1000`, `depth_reached
le=10_000`). Validation-only: `schemaVersion` stays 1; a well-behaved client is unaffected.
Pydantic-level rejection fails the whole batch with 422 — that is acceptable (a client
producing negatives is broken), but note it in the docstring.
**Test:** negative and absurd values → 422; boundary values pass.

### B3 (P2) — `/daily` date is not normalized: `2026-7-1` and `2026-07-01` are different dailies
`app/services/daily.py:69-75` — `validate_date` parses with `strptime` (which accepts
non-zero-padded input) but returns the **raw string**, which is then hashed into the seed.
Confirmed: `_seed_for('2026-7-1',…)` ≠ `_seed_for('2026-07-01',…)`. Two clients asking for
the same calendar day can get different boards; the bests daily slice (keyed by the string
`dailyDate`) splits the same day into two slices.

**Fix:** `parsed = datetime.strptime(date, "%Y-%m-%d"); return parsed.strftime("%Y-%m-%d")`.
Also decide a served-date window (see G6/S6 — suggest rejecting dates more than 1 day in
the future with 400) — but the normalization fix alone is safe and immediate.
**Test:** `GET /daily?date=2026-7-1` returns `date == "2026-07-01"` and the same seed as
the padded form.

### B4 (P2) — `kind:"daily"` with `dailyDate:null` pollutes the delve bests slice
`app/schemas/contract.py:42-48` allows `dailyDate: None` regardless of `kind`;
`app/services/bests.py:69-71` then keys such a run as `(crit, class, foe, None)` — the
**same slice as delve runs**. Confirmed: a daily run with no date overwrote the caller's
delve `fewest-terms` best. Inverse case (`kind:"delve"` with a `dailyDate`) is silently
stored inconsistently.

**Fix:** add a pydantic `model_validator` on `RunContext`: `kind == "daily"` ⇔
`daily_date` present and matching `^\d{4}-\d{2}-\d{2}$`; `kind == "delve"` ⇒
`daily_date is None`. Validation-only, `schemaVersion` stays 1.
**Test:** both invalid combinations → 422; valid daily and delve records pass.

### B5 (P1) — No string-length limits on the wire ⇒ the Postgres one-var swap is broken
Columns are `String(64/128)` but SQLite ignores lengths and the pydantic contract sets
none. Confirmed: a 500-character handle registers fine (stored full length). On Postgres
the same payloads raise `DataError` → unhandled 500s, so the advertised
"switch DB = one env var" claim (CLAUDE.md invariant 3) fails on real-world input. Also an
abuse vector: unbounded `handle`, `eventId`, `seed`, `specRef`, version strings.

**Fix:** add `max_length` to every string field in `contract.py` matching its column:
`fingerprint/event_id/handle` 64, `seed/spec_ref/manifest_hash/recovery_code` 128,
`ruleset_version/content_version` 64, `consent_version` 32, `daily_date` 16,
`class_id/foe_id` 64, `result/kind` already `Literal`. For `handle` additionally:
`min_length=1`, strip surrounding whitespace, and a charset rule — suggest
`^[A-Za-z0-9][A-Za-z0-9 _\-]{0,31}$` (32 chars max for display sanity) — **[SEAM:
set-core]** confirm the client's registration UI matches whatever rule lands.
**Test:** 65-char fingerprint → 422; the §2 repro handle → 422; a normal handle passes.

### B6 (P2) — `schemaVersion` is stored but never asserted
CLAUDE.md invariant 5 says "versioning asserted on every record", and ingest checks
`ruleset_version`/`content_version` non-empty — but `schemaVersion: 999` is accepted
(confirmed). The server is storing payloads in shapes it does not claim to understand.

**Fix:** in `ingest_records`, reject records whose `schema_version` is not in the
supported set (`{settings.schema_version}` today) with
`{reason: "unsupported-schema-version", terminal: true}`. Terminal is correct: retrying
cannot fix it; the (future, newer) client will re-emit under the new schema after its own
migration story. Document the new reason string in SERVICE-RESPONSE.md.
**Test:** `schemaVersion: 2` record → rejected terminal; `1` passes.

---

## 2. Security & abuse hardening

### S1 (P1) — Recovery codes: 390k keyspace, cross-account collisions, O(n) unsalted scan
`app/auth.py:26-47` + `app/services/identity.py:61-69`. Three compounding problems:
1. **Entropy:** 4 words from a 25-word list = 25⁴ = 390,625 codes. With no rate limiting
   (S2), online enumeration of *some* account is a weekend script.
2. **Collisions route to the wrong account:** codes are generated randomly with no
   uniqueness check, and `/recover` takes the **first** identity whose hash matches
   (`identity.py:64-68`). Birthday math: ~1% collision probability at ~90 identities,
   >50% at ~740. A collision means player X's recovery code silently rebinds player Y's
   account (whichever the scan finds first) — account takeover by accident.
3. **Mechanics:** unsalted fast SHA-256 over a tiny keyspace (trivially reversible if the
   DB leaks), and every `/recover` call loads and hashes **every identity row**.

PROGRESS.md already tracks pieces of this ("Pre-public hardening"); this section is the
concrete design.

**Fix (one coherent change):**
- Generate codes as 4 words from the EFF long list (7,776 words) → 7776⁴ ≈ 3.6×10¹⁵, or 6
  words from a curated ~100-word flavor list if the fantasy vocabulary matters (10¹²).
- Require the **handle** in `RecoverRequest` (additive optional→required is a wire change:
  add it optional now, client always sends it, enforce later — **[SEAM: set-core]**).
  Scope the lookup to that identity: kills the O(n) scan *and* makes cross-account
  collision structurally impossible (a colliding code no longer matches "anyone").
- Hash with a per-identity salt (`sha256(salt || code)`, salt stored beside the hash) or
  HMAC with a server key. A KDF (argon2) is optional once entropy is real; don't add a
  dependency for it in the MVP.
- Migration: existing hashes can't be re-derived. Ship as: new registrations use the new
  scheme; `/recover` tries new-scheme first, falls back to legacy global scan until a
  cutoff. (Corpus is tiny today — simply regenerating/notifying is also defensible.)
**Test:** recover with handle+code succeeds; wrong handle + valid code fails; two
identities forced onto the same code (test seam: inject the code) each recover only
themselves.

### S2 (P1) — No rate limiting anywhere
`/register` (unauthenticated) allows handle-squatting and row-spam; `/recover`
(unauthenticated) is the brute-force surface for S1; `/ingest` is authenticated but
unthrottled. There is no middleware and no documented reverse-proxy expectation.

**Fix:** add `slowapi` (or a ~40-line in-app token bucket keyed on client IP — fewer deps,
fits house style): suggest `/register` 5/hour/IP, `/recover` 5/hour/IP, `/ingest`
60/min/token. Return 429 (the client treats non-2xx as retry-later; a `Retry-After` header
is a bonus). Document that self-hosters behind a proxy should also cap there.
**Test:** N+1th call within window → 429; window expiry restores service.

### S3 (P2) — Request body size is uncapped; `actions` is an unbounded opaque blob
`max_batch` caps record *count*, not *bytes*. A single record's `actions` array can be
arbitrarily large (uvicorn does not limit body size); a hostile registered client can fill
the disk. The opaque-store-and-forward invariant means nothing inspects it either.

**Fix:** two layers: (1) a lightweight ASGI middleware rejecting `Content-Length` over,
say, 10 MB with 413; (2) pydantic caps: `actions` `max_length=50_000` items and reject any
single record whose serialized size exceeds ~1 MB (validator using
`len(json.dumps(...))`). Numbers are generous vs. real runs — **[SEAM: set-core]** confirm
a worst-case deep delve's action count and set limits at ~10× that.
**Test:** oversized body → 413; oversized single record → 422/reject; a realistic large
run passes.

### S4 (P2) — Bearer tokens stored in plaintext
`app/models/identity.py:30` stores the raw token; a DB leak (or a stray admin-panel
extension) is full account takeover for every player. Cheap to fix now, annoying after
launch.

**Fix:** store `sha256(token)` in the column (rename via migration or reuse), look up by
hash in `require_identity` (`app/auth.py:55-65`). The unique index moves to the hash. No
wire change; issued tokens are unchanged. Existing rows: one-time migration can't recover
raw tokens — hash-in-place is impossible; either force re-recover (corpus is dev-only
today: acceptable) or dual-read during a transition.
**Test:** register → token authenticates; DB row does not contain the raw token.

### S5 (P3) — Admin panel: default `changeme` + HTTP Basic with no transport story
`app/config.py:22-23`. Fine locally; in prod Basic over plain HTTP is credentials in the
clear, and the default password will survive into someone's deployment.

**Fix:** log a loud startup warning (or refuse to serve `/admin`) when
`admin_password == "changeme"` and the bind is non-local; state "HTTPS required in
production" in README's (future) deploy doc.

### S6 (P3) — The daily seed is derivable by anyone, for any date
`app/services/daily.py:28-30`: `sha256(date|ruleset|content)[:16]` — all public inputs. Any
player can precompute next month's boards and practice. Irrelevant while dailies are
personal-bests-only; **fatal for phase-2 leaderboards** (the daily is the leaderboard's
level playing field). Note `/daily?date=` also happily serves any past/future date.

**Fix (roadmap, before leaderboards):** fold an `EMBASSY_DAILY_SECRET` env value into the
hash and clamp served dates to `today ± 1` (UTC). Contract-compatible: the client treats
`seed` as opaque and fetches it — it never derives the seed itself (it derives *selections
from* the seed). Self-hosters set their own secret. Pairs naturally with G6 (persisted
daily roll). **[SEAM: set-core]** none — verify the client truly never recomputes the seed.

---

## 3. Plausible correctness & portability risks (reasoned, not executed)

### C1 (P2) — Concurrent first-time upload of the same `eventId` ⇒ 500, whole batch lost
`ingest_records` is read-then-insert with one commit (`ingest.py:32-63`). Two devices (or a
double-tapped sync) racing the same new `eventId` both pass the pre-check; the second
commit raises `IntegrityError` → unhandled 500 → **every** record in that batch is
un-acked (they'll retry, so no loss, but it's a crash on a legitimate flow). SQLite's
single-writer masks it locally; Postgres will not.

**Fix (portable, no dialect-specific upsert):** wrap each insert in a nested transaction
(`with db.begin_nested(): db.add(row); db.flush()`), catch `IntegrityError` per record and
treat as duplicate-accepted; keep the outer commit. Alternatively catch at commit and
retry once re-running the existing-ID check.
**Test:** monkeypatch/flush-order test simulating the race, or two threads against a
file-backed SQLite in WAL mode.

### C2 (P3) — Naive datetimes: `achievedAt`/`createdAt` have no timezone, and Postgres would change their meaning
Models use `DateTime` (naive) + `func.now()`. SQLite's `CURRENT_TIMESTAMP` is UTC;
Postgres `now()` is the server timezone — so the swap silently changes semantics; and
`BestEntry.achieved_at` serializes as `2026-06-23T19:52:43` with no `Z`, which a JS
`new Date(...)` parses as **local** time.

**Fix:** migrate columns to `DateTime(timezone=True)`, default
`func.now()` (Postgres) / keep as-is for SQLite (batch mode handles the ALTER), and emit
ISO-8601 with explicit UTC offset in responses (`.replace(tzinfo=timezone.utc).isoformat()`
for legacy naive rows). **[SEAM: set-core]** confirm the client parses the new suffix (it
should be a no-op improvement).

### C3 (P3) — Admin `list_runs` date filters: dead at the router, and string-vs-DateTime comparison
`app/services/admin.py:58-61` compares `date_from/date_to` strings to the `created_at`
DateTime column — works on SQLite by string-collation accident; on Postgres `date_to=
"2026-06-23"` casts to midnight and **excludes that entire day**. Moreover
`app/routers/admin.py:125-139` (`api_runs`) never exposes these params — they are dead
code.

**Fix:** either delete the two params, or expose them and parse to `datetime` with
`date_to` treated as end-of-day exclusive (`< date_to + 1 day`). Small, self-contained.

### C4 (P3) — Malformed `EMBASSY_DAILY_FILE` ⇒ every `/daily` request 500s
`daily.py:33-51` — `json.loads` / `DailySpec(**entry)` exceptions are uncaught. An operator
typo in the authored-dailies file takes the whole daily feature down with it.

**Fix:** catch `json.JSONDecodeError`/`ValidationError` in `authored_spec`, log an ERROR
once, and fall back to path-a (`return None`). Optionally validate the file at startup and
refuse to boot on garbage (fail-fast is also defensible — pick one, document it).
**Test:** point `daily_file` at invalid JSON; `/daily` still 200s (or app refuses boot,
per the chosen policy).

### C5 (P3) — Missing-bearer returns 403, not 401
`HTTPBearer(auto_error=True)` (`app/auth.py:52`) returns 403 with no `WWW-Authenticate`
header when the header is absent; an invalid token returns 401. Already noted in
CLAUDE.md's deferred list; the test suite works around it (`assert r.status_code in
(401, 403)`).

**Fix:** `HTTPBearer(auto_error=False)`, raise 401 + `WWW-Authenticate: Bearer` when creds
are `None`. Tighten the test to expect exactly 401.

### C6 (P3) — Duplicate `eventId` within one batch is echoed twice in `accepted`
`ingest.py:55-61` appends per occurrence, so `accepted == ["e4","e4"]`. Harmless to the
pruning client but untidy wire output the test even shrugs at (`count("e4") >= 1`).
**Fix:** dedupe while preserving order (`dict.fromkeys`), tighten the test to `== 1`.

### C7 (P3) — `consentVersion` at registration is recorded, never checked
`identity.py:34-58` stores whatever the client sends. A stale client can "consent" to
text that no longer exists; the consent audit trail then lies. **Fix:** reject
`register` when `req.consent_version != settings.consent_version` with 409/422 and a
distinct message so the client re-prompts with current text. **[SEAM: set-core]** client
should read `consentVersion` from `/health` before registering (it already fetches
`/health` for gating — confirm).

### C8 (P3) — No FK from `run.fingerprint` to `identity`
Deliberate-looking (rebind rewrites both tables in one transaction,
`identity.py:82-88`), but undocumented, and nothing prevents future code from orphaning
runs. **Fix:** either add the FK (note: rebind must then update parent first or use
deferred constraints — more trouble on SQLite) or add one line to `run.py`'s docstring
stating the invariant is maintained manually by `/recover`. Documentation is the cheap,
correct call.

### C9 (P3) — Alembic URL via `configparser` will choke on `%` in Postgres passwords
`alembic/env.py` calls `config.set_main_option("sqlalchemy.url", ...)` — configparser
interpolation treats `%` specially. Escape (`url.replace("%", "%%")`) or pass the URL via
`context.configure(url=...)` directly in the online path too.

---

## 4. Doc–code mismatches & misconceptions

### D1 — `/ingest` is documented as an "upsert"; it is first-write-wins insert-or-skip
CLAUDE.md invariant 4, SERVICE.md §2, and `ingest.py`'s docstring all say "idempotent
batch **upsert**". The code (`ingest.py:53-57`) never updates: a re-sent `eventId` with
*different* content keeps the old row and reports `accepted`. First-write-wins is
arguably the **right** semantics for an append-only event corpus — but then the docs
should say so, because "upsert" tells a future agent it's safe to re-send corrected
records, and it is not. **Fix:** pick one (recommend: keep first-write-wins, records are
immutable events) and align CLAUDE.md/SERVICE-RESPONSE.md/docstring wording.

### D2 — Dead code: `_TERMINAL_REASONS`
`ingest.py:19` is referenced nowhere (`reject()` hardcodes `terminal=True`). Either use it
(assert `reason in _TERMINAL_REASONS` inside `reject`) or delete it. Trivial.

### D3 — The fossilized `reshareSharePlayer` typo (both repos)
TUNING.md's target is "**Reshape** share"; the wire key is `reshareSharePlayer` — in
SERVICE.md §5, `app/services/admin.py:110`, `scripts/seed_demo.py`, **and** the client
(`set-core/src/net/capture.ts:132`, verified). Both sides agree, so nothing is broken;
it's a permanent misspelling in an open blob that every future analysis script will trip
over. **Fix (coordinated, optional):** client emits both keys for a transition window,
server aggregates `reshapeSharePlayer` with fallback; or just document the typo as
canonical in TUNING.md's reference copy. **[SEAM: set-core]** either way.

### D4 — SERVICE.md §2 promises a handle-**change** flow; nothing provides one
"Server needs handle-availability + claim + **change** + rebind flows" — §4's endpoint
table (built faithfully) has no change endpoint, and no doc records the cut. **Fix:**
one line in SERVICE-RESPONSE.md/PROGRESS.md declaring handle-change deferred to phase 2
(or add `POST /me/handle` guarded by the bearer + availability check — small, but adds
surface; deferral is fine, just make it explicit).

### D5 — `README` privacy posture vs. no erasure path
README says collection is "opt-in and disableable client-side", but once uploaded there is
no deletion mechanism at any level (player or admin panel; only raw `sqlite3`). Opt-out
stops *future* collection only. See G7 for the product fix; minimally, the README should
state data-deletion is by operator request until an endpoint exists.

---

## 5. Simplification & code quality (all small; do opportunistically)

- **A1** `tests/*`: the `_auth(token)` helper is copy-pasted into six files — move to
  `conftest.py`.
- **A2** `app/routers/admin.py:160-176`: the hand-written camelCase dict for `api_runs`
  duplicates the field-name mapping that `contract.py` already owns. Add a small
  `RunSummary(_Wire)` schema (or reuse pieces of `RunRecord`) and serialize with
  `model_dump(by_alias=True)` so field names have one home. (Admin is out-of-contract, so
  this is purely DRY, not a wire change.)
- **A3** `app/services/admin.py:45`: the `["\x00none"]` sentinel for "handle matched no
  fingerprints" — use `sqlalchemy.false()` (`stmt.where(false())`) instead.
- **A4** `app/services/bests.py:95-99` `_field_for` re-scans `_CRITERIA` per entry — carry
  the `_Criterion` (not just its name) in the `best` dict key/value. Cosmetic.
- **A5** `instrument_aggregates` (`admin.py:102-131`) loads every run's JSON into memory.
  Fine at MVP scale; when it hurts, aggregate in SQL over generated columns or accept
  sampling. Leave a comment, don't build it now.
- **Anti-recommendation:** the service-module layout (`services/*.py` as plain functions
  taking `db` first) is exactly right for this size. Do **not** introduce repositories,
  DI containers, or async SQLAlchemy; the biggest quality risk to this repo is additive
  architecture.

---

## 6. Product & game-design gaps (the seam view)

### G1 (P2-product) — Daily streaks: the data exists, the retention loop doesn't
The single strongest cheap addition. The server already stores every daily run keyed by
`dailyDate`; a **streak** (consecutive UTC days with a daily run, and/or with a daily win)
is the classic daily-challenge retention mechanic and is pure read-model — no schema
change. **Proposal:** extend `/me/bests` with an additive `daily: {streak, bestStreak,
playedToday}` object, or a new `GET /me/daily` — additive either way, `schemaVersion` 1.
**[SEAM: set-core]** the Daily Dispatch UI needs a place to show it.

### G2 (P2-product) — `/me/bests` grows without bound
One entry per (criterion × class × foe × dailyDate) **forever** — a year of dailies ≈
1,000+ entries in every response, and the client presumably shows a handful. **Proposal:**
additive query params: `?kind=delve|daily`, `?since=YYYY-MM-DD` (filters daily slices),
default unchanged for compatibility. Decide the client's actual display needs first
**[SEAM: set-core]**.

### G3 (design question, cross-repo) — `deepest-delve` sliced per (class × foe) is conceptually odd
Depth is a property of the *run/dungeon*, not of the headline foe; slicing depth by `foeId`
fragments one "how deep have I gone" number into per-foe shards (your 12-depth run only
counts against the foe you happened to headline). Likely intent: `deepest-delve` per
**class** only. This is a read-model change (bests keying), not a wire change — but it's a
**game-design decision for the set-core side** to ratify. Flag, don't fix unilaterally.

### G4 (P3-product) — Daily `criteria` are static and undifferentiated
Every day advertises the same three criteria. The authored-daily channel (`spec.params`)
already gives operators per-day knobs; documenting a convention like
`params: {featuredCriterion: "fastest-clear"}` would let dailies have personality with
zero schema work. Pure documentation + client-read **[SEAM: set-core]**.

### G5 (P2-ops/product) — The version-equality gate is operationally brittle
Dailies require exact `rulesetVersion`/`contentVersion` equality with two placeholder
`0.0.0-dev` strings that both repos must bump **in lockstep at a UTC boundary, manually**.
The failure mode of forgetting: every player sees "unavailable: update to play" (or worse,
plays a mismatched board silently if versions accidentally match). Already on the
cross-repo deferred list ("real version tokens"). **Roadmap shape:** derive both tokens
from a build/content hash in the client's release pipeline and inject the same values into
the Embassy deploy env — one release artifact, two consumers. Design lives with set-core's
build; the server side is already just env config. **[SEAM: set-core]**

### G6 (P3, design option) — Pin the day's roll server-side to kill the mid-day-re-roll footgun
Today `/daily` is a pure function of config, so an env bump mid-day re-rolls the board
(documented as "don't do that"). Alternative: on first request for a date, persist
`(date, seed, versions, spec)` to a `daily_roll` table and serve that thereafter.
Costs the "pure function" elegance; buys immunity to operator error, an audit trail, and
the natural attachment point for S6's secret and future authored dailies. Reasonable to
defer; record the option so it's weighed once real versions land.

### G7 (P2-privacy) — No data-erasure path
Privacy-first posture needs a deletion story: **proposal** `DELETE /me` (bearer-authed)
that removes the identity row and all runs for the fingerprint (or tombstones the handle
if handle-recycling is unwanted). Also gives the admin panel a per-identity delete. Client
UX ("Leave the Embassy") is **[SEAM: set-core]**. Cheap now, reputationally expensive to
lack later.

### G8 (P3-DX) — No `GET /me`
The client can only validate a stored token by calling `/me/bests` and inferring. A tiny
`GET /me → {handle, fingerprint, consentVersion, createdAt}` improves client boot/refresh
flows and is the natural home for G1's streak block if a separate endpoint is preferred.

---

## 7. Operational readiness (pre-deploy checklist material)

- **O1:** SQLite is not in WAL mode and the deploy story assumes one uvicorn worker —
  neither is stated anywhere. Add a connect-event PRAGMA (`journal_mode=WAL`,
  `busy_timeout=5000`) for SQLite engines in `app/db.py`, and a README line: "SQLite =
  single process; use Postgres for multi-worker."
- **O2:** No structured logging or request metrics (already tracked in PROGRESS.md).
  Minimal bar: uvicorn access logs on + one log line per ingest batch (count
  accepted/rejected) + exceptions with fingerprint context.
- **O3:** Hosting target + deploy doc still open (PROGRESS.md). The doc should carry: the
  HTTPS requirement (S5), reverse-proxy body cap (S3), env checklist including
  `EMBASSY_CORS_ORIGINS` for the deployed client origin, and backup policy for the DB
  file.
- **O4:** CI never boots the app against **Postgres**; the portability invariant is
  test-asserted only on SQLite. Add a CI job with a `postgres` service container running
  `alembic upgrade head` + the pytest suite with `EMBASSY_DATABASE_URL` pointed at it.
  This job would have caught B5/C2/C3 class issues mechanically.

---

## 8. Suggested roadmap (ordered; each item is one agent-sized task)

**Phase 1 — correctness of what exists (no wire changes beyond validation; do first, in order):**
1. B5 string bounds + handle charset (unblocks the Postgres claim; biggest blast-radius fix)
2. B2 outcome bounds
3. B4 kind/dailyDate cross-validation
4. B1 fingerprint-scoped idempotency + `event-id-conflict` reject
5. B6 schemaVersion assertion
6. B3 daily date normalization
7. C1 per-record IntegrityError handling
8. D1 upsert wording, D2 dead constant, C6 accepted-list dedupe, C5 401-vs-403, A1-A4
   (bundle as one cleanup PR)

**Phase 2 — pre-public hardening (before any non-friends deployment):**
9. S1 recovery-code scheme (entropy + handle-scoped recover + salted hash)
10. S2 rate limiting (`/register`, `/recover`, `/ingest`)
11. S3 body-size caps
12. S4 token hashing
13. O1 WAL + worker note, O4 Postgres CI job, S5 changeme guard
14. G7 `DELETE /me` (+ README privacy wording, D5)

**Phase 3 — product depth (coordinate with set-core session):**
15. G1 daily streaks (additive read-model)
16. G2 bests filtering params
17. G5 real version tokens (client-driven; server is ready)
18. G3 deepest-delve slicing decision (game-design ratification first)
19. C2 timezone-aware datetimes (fold into any migration Phase 2/3 already requires)
20. S6 + G6 daily secret / persisted roll + date clamp (prerequisite for leaderboards)
21. D3 reshape-typo decision, D4 handle-change deferral note, G4 featured-criterion
    convention, G8 `GET /me`

**Standing rules for executors:** run `make test && make lint && make openapi && git diff
--exit-code openapi.json` after every task; new gates need a proving test in the matching
`tests/test_*.py` (house rule: acceptance criteria map 1:1 to tests); update PROGRESS.md
as items land; anything tagged **[SEAM: set-core]** needs the mirrored change (or explicit
ack) in `set-core/src/net/contract.ts` and the handshake docs before merging.

---

## 9. Verification playbook (how the confirmed findings were reproduced)

All probes used the conftest pattern (temp SQLite engine + `app.dependency_overrides[get_db]`,
`TestClient(app)`), so they can be turned into regression tests nearly verbatim:

- **B1:** register Alice (`fp-a`) and Bob (`fp-b`); Alice ingests `eventId:"e1"`; Bob
  ingests his own record as `"e1"` → response `accepted:["e1"]`, Bob's `/me/bests` empty.
- **B2:** ingest `outcome.terms = -999` → accepted; `/me/bests` reports `fewest-terms:
  -999`.
- **B3:** `python -c` on `app.services.daily._seed_for` — `'2026-7-1'` and `'2026-07-01'`
  yield different seeds; `validate_date` passes both.
- **B4:** ingest `context: {kind:"daily", dailyDate:null, terms:3}` → its value replaces
  the caller's **delve** `fewest-terms` best (slice key collapses to `None`).
- **B5:** `POST /register` with a 500-char handle → 201, stored at full length on SQLite.
- **B6:** ingest `schemaVersion: 999` → `accepted`.

S1's collision math, C1's race, and the Postgres behaviors (B5's `DataError`, C2/C3) were
reasoned from code and dialect semantics, not executed — the Postgres CI job (O4) is the
mechanical check for that whole class.

---

## 10. Cross-repo coordination ledger ⚠ (for the workspace-level agent)

This analysis covered **only** `crawl-records`; a sibling session is reviewing `set-core`.
A coordinator operating at the `set-crawl/` workspace level should reconcile this section
against that session's findings and sequence any two-sided change as **one** unit of work
(server contract → `make openapi` → mirror `set-core/src/net/contract.ts` → handshake docs).

**Two items found here that CANNOT be resolved in this repo alone — surface these to the
set-core session explicitly:**

1. **`reshareSharePlayer` is a fossilized typo living in BOTH repos (D3).** TUNING.md's
   metric is "**Reshape** share"; the misspelled wire key is emitted by the client
   (`set-core/src/net/capture.ts:132`, verified this session, with its test asserting the
   misspelling at `capture.test.ts:59`) and consumed by this server
   (`app/services/admin.py:110`, `scripts/seed_demo.py`, SERVICE.md §5). The two sides
   agree today, so nothing is broken — but any unilateral rename on either side silently
   zeroes the instrument aggregate (the blob is open/opaque; there is no schema error to
   catch it). **Decision needed:** rename in lockstep (client emits both keys for a
   transition window, server aggregates new-key-with-fallback), or canonize the typo with
   a note in both repos' TUNING.md. Either is fine; drifting is not.

2. **`deepest-delve` bests are sliced per (class × foe) — a game-design call this repo
   should not make alone (G3).** Depth is a property of the run/dungeon, but the read
   model (`app/services/bests.py:69-71`) shards it by headline `foeId`, so "my deepest
   delve" fragments across foes. The likely-intended slice is per **class** only — but
   that is a design question about what a "best" means in SET.crawl, owned by the game
   side. Server-side it is a small read-model change (bests keying), no wire break;
   the client's Hall of Records display assumptions must match whatever is ratified.

**Full seam-tagged index (items elsewhere in this doc that touch set-core):**
B5 (handle charset rule ↔ registration UI) · S1 (handle added to `RecoverRequest` ↔
recover UX) · S3 (actions-size cap ↔ worst-case run size) · S6 (verify client never
recomputes the daily seed) · C2 (timezone suffix ↔ client date parsing) · C7
(consentVersion check ↔ client reads `/health` before register) · D3 (above) · G1
(streaks ↔ Daily Dispatch UI) · G2 (bests filters ↔ display needs) · G3 (above) · G4
(featuredCriterion convention) · G5 (real version tokens — client build pipeline owns the
hash; server is env-ready) · G7 (`DELETE /me` ↔ "Leave the Embassy" UX).
