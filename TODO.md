# TODO — deferred work

## Data coverage gaps (unit_stats, 5.0.16 engine extraction)

The engine extractor (`extract_gamedata.py` → `map_gamedata.py`) covers all 52 canonical
real units authoritatively (cleaned from 62 — dropped campaign/summoned junk). Status:

1. **Air weapons (anti-air dimension) — DONE (2026-06-05).** unit_stats has
   air_damage/air_attack_count/air_damage_bonus(_type)/air_attack_speed/air_range + is_flyer
   (20 flyers, 15 anti-air units). `engine_stats()` emits both weapons via target_type
   (1=ground, 2=air, 3=any); breakpoint calc picks the weapon by the defender's plane and
   raises if a ground-only unit targets a flyer. Verified: Phoenix->Muta 6, Queen uses its
   air weapon (9) vs flying Overlord, Zealot can't hit Phoenix.

**Production catalog — DONE (2026-06-05).** `production_data.py` makes all 42 standard army
units buildable in the timing model (engine cost/supply/build_time + GM-curated production
building + tech prereqs). Verified Immortal 3:41 / Colossus 4:36 / Carrier 5:32 /
SiegeTank 3:10 / Battlecruiser 6:01 / Mutalisk 4:57. Hand-entered units removed from build_data.

**Morph units — DONE (2026-06-05).** `production_data.MORPHS`: Baneling/Ravager/Lurker/
BroodLord/Overseer modeled as from-scratch combined items (dump cost is already total
base+morph; build_time = base build + morph time; built_by larva; requires morph building).
Added GreaterSpire to build_data for Brood Lords. Verified Baneling 4:13 / Ravager 4:32 /
Lurker 5:33 / Overseer 4:46 / BroodLord 7:05. DEFERRED: **Archon** (merges 2 templars, not a
single base unit); **Zergling pairs** (modeled 1-larva=1-ling, real is 2/larva).

**Caster energy + sight range — DONE (2026-06-05).** unit_stats has energy_max + sight_range
(authoritative from dump; casters=200, non-casters NULL). **Oracle Pulsar Beam** added to
ATTACK_OVERRIDE (15 dmg, GM-flagged verified=0).

