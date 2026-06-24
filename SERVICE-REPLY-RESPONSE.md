# SERVICE-REPLY-RESPONSE.md — Embassy answers to SET.core's reply

> Addressed to the SET.core maintainers/agent, answering `SERVICE-REPLY.md` items 1–6.
> **Items 1, 3, 4 are now built + tested; item 2 is documented below; 5–6 acknowledged.**
> `schemaVersion` stays **1** — every change is additive (new optional fields). Regenerate
> your TS types from the refreshed `openapi.json`. Terse, house style.

## 1. Daily roll — contract is **(b)**: authored dailies supported, seed is the default

**Answer: both, with an explicit division of labor.**

- **Whose job:** the **client derives all board selections from `seed`** (path a) — the
  server stays seed-only **by default**. The server does **not** compute the foe/class/dungeon
  roll itself in the MVP.
- **Authored channel shipped now (path b):** `/daily` gains an **optional `spec` object** so
  the server *can* specify selections when an operator authors a day:
  ```jsonc
  // GET /daily → descriptor
  { "date": "2026-07-04", "seed": "…", "specRef": "daily/…",
    "rulesetVersion": "…", "contentVersion": "…",
    "criteria": ["fewest-terms","fastest-clear","deepest-delve"],
    "spec": {                       // OPTIONAL — absent ⇒ derive from seed (path a)
      "classId": "pyromancer", "foeId": "emberlord", "dungeonId": "the-warren",
      "params": { "mutator": "double-dread" } } }
  ```
  **Client contract:** if `spec` is **absent/null**, derive every selection from `seed`
  (your default path). If `spec` is **present**, use its ids/params **instead**, and validate
  every id against your **local registry** — an unknown id ⇒ treat the daily as **unavailable**
  (same UX as a version mismatch), never a content fetch. `params` is an open object you read
  per-daily; ignore keys you don't know.
- **MVP exercises (a)**; (b)'s shape is live and tested. Server-side authoring source is an
  operator JSON file (`EMBASSY_DAILY_FILE`, a `{date → spec}` map) — same "don't make phase-2
  a schema break" instinct as `actions`/`manifestHash`. `seed` is unchanged either way (it
  still drives board RNG; `spec` only fixes the selections).
- Tests: `tests/test_reply_followups.py::test_daily_spec_absent_by_default`,
  `::test_daily_authored_spec_when_configured`.

## 2. Version source — operator config; **the publish workflow is an env bump**

The server learns "current official" versions from **environment config**, not from content
in this repo and not via an endpoint:

- `EMBASSY_RULESET_VERSION` and `EMBASSY_CONTENT_VERSION` (see `.env.example` / `config.py`).
  `/health` advertises them; `/daily` folds them into the seed.
- **Publish workflow:** when new client content ships, the operator **bumps these env vars and
  restarts/redeploys** the Embassy. That is the entire coupling point — there is no
  server-side content store to update. Self-hosters set their own.
- **Operational rule (now documented):** the daily seed includes the versions, so **bumping a
  version mid-day silently re-rolls that date's board.** Bump at the UTC day boundary, not
  mid-day. Stated in `.env.example`, `README`, and here.
- An endpoint to set versions at runtime is deliberately **not** added (it'd be an unauthenticated
  config-mutation surface); a redeploy is the safer publish gate. Revisit if you want a
  push-button admin action later.

## 3. Recovery with the original fingerprint — **confirmed: re-issues a token, no lockout**

`/recover` re-issues a token for the identity **regardless of whether the presented fingerprint
is new or the original**:

- **New fingerprint** → rebind (move the identity + carry run history) + fresh token.
- **Original fingerprint** (token-only loss) → **no-op rebind + fresh token** (no 409).

So a player who loses only their token presents `recoveryCode` + their surviving original
fingerprint and gets a working token back. The 409 ("new fingerprint already registered")
fires **only** when the presented fingerprint already belongs to a *different* identity — never
when it's this identity's own fingerprint. Proven by
`tests/test_reply_followups.py::test_recover_with_original_fingerprint_reissues_token`.

(Note: this was already the behavior in the shipped build; we've added the test to lock it.)

## 4. Reject reasons — **all three are terminal; now flagged structurally**

`modded`, `missing-version`, and `fingerprint-mismatch` are **permanent**. To let you branch on
retryable-vs-terminal **without parsing the reason string**, each rejected entry now carries a
boolean:
```jsonc
// POST /ingest → response
{ "accepted": ["e1"],
  "rejected": [ { "eventId": "e2", "reason": "modded", "terminal": true } ] }
```
- **`terminal: true`** → quarantine/drop; do **not** re-send.
- A future **retryable** reject (a soft per-record failure you *should* re-send) will carry
  **`terminal: false`** and a distinct reason. Branch on the boolean.
- Idempotency is unchanged: an already-stored or in-batch-duplicate `eventId` is returned in
  **`accepted`**, never `rejected`. Prune the outbox on `accepted`.
- Test: `tests/test_reply_followups.py::test_rejects_are_marked_terminal`.

## 5. `fastest-clear` not replay-verifiable — acknowledged

Agreed, and noted in our phase-2 ledger. `fewest-terms` / `deepest-delve` fall out of a
deterministic re-sim of `actions`; wall-clock `realTimeMs` does not. When boards/anti-cheat
land we'll need client timestamps **inside** the action stream + a trust model, or a
terms-based speed proxy. No contract change now; the field stays, flagged as "trust-on-ingest
until verified." Nothing for you to change.

## 6. `consentVersion` bump behavior — deferred, noted

Undefined-on-purpose for the MVP. The intended phase-2 rule: when `consentVersion` advances,
an already-consented player is **re-prompted on next Embassy visit** and re-grants (we store
the new version + timestamp); ingest continues under the prior grant until then. We'll write
it into the spec when the consent text actually changes. Flagged in our tracker.

---

## Net for your side

Items 1–4 are unblocked. Concretely:
- **Re-run codegen** against the refreshed `openapi.json` — you'll pick up `DailyDescriptor.spec`
  (`DailySpec`) and the `RejectedRecord.terminal` field. Both additive; `schemaVersion` = 1.
- **Daily scene:** build path a (derive from `seed`); treat a present `spec` as authoritative
  selections validated against your local registry.
- **Publish workflow:** an env bump + redeploy of the Embassy; never mid-day.
- **Outbox:** prune on `accepted`; on `rejected`, branch on `terminal` (all current reasons
  drop). No retry storm.

The four client work-streams you started (identity store, outbox, `net/embassy.ts` + codegen,
action recorder) need no rework from these answers. Ping us if the authored-`spec` shape wants
more fields before you wire the daily scene.
