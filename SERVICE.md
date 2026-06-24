# SERVICE.md — the Embassy service (seed spec for the new repo)

> **Status:** 🟡 specced, not built. This document is the **seed** for a *separate* repository
> (working name **`set-embassy`** / "the Embassy service"). It is written FOR the agent that will
> stand up that repo. Read it top to bottom, build to the **Acceptance criteria** (§8), and on
> completion write the **response document** described in §10 back into this repo.
>
> Companion context lives in this repo: `CLAUDE.md`, `PROJECT.md` (the deterministic generator —
> this is *why* daily content can be a seed, not a payload), `CRAWL-DESIGN.md` (run loop, foe/class
> taxonomy, dev instruments), `TUNING.md` §"Dev-instrument design targets" (the metrics we care about),
> `MODDING.md` (the YAML→JSON content pipeline that stays the authoring home).

## 1. What this is (and the one insight that shapes everything)

The Embassy service is the **online backend** for SET.crawl: an opt-in, fully-disableable HTTP/JSON
API that (a) **ingests gameplay run records** for balance analysis, (b) serves a deterministic
**daily challenge**, and (c) returns a player's **personal bests**. It is the foundation the
eventual leaderboards / daily content download / cross-player records grow from — but those are
**out of scope for the MVP** (§7).

**The insight:** the game core is a *pure deterministic generator from a seed/spec* (`PROJECT.md`).
Therefore:
- Daily content ships as a **tiny seed + version pin**, not a fat payload. The client regenerates
  the identical board locally.
- If a run's **ordered action stream** is logged alongside its seed + versions, the run is
  **deterministically replayable server-side**. The *same* event log that feeds balance analysis
  is the future leaderboard's **anti-cheat substrate**. So the event schema is designed
  **replay-ready now**, even though replay-verification itself is deferred.

This service is also **open-source and self-hostable**: anyone can run their own instance for their
friends; ours is just the default/official one. The client carries a configurable server URL.

## 2. Settled decisions (from the 2026-06-22 interrogation)

### Repo & stack
- **Decision:** New, separate repository. **FastAPI + pydantic + SQLAlchemy + Alembic.**
  **SQLite first**, written so the DB is a config swap to **Postgres** (and later **Redis** for hot
  read paths) with no rewrite. Server emits **OpenAPI**; the game client generates its TS network
  types from that schema (`openapi-typescript` or equivalent) — server is the contract source of truth.
- **Rationale:** Keeps the game client's **runtime deps empty** (`MODDING.md` invariant); different
  language / deploy / security surface. FastAPI's auto-OpenAPI solves the cross-language contract-drift
  problem; Python is open-source-friendly for self-hosters; SQLite-first is zero-ops to start.
- **Implications:** A codegen step must exist in the client's toolchain (deferred to client work, but
  the server MUST keep its OpenAPI schema accurate and stable — see §8).

### Identity
- **Decision:** Two-part identity. (1) A **fingerprint** — a client-generated UUID (`crypto.randomUUID()`),
  written once into player data at first run, **never read by game logic**, used only as the server key.
  (2) A **handle** — chosen at registration, **globally unique, first-come claimed** on the official
  instance. A **recovery code** is issued at registration so a new install/device can **re-bind** a new
  fingerprint to the existing identity.
- **Rationale:** Fingerprint = anonymous stable key with zero gameplay coupling. Unique handle = clean
  leaderboard identity. Recovery code = survives reinstall without passwords/accounts.
- **Implications:** Server needs handle-availability + claim + change + rebind flows. The client needs a
  registration UX (first Embassy visit) that surfaces and stores the recovery code.

### Consent
- **Decision:** **Consent is the registration.** First Embassy visit on an *unmodded* game → set handle
  + grant consent in one step. Thereafter **every run auto-uploads** for analysis; only the player's
  **best per criterion** is displayed back. **Declining ⇒ the Embassy is closed** (no upload, no daily,
  no bests); the game remains fully playable offline; the player can re-enter and opt in anytime.
- **Rationale:** Privacy-first, single clear gate, no silent collection.
- **Implications:** No "unranked daily" code path in the MVP. Consent state is recorded server-side
  (timestamp + consent version) and locally.