REMAINING (genuinely non-extractable via our path, or niche — the breakpoint + timing tools
don't need them):
- **Ability balance numbers** (spell energy costs, cooldowns, Carrier-interceptor DPS,
  Disruptor Nova AoE) live in the game's CASC/XML, NOT the s2client static data we dump
  (`abilities` isn't even in the response). Options: CASC/XML extraction (heavy/fragile) or
  GM-curated override tables (owner-verified, consistent with project philosophy). The 3
  macro-mechanic energy costs (chrono/MULE/inject) are already modeled.
- **Warp Gate 50/50 transform** — same boundary (ability cost). Kept as CLAUDE.md/GM value.
- **Upgrade effects** (Charge->speed, Glaives->atk-speed) — modeling, not extraction.

**Transform combat modes — DONE (2026-06-05).** SiegeTankSieged (40+30 armored, rng 13),
LiberatorAG (75, flyer-as-defender), HellionTank/Hellbat (18+12 light), VikingAssault
(12+8 mech), ThorAP (air 25+10 massive / ground 30x2) un-excluded as distinct rows +
HP overrides. Verified: sieged tank -> Roach 3, two-shots Marines; works as defender too
(Marauder->sieged 10). 57 units/era, 64 tests.

2. **Transform combat modes — DONE (2026-06-05).** SiegeTankSieged/LiberatorAG/HellionTank/
   VikingAssault/ThorAP un-excluded as distinct rows with HP overrides; LiberatorAG flagged
   is_flyer. See "Transform combat modes — DONE" below.

3. **Special / ability attacks** (empty `weapons` array — not auto-extractable):
   **Oracle** (Pulsar Beam, activated), **Carrier** (damage via Interceptors),
   **Disruptor** (Purification Nova, AoE ability), **Liberator** (needs AG siege).
   - Fix: add GM-known values to `ATTACK_OVERRIDE` in `map_gamedata.py`, or model abilities.
   - Already overridden there: Sentry, Baneling, Battlecruiser, VoidRay.

## Upgrades / research / tech tree — DONE (2026-06-05): 86 upgrades, all L1/L2/L3 + abilities

COMPLETE: 86 standard upgrades (Protoss 26 / Terran 31 / Zerg 29) — all weapon/armor/
shields L1/L2/L3 with tier-2/3 building + prior-level prereqs, plus ability/unit upgrades.
All tech buildings + Lair/Hive morphs in build_data. Verified: +1 attack 3:46, +3 attack
9:42, roach speed 5:38. Minor remaining gaps: PsiStorm (TemplarArchives name not in dump),
a few co-op-only upgrades, Flyer-L3 approximated as Hive (really Greater Spire), per-era
research times (loads 5.0.16 only), and build_data structure costs still hand-entered
(engine caught SpawningPool 200->250, Hatchery 300->325).

(original notes:) engine `UpgradeData` extracted (research_time + cost, authoritative);
`upgrade_data.py` curates upgrade->building + prereqs; tech buildings added to
`build_data.py` (Forge, Twilight, Eng Bay, Armory, Evo, BarracksTechLab); timing calc
schedules `kind='upgrade'` (researched at building, occupies it, marks complete for
prereqs); `list_upgrades` tool + simulate_build_order accept upgrades. Model now answers
"earliest +1 attack -> 3:46" correctly (Forge, 121.4s) instead of hallucinating Cyber.

Covered: L1 ground/air weapon+armor+shields (all races), Charge, Blink, Warpgate,
Stim, ling speed. EXTENSIONS still needed:
1. **Level 2/3 weapon/armor** — need tier-2/3 buildings (Twilight/Armory done; Zerg
   Lair/Hive are morphs not yet in build_data) + prereq = prior level. Add to REQUIREMENTS.
2. **Legacy-named upgrades**: CombatShield, ConcussiveShells, PsiStorm (TemplarArchives) —
   engine names differ (e.g. ShieldWall/PunisherGrenades); find + add.
3. **Per-era research times**: build_data._upgrades() loads from gamedata_5016.json only.
   If live (5.0.15) research times differ, load per-era (extract retail upgrades — already
   in gamedata_5015.json after the live extraction).
4. **build_data structure costs/build-times still hand-entered** — engine caught SpawningPool
   200->250; should engine-source build_data like unit_stats.

## Assistant reasoning / data depth (2026-06-05)

- **Clarify-on-ambiguity is model-limited.** System prompt now tells the model to ask when
  base-count / all-in-vs-macro / warp-gate-transform are unspecified, but local Qwen3:30b
  often ignores it and just answers (assumed 1-base + ignored the 4 gates + transform on the
  "4-gate warpgate all-in" probe). This is the model-quality ceiling — test Opus via
  `--compare` (needs ANTHROPIC_API_KEY); a stronger model should ask reliably.
- **Chrono allocation is strategic, not modeled per-intent.** Realistic default = first ~2
  chronos on economy, then the rush target; EXCEPT 1-base all-in (chrono tech/units). Current
  auto-chrono is greedy-longest. Tie chrono policy to an all-in/macro flag once the model can
  ask for it.
- **Extract AbilityData** (currently only UnitTypeData + UpgradeData). Gives authoritative
  ability costs — notably the **Warp Gate transform 50/50** (currently from CLAUDE.md, flagged
  in build_data; engine WarpGate.mineral_cost is cumulative 150, real cost is on the ability),
  and would let us fill the deferred ability-attacks (Sentry/Baneling/Oracle/Carrier/Disruptor).

## Abuse / cost protection (for public/multi-user deployment)

Built now: system-prompt SCOPE LOCK (refuses non-SC2 + ignores role-change/injection;
verified even Qwen3 declines "write me a crypto bot"), max_tokens=2048 cap, MAX_STEPS=8
loop cap, SC2-only tools. For LATER when multi-user/public:
- **Topic pre-gate before routing to Opus** — the router escalates on keywords, so a query
  with SC2 words + an off-topic pivot still reaches paid Opus (scope lock refuses it + cap
  bounds cost, but a cheap pre-check avoids the spend entirely).
- **Per-user rate limits + cumulative spend budget** (hard $ ceiling; refuse when exceeded).
- **Logging / monitoring** of escalations and refusals.

## Other

- **Engine-source `build_data.py` build times** (timing calc) like we did for unit_stats.
  Current hand values verified within tolerance vs engine (Pylon 17.9, Gateway 46.4, etc.),
  so low priority.
- ~~5.0.15 baseline hand-seeded~~ **DONE (2026-06-05):** 5.0.15 (live) is now engine-sourced
  from the retail client (5.0.15.96883). `db.build()` loads `gamedata_5015.json` +
  `gamedata_5016.json`; `seed_5015.py`/`seed_5016.py` are fallbacks only. PTR-vs-live
  comparisons (e.g. Ghost vs Stalker: 9 shots PTR vs 17 live) are now both authoritative.
