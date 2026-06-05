# SC2 Theorycrafter — sc2-theorycrafter repo

## What This Project Is

A StarCraft 2 theorycrafting assistant that gives verified, patch-accurate answers
grounded in real game data — not scraped wiki text or forum discussions.

Owner is a GM-level SC2 player. This domain expertise is the unfair advantage — used
to curate training data and catch model hallucinations that no silver-level dev could spot.

## Sibling Repo

The replay parser lives in a sibling fork:
  C:\Users\binlo\AIProjects\zephyrus-sc2-parser\

That repo handles replay parsing only. This repo depends on it:
  pip install -e ../zephyrus-sc2-parser

Do not put parser code here. Do not put theorycrafting code there.

---

## Core Architecture Principle (Never Violate This)

  Facts live in the database. Reasoning lives in the model.

The model NEVER recalls unit stats, damage values, HP, build times, or upgrade costs
from its weights. All of that comes from the DB at runtime via tool calls.
When a patch changes a value, we update one DB record — not retrain the model.

---

## Current State (as of session start)

- No replay corpus yet. Parser work is in progress in the sibling repo.
- Data layer is the immediate priority — it can be built entirely from patch notes
  without any replays.
- Fine-tuned model is Phase 3, months away. Do not block on it.
- A well-prompted base model (Qwen3 14B local or Claude API) over the grounded DB
  is already useful without fine-tuning.

Patch currently being built for: **5.0.16 PTR** (may become live soon).
This is a massive economy + mechanic overhaul — effectively a new game.
Being the first tool with verified 5.0.16 data is the primary opportunity.

---

## Immediate Tasks (Phase 1 — Data Layer)

Do these in order. Do not over-engineer. Owner has ~1 hr/day.

### Task 1 — Unit Stats DB
Populate a SQLite database (or structured JSON if simpler to start) with:
- All unit stats changed in 5.0.16 PTR (see section below)
- Schema: unit_name, race, hp, shields, armor, armor_type, damage, damage_bonus,
  damage_bonus_type, attack_speed, range, supply_cost, mineral_cost, gas_cost,
  build_time_s, movement_speed, patch_era
- patch_era field is critical — every row is tagged to a patch so we can query
  "give me zealot stats for 5.0.16" vs "give me zealot stats for 5.0.15"

### Task 2 — Breakpoint Calculator
Pure math module. No LLM, no replays needed.
- Input: attacker unit, defender unit, attacker_upgrades, defender_upgrades, patch_era
- Output: number of hits to kill, whether it's a one-shot or two-shot
- Example: breakpoint("zealot", "zergling", atk=1, armor=0, patch="5.0.16") → 1
- Pre-compute a full table for all relevant PvZ/TvZ/TvP unit combos at all upgrade levels
- This is what makes "+1 zealot one-shots zergling" a verified fact, not a guess

### Task 3 — Timing Calculator
Models resource income and unit production timing. No replays needed.
- Key parameter: starting_workers (NOW 8, was 12 — must be configurable)
- Input: build_order steps (list of buildings/units in order), race, patch_era
- Output: timestamp when each step completes, mineral/gas curve over time
- Must handle: worker production cadence, chrono/mule/inject equivalents,
  supply blocks, tech requirements
- This answers: "With 8 workers, when can I afford gate + core?" before any
  human has played enough PTR games to know intuitively

### Task 4 — Patch Update Pipeline
When a new patch drops:
1. Pull changed values from patch notes (or game XML if available)
2. Insert new rows into unit stats DB with new patch_era tag
3. Regenerate breakpoint tables for the new patch
4. No model retraining required
5. Tool is accurate for new patch within hours of patch notes dropping

---

## 5.0.16 PTR — Key Changed Values to Populate Immediately

### Economy (game-wide, affects all races)
- starting_workers: 12 → **8**  ← most important change, parameterize everything
- large_mineral_patch: 1800 → 1600
- small_mineral_patch: 900 → 1200
- total_minerals_per_base: 10800 → 11200
- vespene_geyser: 2250 → 2500
- rich_vespene_harvest_return: 8 → 6

### Supply per Structure (all changed)
- Command Center: 15 → **13**
- Nexus: 15 → **13**
- Hatchery/Lair/Hive: 6 → **4**  ← 33% supply reduction per hatch, major Zerg impact

### Terran — Ghost (heavily reworked)
- supply_cost: 2 → **3**  ← fewer ghosts in 200-supply army, major composition change
- hp: 125 → 100
- damage: 10 (+10 vs Light) → **20** (flat, no bonus)
- range: 6 → 7
- steady_targeting_damage: 130+40vsPsionic → 170 (flat)
- steady_targeting_energy: 50 → 75
- steady_targeting_cancels_on_damage: true → **false**

