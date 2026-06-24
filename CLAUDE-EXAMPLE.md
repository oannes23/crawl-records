# CLAUDE.md — guidance for Claude Code sessions on SET.core

Read `PROJECT.md` first — it is the full design context and the source of truth
for *why* the generation/tuning math is the way it is. This file is the fast
orientation.

**Design-doc map** (read in this order for the *game* on top of the core):
- `PROJECT.md` — the Set core + generation/tuning math (why the levers exist).
- `GAME-DESIGN.md` — the real game: locked f=3 / N=15 **5×3** board, trigger bus,
  transmute verb. Wins over the prototype defaults where they conflict.
- `CRAWL-DESIGN.md` — **set.crawl**, the data-driven dungeon-crawler: run loop,
  entity architecture (typed TS data, YAML-portable), combat resolution,
  **Tactics v2** (§5.5 — charge queue + Stand Ground / Maneuver), gear taxonomy.
- `TRAPS.md` — the reactive **threat layer**: trap vocabulary, the four board verbs
  (destroy / transmute / lock / + conditions), dungeon·elite·boss attachment, foe
  composition (creature ⊕ variant ⊕ template), enemy-transmute tuning.
- `TUNING.md` — the **live-constants reference** (code is source of truth): Tactics,
  caps, speed bands, gen spec, severity laws, dev-instrument targets. Cite it
  instead of inlining numbers in docs.
- `FABLE.md` — the 2026-06-09 full-repo review: bug ledger, invariant risks,
  architecture notes, prioritized action list (§14).
- `REVIEW-2026-06-16.md` — the 4-agent state-of-project deep dive: code-reality map,
  roadmap status, FABLE re-verification, market/genre analysis. Seeds the
  **POST-REVIEW HARDENING TRACK** in `TODO.md` + `DESIGN-GOALS.md`.
- `DESIGN-GOALS.md` — **guiding principles & go-to-market north star** (from the market
  review). Principles, not a backlog — steer judgment calls + the killer-feature watch-list.
- `WRAPPERS.md` — shipping decision: web client + PWA (Tauri/Capacitor documented);
  Godot rejected.
- `MODDING.md` — the **YAML content-conversion track** (Phases 0–2 DONE 2026-06-17): how all content
  became external YAML, the loader/registry/derived-validator architecture, the affix magnitude DSL,
  and the remaining Phase 3 (the effect-DSL). Dependency invariant: runtime deps stay empty.
- `docs/` — the **modder wiki**: `glossary.md` + the full YAML config reference (`yaml-content.md`
  registry, `yaml-catalogs.md` classes/gear/affixes, `yaml-tuning.md` loot/economy/progression/delve).
  Cite these for "what fields does X.yaml take".

## What this is
A skill-component minigame based on the card game **Set**, the reusable
action-resolution layer of a web RPG. Lineage: `set.core` (skill core + tuning
console) → **`set.combat`** (classes, passives, abilities, Tactics, transmute,
the threat layer) → **`set.crawl`** (the dungeon-crawler game — combat + Tactics
v2 + Phase B1 hub/persistence shipped; run loop next).
**The live game is now the modular TypeScript client in `src/`** (`core`/`data`/
`engine`/`ui`, entry root `index.html`, run with `pnpm dev`). The original
single-file prototypes (`prototype/set-proto.html`, `prototype/set-combat.html`)
are **archived** under `prototype/` as the behavioral oracle the rebuild was
diffed against — read them for *intent*, but new code lands in `src/`. The
foundation migration is complete (TODO §A); next is **set.crawl on the modules**.

## Mental model (don't lose this)
- Set = finite affine geometry **AG(f,3)**. Cards are points in (ℤ/3)^f; a set is
  a line; three cards are a set iff every coordinate sums to 0 mod 3.
- Two cards uniquely determine the third: `third(a,b)_i = (-(a_i+b_i)) mod 3`.
- **Keep 3 values per feature.** Vary `f` for difficulty, never `v`.
- Density: `E[sets] = C(N,3)/(3^f − 2)`.
- The dials are NOT one difficulty scale. F = difficulty spine (moves findability
  AND availability). N = texture (U-shaped, not monotonic). Timer = pressure
  (maps to character skill). k-bias = pure findability. See PROJECT.md §4.

## Hard rules / invariants (assert in any refactor)
1. No duplicate cards on a board.
2. At least `FLOOR` sets present at all times (never a dead board).
3. Dropped/inactive axes are pinned to a constant → must stay all-same →
   never affect set validity. (Cards are always 4-tuples internally.)
4. Generator is a **pure function of a target spec**. Abilities/encounters are
   **spec→spec transforms**, never direct generator inputs. This is the
   structural fairness guarantee — do not add a difficulty input that bypasses it.
5. Control aggregate stats; randomize specifics (no positional tells).
6. **Selection-protected turnover (settled 2026-06-13; build pending).** No card *turnover*
   (any transmute — drift / churn / trap / dread / any owner) may target a card that is
   currently **selected** OR is a **set-mate of a selected card** (a board card that completes
   a set with one or more selected cards). Kills the "I clicked 2 of the 3 and the last one
   morphed" bad-feel — your pattern-finding beats your click speed, never the reverse. Holding a
   partial selection therefore *shields* those cards: an acceptable (clever) exploit, far
   outweighed by removing the bad feel. Pre-first-select turnover is **unprotected** (rare,
   acceptable). Invariant-safe: protection only *restricts* eligible targets, so it can only
   reduce churn — it never breaks the FLOOR (a turnover with no legal target simply skips).
   Implementation note: selection is UI-ephemeral, so the turnover path needs the live selection
   (a `selected` field on combat state, or passed via the action context).

