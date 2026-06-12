# Macro Ability Values — for GM review

These are the **ability-driven values the calculators actually use** (the macro mechanics +
warp-gate transform). Exported from `src/sc2tc/calc/timing.py` (`IncomeRates`) and
`src/sc2tc/calc/build_data.py`. Edit there to change them — this file is a snapshot for review.

Status legend: ✅ owner-calibrated · ⚙️ SC2-standard (tunable, not independently verified) ·
📋 from CLAUDE.md (not engine-verified).

## Energy (global — all casters)

| Parameter | Value | Notes | Status |
|---|---|---|---|
| Energy regen | **0.7875 /s** | per caster (Nexus / Orbital / Queen) | ⚙️ |
| Start energy | **50** | energy a caster has when it appears | ⚙️ |
| Max energy | **200** | cap | ⚙️ |

## Chrono Boost (Protoss — Nexus)

| Parameter | Value | Notes | Status |
|---|---|---|---|
| Energy cost | **50** | per cast | ⚙️ |
| Duration | **20 s** | one boost lasts this long | ⚙️ |
| Effect | **+50% work speed** | applied to the boosted building | ⚙️ |
| Cooldown | **none** | energy-gated only; ~63 s to re-afford at full regen | ⚙️ |
| Manual-boost shave | **10 s** | flat shave used for an explicit `Chrono:Target` action (approx of 20 s × 50%) | ⚙️ approx |

## MULE (Terran — Orbital Command)

| Parameter | Value | Notes | Status |
|---|---|---|---|
| Energy cost | **50** | per MULE | ⚙️ |
| Mining rate | **3.5 min/s** | while active | ⚙️ |
| Duration | **64 s** | MULE lifetime | ⚙️ |
| Total yield | **~225 min** | rate × duration | ⚙️ derived |

## Inject Larva (Zerg — Queen)

| Parameter | Value | Notes | Status |
|---|---|---|---|
| Energy cost | **25** | per inject | ⚙️ |
| Larva added | **+3** | per inject | ⚙️ |
| Delay | **29 s** | larva appear this long after casting | ⚙️ |

## Warp Gate transform (Protoss)

| Parameter | Value | Notes | Status |
|---|---|---|---|
| Cost | **50 / 50** | morph a Gateway → Warp Gate (5.0.16 PTR; was free pre-patch) | 📋 not engine-verified |
| Transform time | **7 s** | engine morph time | engine |
| (Research) | — | Warp Gate *research* time/cost is engine-sourced separately | engine ✅ |

---

**Not in this table (deliberately):** combat-spell numbers — Psi Storm, EMP, Fungal, Snipe,
Disruptor Nova, Carrier interceptors, etc. None of the calculators consume them, and they
aren't in the client API (the open sourcing question). This table is only the macro/transform
values that are already wired in.

**Owner review asks:** the ⚙️ macro constants are SC2-standard defaults, tunable but not
independently verified for 5.0.16 — flag any that the PTR changed. The 📋 warp transform
50/50 is from CLAUDE.md, worth confirming on the PTR.