### Zerg
- hatchery_supply: see above (6→4)
- creep_spread_rate: 0.45 → 0.55 (slower spread)
- spore_crawler_damage_vs_bio: 20+10bio → 20+**15**bio
- carapace_l1_cost: 150/150 → 100/100
- carapace_l2_cost: 200/200 → 150/150
- carapace_l3_cost: 250/250 → 200/200
- infestor_microbial_shroud_range: 9 → 12
- infestor_microbial_shroud_requires_upgrade: true → **false**
- infestor_has_auto_attack: false → **true**
- viper_abduct_valid_targets: [non-mech] → includes **Sieged Tanks**
- overlord_speed_without_upgrade: 0.9 → 0.7

### Protoss — Warpgate (major mechanic overhaul)
- warpgate_research_location: Cybernetics Core → **Gateway**
- warpgate_effect: enables warp-in → **speeds up Gateway production by 35%**
- transform_to_warpgate_cost: 0/0 → **50/50**
- warp_in_time_flat: 3s (was 3.6s fast field, 11.4s slow field)
- nexus_supply: see above (15→13)

### Protoss — Gateway Pre-Warpgate Build Times
- zealot: 27 → 28s
- adept: 30 → 28s
- stalker: 27 → 28s
- sentry: 23 → 24s
- high_templar: 32 → 40s
- dark_templar: 32 → 40s

### Protoss — Post-Warpgate Cooldowns (after warp-in)
- zealot: 22s
- adept: 22s
- stalker: 22s
- sentry: 16s
- high_templar: 35s
- dark_templar: **2s**  ← verify this on PTR, may be a typo or intentional

### Protoss — Other
- psi_storm_total_damage: 110 → 100
- nexus_supply: 15 → 13

---

## Tech Stack

| Component          | Choice                        | Notes                              |
|--------------------|-------------------------------|------------------------------------|
| Language           | Python                        |                                    |
| Unit stats DB      | SQLite (start) or JSON        | Patch-diffable, simple             |
| Breakpoint calc    | Pure Python math module       | No external deps                   |
| Timing calculator  | Pure Python, parameterized    | starting_workers must be a param   |
| Vector DB / RAG    | ChromaDB                      | Consistent with stock-vetter work  |
| Local inference    | Ollama (already set up)       | Qwen3 14B on RTX 5090              |
| Fallback model     | Claude API (claude-sonnet)    | For complex queries, ~$0.006/query |
| Replay parser      | Zephyrus (sibling repo)       | Parser work separate, not blocking |

---

## What NOT to Do

- Do not wait for replays before building the data layer. Replays validate it; they
  don't create it.
- Do not model-hallucinate unit stats. Every stat must come from the DB.
- Do not build a UI before the data layer is verified by owner (GM player sanity check).
- Do not mix parser code into this repo.
- Do not hard-code starting_workers=8 anywhere — always a parameter so we can
  compare eras.
- Do not retrain the model when a patch drops. Update the DB instead.

---

## Validation Strategy (no replays needed for Phase 1)

Owner is GM-level and can verify outputs directly:
- Run breakpoint calculator → owner confirms "+1 zealot one-shots zergling" ✓/✗
- Run timing calculator on known opener → owner confirms timing makes sense ✓/✗
- Once PTR is accessible, owner plays 10-15 games and replays validate calculator output

First replay-based validation: compare timing calculator output against owner's own
PTR replays once the Zephyrus parser (sibling repo) is working.

---

## Repo Structure

sc2-theorycrafter/
  pyproject.toml          # depends on editable zephyrus-sc2-parser install
  src/sc2tc/
    __init__.py
    db/
      schema.sql          # unit stats table definition
      seed_5016.py        # populate DB from 5.0.16 values above
      seed_5015.py        # previous patch values for comparison queries
    calc/
      breakpoints.py      # hits-to-kill calculator
      timing.py           # build order timing calculator (starting_workers param)
    rag/
      ingest.py           # future: ingest replay JSONs into ChromaDB
      retrieve.py         # future: retrieve relevant context for queries
    api/
      main.py             # future: FastAPI endpoint
  data/
    replays/              # gitignored
    extracted/            # gitignored (output from Zephyrus parser)
  tests/
    test_breakpoints.py   # known correct answers, owner-verified
    test_timing.py        # known correct timings, owner-verified
  CLAUDE.md               # this file