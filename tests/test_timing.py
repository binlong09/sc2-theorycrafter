"""Timing-calculator tests.

These pin the *model's mechanics* (income math, supply blocks, tech gating,
era-awareness, race-specific worker handling). The absolute build-time numbers
depend on build_data.py values flagged time_verified=False — those get calibrated
against the GM owner's PTR replays, so tests here assert relationships and
hand-computable income, not memorized timestamps.
"""

import pytest

from sc2tc.calc.timing import simulate, IncomeRates


def _sample_at(result, t):
    for s in result.curve:
        if abs(s.t - t) < 1e-6:
            return s
    raise AssertionError(f"no curve sample at t={t}")


# --- era awareness (the whole point of patch_era) ----------------------------

def test_starting_workers_per_era():
    assert simulate(["Pylon"], "Protoss", "5.0.16-ptr").starting_workers == 8
    assert simulate(["Pylon"], "Protoss", "5.0.15").starting_workers == 12

def test_base_supply_cap_per_era():
    # Engine-verified 5.0.16: Nexus provides 12 (CC is 13 — asymmetric). Live 5.0.15: 15.
    assert _sample_at(simulate(["Pylon"], "Protoss", "5.0.16-ptr"), 0).supply_cap == 12
    assert _sample_at(simulate(["CommandCenter"], "Terran", "5.0.16-ptr"), 0).supply_cap == 13
    assert _sample_at(simulate(["Pylon"], "Protoss", "5.0.15"), 0).supply_cap == 15

def test_zerg_starts_with_overlord_supply():
    # Hatch 4 (5.0.16) + starting Overlord 8 = 12.
    assert _sample_at(simulate(["Overlord"], "Zerg", "5.0.16-ptr"), 0).supply_cap == 12

def test_fewer_workers_means_later_gateway():
    g16 = simulate(["Pylon", "Gateway"], "Protoss", "5.0.16-ptr").start_of("Gateway")
    g15 = simulate(["Pylon", "Gateway"], "Protoss", "5.0.15").start_of("Gateway")
    assert g16 > g15  # 8 workers mine slower than 12


# --- income math (hand-computable) -------------------------------------------

def test_mineral_income_matches_formula():
    # 8 workers (1/patch, tier-1 rate 1.0/s) with a 5s startup ramp, no extra workers.
    # Income flows only from t=5: sample at t=10 = 50 + 8 * 1.0 * (10 - 5) = 90.
    # Calibrated against the owner's PTR test (2026-06-05).
    r = simulate(["Nexus"], "Protoss", "5.0.16-ptr", make_workers=False)
    assert _sample_at(r, 10).minerals == pytest.approx(90.0, abs=0.1)

def test_mining_efficiency_scales_minerals():
    # mining_efficiency models un-microed loss below the optimal ceiling (minerals only).
    full = simulate(["Stalker"], "Protoss", "5.0.16-ptr", make_workers=False)  # never builds: pure mining
    lossy = simulate(["Stalker"], "Protoss", "5.0.16-ptr", make_workers=False,
                     rates=IncomeRates(mining_efficiency=0.9))
    mined_full = _sample_at(full, 30).minerals - 50
    mined_lossy = _sample_at(lossy, 30).minerals - 50
    assert mined_lossy == pytest.approx(mined_full * 0.9, abs=0.1)

def test_startup_ramp_zero_income_before_delay():
    # Nothing is mined during the initial worker walk-out.
    r = simulate(["Nexus"], "Protoss", "5.0.16-ptr", make_workers=False)
    assert _sample_at(r, 0).minerals == 50
    assert _sample_at(r, 5).minerals == 50   # still ramping at t=5

def test_saturation_tiers_diminish():
    # Marginal worker value strictly decreases; the 3rd worker is split far vs close,
    # and a far-patch 3rd worker is worth much more than a close-patch one.
    r = IncomeRates()
    assert (r.first_worker_per_patch > r.second_worker_per_patch
            > r.third_worker_far_patch > r.third_worker_close_patch)
    assert r.third_worker_far_patch > 3 * r.third_worker_close_patch  # ~0.60 vs ~0.13


# --- tech prerequisites -------------------------------------------------------

def test_cyber_never_starts_before_gateway_done():
    r = simulate(["Pylon", "Gateway", "CyberneticsCore"], "Protoss", "5.0.16-ptr")
    assert r.start_of("CyberneticsCore") >= r.complete_of("Gateway")

def test_stalker_requires_cyber():
    # Stalker needs Gateway + Cyber (and 50 gas, hence the Assimilator).
    r = simulate(["Pylon", "Gateway", "Assimilator", "CyberneticsCore", "Stalker"],
                 "Protoss", "5.0.16-ptr")
    assert r.start_of("Stalker") >= r.complete_of("CyberneticsCore")


# --- supply blocks ------------------------------------------------------------

def test_supply_block_detected():
    # 8/13 start; 3 zealots = +6 supply -> the 3rd is supply-blocked (no pylon).
    r = simulate(["Gateway", "Zealot", "Zealot", "Zealot"], "Protoss", "5.0.16-ptr",
                 make_workers=False)
    assert any("supply-blocked" in w for w in r.warnings)


