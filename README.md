# sc2-theorycrafter

A StarCraft 2 theorycrafting assistant that gives **verified, patch-accurate
answers** grounded in real game data — not paraphrased wiki text or forum
discussions.

The problem with stock LLMs (Claude, Gemini, etc.) for SC2: their knowledge
comes from scraped community chatter, so they confidently quote stale HP
values, hallucinate build times, and miss patch changes by months. This tool
separates the two things they conflate:

> **Facts live in the database. Reasoning lives in the model.**

Unit stats, breakpoints, and build-order timings come from the DB at runtime.
The model only reasons about strategy *given* those facts as context. When a
patch changes zergling HP, we update one DB row — no retraining required.

---

## Status

Built for the **5.0.16 PTR** (massive economy + mechanic overhaul) and live
**5.0.15** for comparison queries.

| Component                | State                                                        |
|--------------------------|--------------------------------------------------------------|
| Unit stats DB            | seeded for 5.0.15 + 5.0.16-ptr (or extracted from game data) |
| Breakpoint calculator    | working, CLI                                                 |
| Timing calculator        | working, CLI (`starting_workers` parameterized)              |
| Replay extractor         | working, batch-tested on ~250 replays                        |
| Agent (Ollama or Claude) | working, with DB tool access                                 |
| Fine-tuned local model   | not yet — well-prompted base model + grounded DB suffices    |
| RAG over replay corpus   | not yet                                                      |
| FastAPI                  | not yet                                                      |