### Mod-gate (record integrity)
- **Decision:** **Honor-system `modded` flag** for the MVP. If any modded content is loaded the client
  sets `modded: true` and **the Embassy is disabled entirely** (no requests); the server also rejects/
  filters any payload with `modded: true`. Mods don't exist yet, so this is an explicit placeholder.
- **Rationale:** Zero effort now; keeps modded runs out of the official corpus by construction.
- **Implications:** The integrity field is **structured for upgrade** — see `integrity` in §5 — so it
  becomes a content-manifest **hash** later **without a schema break**. Self-hosted instances set their
  own accepted manifest(s).

### Metrics grain
- **Decision:** **Replay-ready event log.** Each run uploads `seed + rulesetVersion + contentVersion +
  an ordered action stream (every player decision) + a dev-instrument summary + outcome`.
- **Rationale:** One corpus serves balance analysis *and* future leaderboard anti-cheat; no
  re-instrumentation when boards land.
- **Implications:** Client must emit a complete, ordered, replayable action stream (client-side work).
  Server stores it append-only; replay-verification is built later.

### Daily challenge
- **Decision:** `GET /daily` returns `{ date, seed, specRef, rulesetVersion, contentVersion, criteria }`.
  The client regenerates the board locally. If the client's ruleset/content version ≠ the challenge's,
  the daily is **unavailable** ("update to play today"). Daily is **server-authored/generated** but
  **references only content that already exists in the client** (no content shipped).
- **Rationale:** Tiny payload, deterministic, fair (everyone on version vX gets the identical board),
  trivially replay-verifiable later.
- **Implications:** Server owns the daily-roll logic + a deterministic, date-addressable seed scheme.

### Bests
- **Decision:** **Server-computed.** The server ingests all runs and computes the player's best per
  criterion; the Embassy fetches them. MVP criteria: **fewest-terms**, **fastest-clear** (real time),
  **deepest-delve**, sliced **per (foe × class)**. Daily-challenge bests are a slice keyed by `date`.
- **Rationale:** Single source of truth; directly extends to cross-player boards later.
- **Implications:** The bests query is the seed of the leaderboard read model.

### Upload protocol
- **Decision:** **Outbox + ack + idempotency.** Every event/record carries a client-generated stable
  `eventId` (UUID). `POST /ingest` is an **idempotent batch upsert** keyed on `eventId`. The client
  prunes local records **only after the server acks those specific IDs**.