# --- race-specific worker handling -------------------------------------------

def test_terran_scv_occupied_during_build():
    # Building a structure pulls one SCV off minerals for the whole build (8 -> 7).
    # SupplyDepot has no prereq, so it actually gets built here.
    r = simulate(["SupplyDepot"], "Terran", "5.0.16-ptr", make_workers=False)
    assert any(s.workers == 7 for s in r.curve)

def test_zerg_drone_consumed_building_structure():
    # Drone morphs into the building: worker count drops permanently 8 -> 7.
    r = simulate(["SpawningPool"], "Zerg", "5.0.16-ptr", make_workers=False)
    assert r.curve[-1].workers == 7

def test_protoss_probe_not_consumed():
    # Probe returns to mining; worker count holds at 8 (occupancy default 0).
    r = simulate(["Gateway"], "Protoss", "5.0.16-ptr", make_workers=False)
    assert all(s.workers == 8 for s in r.curve)


# --- boosters -----------------------------------------------------------------

def test_chrono_speeds_completion():
    base = simulate(["Pylon", "Gateway", "CyberneticsCore"], "Protoss", "5.0.16-ptr",
                    make_workers=False)
    boosted = simulate(["Pylon", "Gateway", "Chrono:CyberneticsCore", "CyberneticsCore"],
                       "Protoss", "5.0.16-ptr", make_workers=False)
    assert boosted.complete_of("CyberneticsCore") < base.complete_of("CyberneticsCore")

def test_mule_ignored_for_non_terran():
    r = simulate(["Pylon", "MULE"], "Protoss", "5.0.16-ptr")
    assert any("non-Terran" in w for w in r.warnings)

def test_production_catalog_builds_army_units():
    # Any standard army unit (not just zealots) can now be timed — Immortal off a Robo.
    bo = ["Pylon", "Assimilator", "Gateway", "CyberneticsCore", "RoboticsFacility",
          "Pylon", "Pylon", "Immortal"]
    r = simulate(bo, "Protoss", "5.0.16-ptr", max_time_s=600)
    assert r.complete_of("Immortal") is not None

def test_unit_requires_its_tech_building():
    # Colossus needs a Robotics Bay; without it, it cannot be produced.
    bo = ["Pylon", "Assimilator", "Gateway", "CyberneticsCore", "RoboticsFacility",
          "Pylon", "Colossus"]
    r = simulate(bo, "Protoss", "5.0.16-ptr", max_time_s=400)
    assert r.start_of("Colossus") is None

def test_morph_unit_buildable():
    # Baneling is a morph (Zergling -> Baneling); modeled as a from-scratch combined item.
    bo = ["Overlord", "Extractor", "SpawningPool", "BanelingNest",
          "Overlord", "Overlord", "Baneling"]
    r = simulate(bo, "Zerg", "5.0.16-ptr", max_time_s=500)
    assert r.complete_of("Baneling") is not None


def test_upgrade_researches_at_its_building():
    # +1 ground attack (Forge, engine research 121.4s) must start after the Forge and
    # take its research time. Needs gas, so include an Assimilator.
    r = simulate(["Pylon", "Assimilator", "Forge", "ProtossGroundWeaponsLevel1"],
                 "Protoss", "5.0.16-ptr")
    assert r.start_of("ProtossGroundWeaponsLevel1") >= r.complete_of("Forge")
    dur = r.complete_of("ProtossGroundWeaponsLevel1") - r.start_of("ProtossGroundWeaponsLevel1")
    assert abs(dur - 121.4) < 1.5

def test_upgrade_without_its_building_does_not_complete():
    r = simulate(["Pylon", "Assimilator", "ProtossGroundWeaponsLevel1"], "Protoss",
                 "5.0.16-ptr", max_time_s=300)
    assert r.start_of("ProtossGroundWeaponsLevel1") is None
    assert any("did not complete" in w for w in r.warnings)

def test_upgrade_levels_chain_in_order():
    # L2 must wait for both Twilight Council (tier-2 building) AND L1.
    r = simulate(["Pylon", "Assimilator", "Gateway", "CyberneticsCore", "Forge",
                  "TwilightCouncil", "ProtossGroundWeaponsLevel1", "ProtossGroundWeaponsLevel2"],
                 "Protoss", "5.0.16-ptr", max_time_s=900)
    assert r.complete_of("ProtossGroundWeaponsLevel2") is not None
    assert r.start_of("ProtossGroundWeaponsLevel2") >= r.complete_of("ProtossGroundWeaponsLevel1")
    assert r.start_of("ProtossGroundWeaponsLevel2") >= r.complete_of("TwilightCouncil")

def test_terran_mule_adds_minerals():
    bo = ["SupplyDepot", "Barracks", "OrbitalCommand"]
    off = simulate(bo, "Terran", "5.0.16-ptr", macro=False, max_time_s=400)
    on = simulate(bo, "Terran", "5.0.16-ptr", macro=True, max_time_s=400)
    assert any("MULE" in n for n in on.notes)
    last = min(off.curve[-1].t, on.curve[-1].t)
    m = lambda r: next(s.minerals for s in r.curve if abs(s.t - last) < 1e-6)
    assert m(on) > m(off)  # MULEs add minerals

