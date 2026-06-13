# sc2-theorycrafter

A StarCraft 2 theorycrafting assistant that gives **verified, patch-accurate
answers** grounded in real game data — not paraphrased wiki text or forum
discussions.

The problem with stock LLMs (Claude, Gemini, etc.) for SC2: their knowledge
comes from scraped community chatter, so they confidently quote stale HP
values, hallucinate build times, and miss patch changes by months. This tool
separates the two things they conflate:

> **Facts live in the database. Reasoning lives in the model.**

Unit stats, breakpoints, and build-order timings come from the DB and pure-math
calculators at runtime. The model only reasons about strategy *given* those
facts. When a patch changes zergling HP, we update one DB row — no retraining.

---

## Contents

- [Status](#status)
- [Setup](#setup)
- [What it can do](#what-it-can-do)
  - [Build-order planner](#build-order-planner--design-a-complete-build-from-a-goal) ← the headline feature
  - [Breakpoint calculator](#breakpoint-calculator--how-many-hits-to-kill)
  - [Timing calculator](#timing-calculator--time-a-build-you-wrote)
  - [Natural-language agent](#natural-language-agent)
  - [Replay extractor](#replay-extractor)
- [How the planner works](#how-the-planner-works)
- [How a patch update works](#how-a-patch-update-works)
- [Repo layout](#repo-layout)
- [Design principles](#design-principles)
- [Roadmap](#roadmap)

---

## Status

Built for the **5.0.16 PTR** (a massive economy + mechanic overhaul) with live
**5.0.15** kept alongside for comparison queries. Every value is tagged to a
`patch_era`, so the same question can be asked of either patch.

| Component                      | State                                                              |
|--------------------------------|--------------------------------------------------------------------|
| Unit stats DB                  | seeded for 5.0.15 + 5.0.16-ptr (or extracted from the game client)  |
| Breakpoint calculator          | working — pure math, CLI                                            |
| Timing calculator              | working — tick sim, `starting_workers` parameterized, CLI           |
| **Build-order planner**        | **working — designs complete, legal builds from a goal, CLI + tool**|
| Natural-language agent         | working — Ollama (local) or Claude, DB/calculator tool access       |
| Replay extractor               | working — batch-tested on ~250 replays                              |
| Fine-tuned local model         | not yet — a well-prompted base model over the grounded DB suffices  |
| RAG over replay corpus         | not yet                                                             |
| FastAPI service                | not yet                                                             |

96 tests, all owner-verifiable. The replay parser lives in a separate sibling
repo (see [Setup](#setup)).

---

## Setup

```powershell
# 1. Clone both repos as siblings:
#    C:\...\AIProjects\zephyrus-sc2-parser   <- the parser fork
#    C:\...\AIProjects\sc2-theorycrafter     <- this repo

# 2. Install the parser editable, then this package
pip install -e ..\zephyrus-sc2-parser
pip install -e .

# 3. Build the unit-stats DB from the seed datasets (or game-data dumps)
python -m sc2tc.db.build           # -> writes data/sc2tc.db

# 4. (optional) extras
pip install -e .[agent]            # anthropic SDK (Claude backend)
pip install -e .[gamedata]         # burnysc2 (engine extractor)
pip install -e .[dev]              # pytest
```

The parser dependency is intentionally **not** in `pyproject.toml`, so a fresh
clone fails loudly if the sibling repo is missing rather than silently pulling a
stale version from PyPI. The data layer itself is pure stdlib (sqlite3 + math).

---

## What it can do

### Build-order planner — design a complete build from a goal

The headline feature. You give a **goal** (army composition, upgrades, base
count); the planner assembles a complete, legal, playable build — every tech
prerequisite, gas, supply, expansion, per-race macro (Orbital/Queens),
production buildings, and warp-gate tech — then simulates it and renders the
full table. It does **not** rely on the model to know the tech tree.

```powershell
# 2-base +1 charge-zealot timing (4 gateways)
python -m sc2tc.calc.planner_cli Protoss --units Zealot --upgrades "+1 attack" charge --bases 2 --production-total 4

# a composition ratio (2 zealots per templar), tech-heavy so double-gas
python -m sc2tc.calc.planner_cli Protoss --units Zealot:2 HighTemplar:1 --upgrades charge --bases 2

# 1-base Terran bio
python -m sc2tc.calc.planner_cli Terran --units Marine:2 Marauder:1 --upgrades stim
```

```
Protoss @ 5.0.16-ptr — start 8 workers

Supply  Time  Action                      Cost       Notes
----------------------------------------------------------
8       0:00  Probe                       50m        Chrono Boost
9       0:12  Probe                       50m
10      0:23  Pylon                       100m
12      0:47  Gateway                     150m
...
BUILD DONE 5:34 — 4 Warp Gates ready, 9 Zealot on hand. Upgrades: +1 ground
attack 5:31, charge 5:34. Put a proxy Pylon in a safe spot near the enemy and
warp your army in to attack.
```

Key ideas:

- **`units` is a composition *ratio*, not a fixed count.** `Zealot:2 HighTemplar:1`
  streams a 2:1 army continuously from every production building; you read how
  much you have at any timestamp off the table.
- **The table ends at the build's endpoint** — when the last planned
  building/transform/upgrade completes — followed by a tactical "what now" note
  (warp-in / move out), not an endless army tail.
- **Race-aware, build-type-aware knobs:** `--production-total` ("4-gate",
  "7-gate"), `--gas-per-base` (1 = economic, 2 = tech/all-in, hard-capped at the
  2-geyser physical limit), `--bases`. Warp-gate research + a transform per
  gateway (50/50 each) are included by default for Protoss.

### Breakpoint calculator — "how many hits to kill?"

```powershell
python -m sc2tc.calc.cli zealot zergling --atk 1 --patch 5.0.16-ptr
python -m sc2tc.calc.cli marauder roach
python -m sc2tc.calc.cli stalker immortal --atk 2 --armor 1
```

Pure math over DB-sourced stats: hits-to-kill, per-cycle damage, and whether
vs-type bonuses applied. Picks the correct (ground vs air) weapon and refuses
nonsense (a ground-only unit "shooting" a flyer).

### Timing calculator — "time a build *you* wrote"

```powershell
python -m sc2tc.calc.timing_cli Protoss Pylon Gateway CyberneticsCore
python -m sc2tc.calc.timing_cli Protoss Pylon Gateway --patch 5.0.15 --no-workers
python -m sc2tc.calc.timing_cli Terran SupplyDepot Barracks Refinery Factory --curve
```

A tick-based economic sim: worker production, per-patch mineral/gas saturation,
tech gating, supply blocks. `starting_workers` is a parameter (5.0.16 changed it
12 → 8 — every era is directly comparable). Boosters (`MULE`, `Inject`,
`Chrono:CyberneticsCore`) are valid steps. This times a list you hand it; the
[planner](#build-order-planner--design-a-complete-build-from-a-goal) is what
*designs* the list.

### Natural-language agent

```powershell
python -m sc2tc.agent.cli "does +1 zealot two-shot a zergling?"
python -m sc2tc.agent.cli "give me a PvZ +1 charge all-in on 2 bases"
python -m sc2tc.agent.cli "when can I afford gate and core with 8 workers?" --backend claude
python -m sc2tc.agent.cli -i        # interactive, keeps context
```

The agent has tool access to the DB and every calculator — it **cannot** answer
a stat question from its weights. Tool routing: breakpoint questions →
`compute_breakpoint`; "design me a build" → `plan_build_order` (whose table is
printed verbatim, since it's ground truth); "time this list" / "earliest single
upgrade" → `simulate_build_order`. If the DB has no row for a unit at a patch,
the agent says so rather than guessing.

Backends: local **Ollama** (default, free) or **Claude** for harder reasoning;
`--backend auto` routes by difficulty, `--compare` runs both. The Claude backend
reads `SC2TC_ANTHROPIC_API_KEY` or a `.anthropic_key` file at the repo root —
deliberately **not** the shared `ANTHROPIC_API_KEY` (Claude Code bills against
that one).

### Replay extractor

```powershell
python -m sc2tc.extract --replay "C:\...\Mothership LE (3).SC2Replay"
python -m sc2tc.extract --dir "C:\...\Multiplayer" --out-dir data\extracted
python -m sc2tc.extract --dir "C:\...\Multiplayer" --limit-seconds 480   # opener only
```

Each JSON is one game: `replay_hash`, `base_build`, `patch_era`, per-player
build order with `(time_s, supply, name, kind, cost)`, upgrades, and result. The
filename is the sha256 of the `.SC2Replay`, so re-extraction is idempotent and
mixing corpora never collides. Build → era mapping lives in `patch_eras.py`.

---

## How the planner works

The split mirrors the project's core principle:

- **Completeness & legality are facts → the tool's job.** From the catalog's
  `requires` / `built_by` chains the planner computes the full prerequisite
  closure (charge ⇒ Twilight ⇒ Cyber ⇒ Gateway; +1 ⇒ Forge), then inserts the
  economy by policy: expansion(s), gas, per-race macro, production buildings,
  warp-gate research + transforms. The sim auto-builds supply (no supply
  blocks), caps workers at saturation, and produces the army composition
  continuously while reserving resources for a queued expansion. A build that
  "makes zealots" can never come out without a Gateway.
- **Strategic intent is reasoning → the caller's input.** Which army, how
  aggressive, how many bases, how much gas — supplied by you (CLI) or the model
  (the `plan_build_order` tool). The model never has to know the tech tree.

The ordering is a sensible standard-macro heuristic, **not** a provably-earliest
optimizer (a possible later phase). Absolute build times are seeded at best
confidence (`time_verified=False`) pending calibration against PTR replays —
they're the first thing the GM owner tunes.

---

## How a patch update works

1. Pull changed values from patch notes, or run `extract_gamedata` against the
   updated client.
2. Add a seed file under `db/` (e.g. `seed_5017.py`) and wire it into
   `db/build.py`.
3. Add the new build → era pair to `patch_eras.py`.
4. `python -m sc2tc.db.build` — regenerates the SQLite file.
5. Done. No model retraining; the tool is accurate within hours of patch notes.

---

## Repo layout

```
sc2-theorycrafter/
  pyproject.toml
  README.md                     # this file
  CLAUDE.md                     # owner-facing project guidance
  TODO.md                       # deferred work / known gaps
  src/sc2tc/
    extract.py                  # replay -> training-data JSON
    patch_eras.py               # base_build -> "5.0.16-ptr"
    db/
      schema.sql                # unit_stats table definition
      __init__.py               # connect, get_unit, nickname/alias resolver
      build.py                  # rebuild the DB from seeds / game-data dumps
      seed_5015.py / seed_5016.py   # hand-curated live + PTR values
      extract_gamedata.py       # dump authoritative values from the SC2 client
      map_gamedata.py           # map engine dump -> unit_stats rows
    calc/
      breakpoints.py / cli.py   # hits-to-kill math + CLI
      timing.py / timing_cli.py # build-order resource/timing sim + CLI
      planner.py / planner_cli.py   # goal -> complete build + full-table render + CLI
      patch_config.py           # starting_workers, supply per structure, income rates
      build_data.py             # structures/workers: cost, build time, tech reqs
      production_data.py        # army-unit production building + prereqs (engine costs)
      upgrade_data.py           # upgrade research building + prereqs (engine times)
    agent/
      agent.py                  # ask(), compare(), start_session(), routing + system prompt
      backends.py               # Ollama + Claude tool-use loops
      tools.py                  # DB / calculator tools exposed to the model
      cli.py                    # agent CLI (prints planner tables verbatim)
  tests/                        # test_breakpoints / test_timing / test_planner / test_agent
  data/
    replays/                    # gitignored — point your replay folder here
    extracted/                  # gitignored — one .json per replay + game-data dumps
    sc2tc.db                    # gitignored — regenerable via db.build
```

---

## Design principles

- **Facts from the DB/calculators, never from model weights.** The agent must
  call a tool for any HP / damage / cost / build time / hits-to-kill number.
- **Build *correctness* is deterministic.** Tech prerequisites, supply, gas, and
  legality are computed by the planner — not left to the model to remember.
- **`starting_workers` is always a parameter.** Never hard-code 8 (or 12); read
  it from the era's config so 5.0.15 and 5.0.16 stay comparable.
- **A patch is a data change, not a retrain.** Update one row / seed file.
- **The GM owner is the validator.** Outputs are owner-verifiable by design;
  unverified seed values are flagged `time_verified=False`.

---

## Roadmap

- Calibrate `build_time_s` against the owner's PTR replays (first replay-grounded
  validation of planner timings).
- Per-era tech building map (e.g. 5.0.16 moved warp-gate research to the Gateway;
  the curated requirements table is currently era-agnostic).
- Warp-in *burst* army modeling (army size at a timing is currently streamed).
- RAG over the extracted replay corpus; optional fine-tune; FastAPI service.

See `TODO.md` for the detailed data-coverage status and deferred items.