## Working style notes
- The generation core is heavily validated (100k+ clears/config, zero invariant
  violations). Trust it. Bugs so far have all been in the UI layer.
- Before shipping any change to generation, re-run a headless simulation that
  checks the invariants above across the dial space. (Past sessions extracted the
  `<script>` core with a small Node harness and asserted floor/distinct/pin.)
- The live game is the framework-free TS client in `src/` (Vite/Vitest toolchain);
  shipping is settled as **web client + PWA** per `WRAPPERS.md` (Tauri/Capacitor
  documented as wrapper paths; Godot rejected). The archived single-file
  prototypes are oracles only — don't grow them.
- **Lock-layer invariant (built, keep asserting):** ≥ FLOOR sets must be completable from
  *unlocked* cards (the makeable-set floor, `TRAPS.md` §6). Locked cards still form
  sets on paper but not in reach.
- **Keep everything testable, and keep tests quick.** Engine/core logic → vitest
  unit/integration. For UI work, push logic into a pure module and test *that* — never
  the DOM. The `ui/app.ts` monolith is being broken up precisely so the run-economy glue
  becomes coverable; new glue should land already-extracted + tested.
- **Watch for killer-feature hook-ins.** `DESIGN-GOALS.md` carries a watch-list of
  not-yet-built features that tend to drive success in this niche (daily seed + leaderboards,
  relaxed/no-timer mode, clock-on-first-action, graceful miss-degradation). Don't force them —
  but when a feature you're already building gives a clean, cheap hook-in point, flag it to
  the user rather than letting the opportunity pass.
- **Don't run the real balance sim yet — it's gated.** Combat numbers are deliberately
  skeleton/"vibes" until gear loot + the ability reprice/content land (so the sim has real
  weight to bear). Only then run the §11/§13 coupled pass for "combat too easy for skilled
  play." Do not hand-edit `CRAWL-DESIGN.md` §5.6 before the sim. (The generation-invariant
  headless sweep above is separate and always runs before generation changes.)

## Repo / workflow
- **Personal repo** — committing and **pushing directly to the default branch
  (`master`) is fine**, including in auto/unattended mode. No PR/branch dance
  required unless a change is genuinely risky. Commit/push when the user asks.

## Immediate open threads
- **DONE: the threat layer** (`TRAPS.md`) — enemy traps/tricks fire on the trigger bus
  (gated by condition/cadence; no enemy resources), the `locked` card set, named geometry
  selectors, dungeon-drift tick. Built in the prototype, then ported to `src/engine`.
- **DONE: the foundation migration** (TODO §A) — the modular `src/` client is the live
  game at full parity (engine + UI + coaching + polish); the prototype is archived.
- **DONE: Tactics v2** (`CRAWL-DESIGN.md` §5.5) — the charge queue + Stand Ground /
  Maneuver stances replaced the old armed meter; tug-readability polish and the
  **dev instruments** (reshape share, trap-spring rate vs targets — `TUNING.md`)
  are live in the combat UI.
- **DONE: crawl Phase B1** — scene router + town screens (character select /
  dungeon select) + persisted roster (`save.ts`) + the run layer (`run.ts`).
  No run-map yet — that's B2.
- **IN PROGRESS: `set.crawl` Phase B2** — the **delve flow first cut shipped 2026-06-12**
  (`engine/delve.ts` + the run loop in `app.ts`): room chain, boss inverse-CDF + elite
  sawtooth rolls, the between-rooms fork (dread meter, satchel, HP carry), placeholder
  one-consumable room loot. Still open (`TODO.md` §B2): real loot/gold/XP, the flee
  parting blow, the death tithe, folding the delve into the `session.ts` seam.
- **DONE: Resolution v2 "sets steer, stats carry"** (Model B) — stats P/E/S carry the
  numbers, sets steer; telegraphed exchanges. Built 2026-06-10; B3 gear designs
  against the stat block.
- **⭐ NEXT COMBAT BUILD: ROUNDS v3** (settled 2026-06-11; spec `CRAWL-DESIGN.md` §5.6,
  build checklist in `TODO.md`, planned constants in `TUNING.md`) — 20-second rounds:
  verbs accumulate → exchange at the rollover (kill-race ordering), Tactics wheel
  (Stand Ground banker vs Maneuver dumper, CHARGE_CAP 15), computed wound laws, the
  decimal rebase (HP 100 / stats 10). Combat-only; lands before B3 gear.
- **SETTLED 2026-06-12: the progression package** (`CRAWL-DESIGN.md` §3 + §5.7; first-cut
  numbers in `TUNING.md` "PLANNED", gated by the budget sim): level cap 21 (★), +5 HP &
  +3/+2/+1 allocated stats/level (→ the stat re-denomination), XP computed from foe statlines,
  curve anchored dummy→2 / gauntlet→3, category-first loot tables, tithe ~12%, dodge-at-the-deal,
  guard-carry through windups, Maneuver live-burn. The rescoped **numbers workshop** (TODO.md)
  is the gate; run the sim before building.
- Still open (see `TRAPS.md` §8 / `CRAWL-DESIGN.md` §6): per-foe transmute *numbers*
  (framework set, tune in play); ability slots vs. learned library; cooldowns vs.
  resource-only; whether the enemy ever gets an active resource-spending layer.