def test_zerg_inject_adds_drones():
    bo = ["Overlord", "Overlord", "Overlord", "SpawningPool", "Queen"] + ["Drone"] * 60
    off = simulate(bo, "Zerg", "5.0.16-ptr", macro=False, make_workers=False, max_time_s=420)
    on = simulate(bo, "Zerg", "5.0.16-ptr", macro=True, make_workers=False, max_time_s=420)
    drones = lambda r, t: sum(1 for s in r.steps if s.name == "Drone" and s.complete_s <= t)
    assert any("Inject" in n for n in on.notes)
    assert drones(on, 280) > drones(off, 280)  # injected larva -> more drones

def test_protoss_chrono_casts():
    r = simulate(["Pylon", "Nexus"], "Protoss", "5.0.16-ptr", macro=True, max_time_s=200)
    assert any("Chrono" in n for n in r.notes)

def test_chrono_speeds_research():
    # Chrono boost must actually shorten the reported research completion (was a stale-
    # complete_s reporting bug: the sim shortened it but the StepResult kept the old time).
    bo = ["Pylon", "Assimilator", "Forge", "ProtossGroundWeaponsLevel1"]
    off = simulate(bo, "Protoss", "5.0.16-ptr", macro=False, max_time_s=400)
    on = simulate(bo, "Protoss", "5.0.16-ptr", macro=True, max_time_s=400)
    assert on.complete_of("ProtossGroundWeaponsLevel1") < off.complete_of("ProtossGroundWeaponsLevel1")

def test_macro_off_by_default_is_deterministic():
    a = simulate(["Pylon", "Gateway"], "Protoss", "5.0.16-ptr")
    b = simulate(["Pylon", "Gateway"], "Protoss", "5.0.16-ptr", macro=False)
    assert a.start_of("Gateway") == b.start_of("Gateway")


def test_zerg_morph_gated_upgrade():
    # +2 melee needs a Lair (a morph of the Hatchery). It must finish before L2 starts.
    r = simulate(["Overlord", "SpawningPool", "Extractor", "EvolutionChamber", "Lair",
                  "ZergMeleeWeaponsLevel1", "ZergMeleeWeaponsLevel2"], "Zerg", "5.0.16-ptr",
                 max_time_s=900)
    assert r.complete_of("Lair") is not None
    assert r.start_of("ZergMeleeWeaponsLevel2") >= r.complete_of("Lair")


def test_inject_adds_larva_for_zerg():
    # With no inject, 3 starting larva cap Zerg drone output early; inject grants more.
    r = simulate(["Inject"], "Zerg", "5.0.16-ptr")
    assert any("Inject" in n for n in r.notes)


# --- gas worker control (pull in / pull out) ---------------------------------

def test_gas_action_waits_for_geyser_then_applies():
    # Gas:1 written before the Assimilator finishes must WAIT, not be dropped.
    r = simulate(["Pylon", "Gateway", "Assimilator", "Gas:1"], "Protoss", "5.0.16-ptr")
    assert not any("ignored" in w for w in r.warnings)
    assert any("gas workers -> 1" in n for n in r.notes)

def test_gas_pull_out_stops_gas_income():
    # Saturate gas, then Gas:0 pulls everyone back to minerals -> gas income flatlines.
    r = simulate(["Pylon", "Gateway", "Assimilator", "Gas:3", "Gas:0"], "Protoss", "5.0.16-ptr",
                 max_time_s=120)
    assert any("gas workers -> 0" in n for n in r.notes)
    assert r.curve[-1].gas == pytest.approx(r.curve[-2].gas, abs=0.01)  # no more gas mined

def test_gas_income_matches_calibration():
    # One geyser, saturated at 3 workers, should mine 1.03+0.93+0.70 = 2.66 gas/s.
    r = simulate(["Pylon", "Gateway", "Assimilator"], "Protoss", "5.0.16-ptr", max_time_s=300)
    late = [s for s in r.curve if s.t >= 130]  # well after the Assimilator saturates
    g0, g1 = late[0], late[-1]
    rate = (g1.gas - g0.gas) / (g1.t - g0.t)
    assert rate == pytest.approx(2.66, abs=0.05)

def test_gas_tiers_diminish_gently():
    # Gas diminishes far less than minerals: 3rd worker still > 60% of the first.
    r = IncomeRates()
    assert r.first_gas_worker > r.second_gas_worker > r.third_gas_worker
    assert r.third_gas_worker > 0.6 * r.first_gas_worker

def test_gas_capped_at_geyser_capacity():
    # Asking for more gas workers than 3/geyser caps at capacity (no phantom workers).
    r = simulate(["Pylon", "Gateway", "Assimilator", "Gas:9"], "Protoss", "5.0.16-ptr")
    assert any("gas workers -> 3" in n for n in r.notes)