- **Rationale:** A failed ack after a successful write must not double-count. Lets the client delete
  uploaded records to avoid local bloat (the user's explicit goal).
- **Implications:** Server dedupes on `eventId`; `/ingest` returns the set of accepted IDs.

### Storage / hosting
- **Decision:** SQLite (JSON columns for event payloads) behind SQLAlchemy + Alembic; Postgres-ready;
  Redis later for hot reads. Hosting target left to the new repo's first decision (Fly/Railway/Render-class).
- **Rationale:** Cheapest start, clean upgrade path; low write volume (single-player).

## 3. Versioning (assert everywhere)

Every payload carries explicit versions; **never** infer them:
- `schemaVersion` — the wire-format version of *this* payload type (bumped per breaking shape change).
- `rulesetVersion` — the game-rules/engine version that produced/validates a run (determinism pin).
- `contentVersion` — the content-registry version (which foes/classes/gear exist).
- `consentVersion` — the consent text the player agreed to.

Daily correctness and replay both **depend on `rulesetVersion` + `contentVersion` matching**. The server
must store these on every record and refuse to compute a daily board guarantee across mismatched versions.

## 4. API surface (MVP)

JSON over HTTPS. All write endpoints require a valid registered identity (fingerprint + a session/bearer
token issued at registration — keep auth minimal: a bearer token bound to the fingerprint is enough).

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health` | Liveness + advertised `rulesetVersion`/`contentVersion`/`schemaVersion`/`consentVersion`. |
| `GET`  | `/handle/available?name=` | Handle availability check (unique-claim flow). |
| `POST` | `/register` | Claim handle + record consent → returns identity token + **recovery code**. |
| `POST` | `/recover` | Re-bind a new fingerprint to an existing identity via recovery code. |
| `POST` | `/ingest` | **Idempotent batch** of run records (event log + summary). Returns accepted `eventId`s. |
| `GET`  | `/me/bests` | The caller's best per criterion (per foe × class; daily slice by date). |
| `GET`  | `/daily?date=` | The deterministic daily challenge descriptor (defaults to "today" UTC). |

Out of scope endpoints (documented as **phase 2+**, do not build): cross-player leaderboards,
content/asset download, run-replay verification, account/social features, art/sprite delivery.

## 5. Data shapes (authoritative sketch — pydantic models are the real source)

> These are the *intent*. The new repo defines pydantic models + the OpenAPI schema; keep field names
> stable once published or bump `schemaVersion`.

```jsonc
// POST /register
{ "fingerprint": "uuid", "handle": "Ashling", "consentVersion": "1",
  "client": { "rulesetVersion": "...", "contentVersion": "..." } }
// → { "token": "...", "recoveryCode": "word-word-word-word", "handle": "Ashling" }

// A single run record (the unit batched into POST /ingest)
{
  "eventId": "uuid",                 // idempotency key, client-generated
  "fingerprint": "uuid",
  "schemaVersion": 1,
  "rulesetVersion": "...",
  "contentVersion": "...",
  "integrity": { "modded": false, "manifestHash": null },  // hash slot reserved for the future gate
  "context": {
    "kind": "delve" | "daily",
    "dailyDate": "2026-06-22" | null,
    "classId": "pyromancer",
    "foeId": "emberlord" | null,     // the headline/boss foe for slicing bests
    "seed": "...", "specRef": "..."  // enough to regenerate the run's boards
  },
  "outcome": { "result": "win" | "loss" | "flee", "terms": 37,
               "realTimeMs": 184210, "depthReached": 6 },
  "actions": [ /* ordered, replay-ready: every player decision + the inputs needed to replay */ ],
  "instruments": {                   // the dev-stat summary (TUNING.md targets)
    "setsMatched": 0, "setsPerRound": 0.0, "reshareSharePlayer": 0.0,
    "trapSpringRate": 0.0, "abilityActivations": { /* abilityId: count */ },
    "tacticsUsage": { "standGround": 0, "maneuver": 0, "charges": 0 },
    "transmutes": 0
    /* extend freely — the server stores instruments as an open JSON object */
  }
}

// GET /daily → the descriptor the client regenerates from
{ "date": "2026-06-22", "seed": "...", "specRef": "...",
  "rulesetVersion": "...", "contentVersion": "...",
  "criteria": ["fewest-terms", "fastest-clear", "deepest-delve"] }

// GET /me/bests
{ "bests": [ { "criterion": "fewest-terms", "classId": "pyromancer",
              "foeId": "emberlord", "value": 31, "eventId": "uuid",
              "achievedAt": "..." } /* ... */ ] }
```

**Storage model:** an `identity` table (fingerprint PK, handle UNIQUE, recovery-code hash, consent
version+timestamp, token); a `run` table (eventId PK for dedupe + the structured columns above + a JSON
column for `actions` and `instruments`); a derived `bests` read model (recompute on ingest, or compute
on read for MVP — your call, document it). Keep `actions` opaque/append-only; nothing in the MVP parses it.

## 6. Client-side companion work (NOT this repo — for awareness / the contract)

The new repo doesn't build these, but its API must serve them. Logged here so the contract is designed
against real client needs (tracked separately in this repo's `TODO.md`):
- A **fingerprint + recovery** field on a new **account-level save key** (envelope `{ v, ... }` pattern,
  mirroring `src/ui/save.ts`'s planned separate bank store — **not** on `SavedChar`).
- A **local metrics outbox** (append per run; prune on ack) on its own save key.
- The **only** network module (e.g. `src/net/embassy.ts`), hard-gated by config; engine/core stay pure.
- A complete, ordered, **replay-ready action recorder** in the engine.
- The **Embassy** town scene: register/consent flow (+ recovery-code display), daily fetch+regenerate,
  bests display, version-mismatch handling, mod-detected disabled state.
- The OpenAPI→TS **codegen step** in the client toolchain.

## 7. Scope boundaries (explicitly NOT in the MVP)

- ❌ Cross-player leaderboards (only **personal** bests).
- ❌ Content / asset / sprite download (daily references client-resident content only; art is emoji
  placeholders project-wide for now).
- ❌ Server-side **replay verification** (the data is *captured* replay-ready; the verifier is later).
- ❌ Real anti-cheat / signed content (honor-system `modded` flag only).
- ❌ Social features, accounts beyond fingerprint+handle+recovery, friends, chat.

## 8. Acceptance criteria (build to these — strict)

A delivery is complete only when **all** of the following hold:

1. **Stack:** FastAPI + pydantic + SQLAlchemy + Alembic; runs on **SQLite** out of the box with a
   documented **one-config-change** path to Postgres. No Postgres-only SQL in the MVP.
2. **OpenAPI:** the service emits a valid OpenAPI schema covering every §4 endpoint, and
   `openapi-typescript` (or equiv) generates a clean client without hand-edits. The schema is committed
   as an artifact and regenerable via a documented command.
3. **Idempotency:** re-`POST`ing the same `eventId`(s) to `/ingest` never double-counts; a test proves
   duplicate + partial-batch re-upload converges to one stored record each, and the response reports the
   accepted IDs.
4. **Versioning:** every stored run persists `schemaVersion`, `rulesetVersion`, `contentVersion`; `/daily`
   refuses to assert board-equality across mismatched versions; `/health` advertises current versions.
5. **Identity:** handle uniqueness is enforced (concurrent-claim safe); `/recover` re-binds a fresh
   fingerprint to an existing identity via the recovery code; recovery codes are stored **hashed**.
6. **Consent gate:** no run is accepted without a registered, consented identity; a `modded: true`
   payload is rejected; tests cover both rejections.
7. **Bests:** `/me/bests` returns correct per-criterion bests for (fewest-terms, fastest-clear,
   deepest-delve) sliced per (foe × class), with a daily slice by date; ties resolved deterministically
   (document the rule).
8. **Daily determinism:** `/daily` is a pure function of `date` (+ the active ruleset/content version);
   the same date returns the same descriptor; a test pins this.
9. **Self-host:** a fresh clone runs with one documented command (e.g. `make dev` / `uvicorn ...`) on
   SQLite with no external services; the server URL/instance config is documented for client pointing.
10. **Tests + migrations:** pytest suite green; Alembic migrations apply cleanly from empty and are
    reversible; CI config (or a documented test command) present.
11. **Privacy posture:** no PII is collected beyond the chosen handle; the README states what is stored
    and that collection is opt-in/disableable client-side.
12. **No content leakage:** the service ships **no** game content/balance numbers; it references content
    by id + version only (keeps `MODDING.md`/`TUNING.md` as the single authoring home).

## 9. Open questions to resolve IN the new repo (flag, don't block)

- Bearer-token shape + rotation (keep minimal; document it).
- Daily seed scheme: exact date→seed derivation + UTC rollover boundary.
- Bests recompute-on-ingest vs compute-on-read (pick per simplicity; document).
- Hosting target + a deploy doc.
- Rate limiting / payload size caps for `/ingest` (single-player volume is low, but cap it).

## 10. Required response document (write this back to THIS repo on completion)

When the service exists and meets §8, **write `SERVICE-RESPONSE.md` into the `set-core` repo root**
(this repo) addressed back to the SET.core maintainers/agent. It MUST contain:

1. **Repo location** (URL/path) + how to run it locally (the one command) + how to run tests.
2. **The committed OpenAPI schema** path + the exact client codegen command to generate TS types.
3. **The final contract**: any field/name deviations from §5, with rationale, and the resulting
   `schemaVersion`(s).
4. **Endpoint reference**: each §4 endpoint's final request/response, auth requirements, and error codes.
5. **A §8 checklist** with each criterion marked met (with the proving test name) or explicitly deferred
   (with reason).
6. **Integration steps for the client**: env/config keys (server URL, enable flag), the register→ingest→
   bests→daily call sequence, and the version-mismatch + mod-disabled behaviors the client must honor.
7. **Open questions resolved** (from §9) and any **new** ones that surfaced.
8. **What's stubbed vs real**, and the seam where phase-2 (leaderboards / replay-verify / content
   download) plugs in.

Keep it terse and factual in the house style of this repo's docs. That document is the handshake that
lets the client work (§6) begin.