The replay parser is a separate sibling repo: see [Setup](#setup).

---

## Setup

```powershell
# 1. Clone both repos as siblings
#    C:\...\AIProjects\zephyrus-sc2-parser   <- the parser fork
#    C:\...\AIProjects\sc2-theorycrafter     <- this repo

# 2. Install the parser editable, then this package
pip install -e ..\zephyrus-sc2-parser
pip install -e .

# 3. Build the unit stats DB from the seed datasets
python -m sc2tc.db.build
# -> writes data/sc2tc.db

# 4. (optional) Install agent / RAG / dev extras
pip install -e .[agent]   # anthropic SDK for the Claude backend
pip install -e .[rag]     # chromadb (future)
pip install -e .[dev]     # pytest
```

The parser dep is intentionally NOT listed in `pyproject.toml` so a fresh clone
fails loudly if the sibling repo is missing, rather than silently grabbing a
stale version off PyPI.

---

## Usage

### Breakpoint calculator — "how many hits to kill?"

```powershell
python -m sc2tc.calc.cli zealot zergling --atk 1 --patch 5.0.16-ptr
python -m sc2tc.calc.cli marauder roach
python -m sc2tc.calc.cli stalker immortal --atk 2 --armor 1
```

Pure math over DB-sourced stats. Output includes hits-to-kill, per-cycle damage,
and whether vs-type bonuses applied.

### Timing calculator — "when does this build complete?"

```powershell
python -m sc2tc.calc.timing_cli Protoss Pylon Gateway CyberneticsCore
python -m sc2tc.calc.timing_cli Protoss Pylon Gateway --patch 5.0.15 --no-workers
python -m sc2tc.calc.timing_cli Terran SupplyDepot Barracks Refinery Factory --curve
```

Models worker production, resource income, and tech timing. `starting_workers`
is a parameter (5.0.16 PTR changed it from 12 to 8 — every era is comparable).
Boosters (`MULE`, `Inject`, `Chrono:CyberneticsCore`) are valid steps.

### Replay extractor — turn .SC2Replays into training data

```powershell
# single replay -> stdout (or --out file.json)
python -m sc2tc.extract --replay "C:\...\Mothership LE (3).SC2Replay"

# whole folder -> one JSON per replay in data/extracted/
python -m sc2tc.extract --dir "C:\...\Multiplayer" --out-dir data\extracted
python -m sc2tc.extract --dir "C:\...\Multiplayer" --limit-seconds 480  # opener only
```

Each JSON is one game with `replay_hash`, `base_build`, `patch_era`, per-player
build order with `(time_s, supply, name, kind, cost)`, upgrades, and result.
Filename is the sha256 of the .SC2Replay file so re-extracting is idempotent and
mixing corpora across folders never collides.

The build → patch era mapping is in `src/sc2tc/patch_eras.py` — add a row when a
new patch ships.

### Agent — natural-language theorycrafting with DB-grounded answers

```powershell
# one question, local Ollama backend (default)
python -m sc2tc.agent.cli "does +1 zealot two-shot a zergling?"

# Claude backend for harder questions
python -m sc2tc.agent.cli "when can I afford gate and core with 8 workers?" --backend claude

# auto-routing (local for simple, Claude for ambiguous builds)
python -m sc2tc.agent.cli "what's the fastest 4-gate timing on PTR?" --backend auto

# compare both backends side by side
python -m sc2tc.agent.cli "how many marines to kill a roach?" --compare

# interactive (keeps context across questions)
python -m sc2tc.agent.cli -i
```

The agent has tool access to the DB and the calculators — it cannot answer a
stat question by recalling from weights. If the DB has no row for a unit at
that patch, the agent says so explicitly.

Claude backend needs an API key in `SC2TC_ANTHROPIC_API_KEY` or a
`.anthropic_key` file at the repo root. (Note: deliberately not the shared
`ANTHROPIC_API_KEY` — Claude Code bills against that one.)

---

## Repo layout

```
sc2-theorycrafter/
  pyproject.toml
  README.md                     # this file
  CLAUDE.md                     # owner-facing project guidance
  src/sc2tc/
    extract.py                  # replay -> training-data JSON
    patch_eras.py               # base_build -> "5.0.16-ptr"
    db/
      schema.sql                # unit_stats table definition
      __init__.py               # connect, get_unit, alias resolver
      build.py                  # rebuild the DB from seeds / game-data dumps
      seed_5015.py              # hand-curated 5.0.15 (live) values
      seed_5016.py              # hand-curated 5.0.16 PTR values
      extract_gamedata.py       # dump authoritative values from the SC2 client
      map_gamedata.py           # map engine dump -> unit_stats rows
    calc/
      breakpoints.py            # hits-to-kill math
      cli.py                    # breakpoint CLI
      timing.py                 # build-order resource/timing sim
      timing_cli.py             # timing CLI
      patch_config.py           # starting_workers, supply per structure, etc.
      build_data.py             # build-time + tech-req tables
      production_data.py        # production-structure costs / capacities
      upgrade_data.py           # upgrade costs / research times
    agent/
      agent.py                  # ask(), compare(), start_session()
      backends.py               # Ollama + Claude tool-use loops
      tools.py                  # DB / calculator tools exposed to the model
      cli.py                    # agent CLI
  tests/
    test_breakpoints.py         # owner-verified ground-truth checks
    test_timing.py
    test_agent.py
  data/
    replays/                    # gitignored — symlink your replay folder here
    extracted/                  # gitignored — one .json per replay
    sc2tc.db                    # gitignored — regenerable via db.build
```

---

## How a patch update works

1. Pull changed values from patch notes (or run `extract_gamedata` against the
   updated client).
2. Add a new seed file under `db/` (e.g. `seed_5017.py`) and wire it into
   `db/__init__.py:build()`.
3. Add the new build → era pair to `patch_eras.py`.
4. `python -m sc2tc.db.build` — regenerates the SQLite file.
5. Done. No model retraining. The tool is accurate for the new patch within
   hours of patch notes dropping.

---

## What the model must NOT do

- State unit HP, damage, or build times from memory — always query the DB.
- Generate build orders without pulling timing data from the calculator.
- Reference patch-specific changes without checking the current DB era.
- Claim a timing is "standard" without verifying against the calculator.

If the DB has no row for a query, the assistant says so explicitly rather than
hallucinate a number. The breakpoint and timing modules document their
modeling limits (e.g. bonus-vs-type scaling above +0 weapon, splash, ability
damage out of scope) in their module docstrings so the agent can quote them
honestly.

---

## Validation

Owner is GM-level and is the source of ground truth until enough PTR replays
exist to validate timings against real games. Tests in `tests/` capture
known-correct answers (e.g. "+1 zealot one-shots zergling on 5.0.16-ptr") and
should grow whenever the owner spots a wrong output. First replay-based
validation will compare timing calculator output against the owner's own PTR
replays once they exist in `data/extracted/`.
