"""Planner tests — the goal-driven build-order generator.

These pin the PLANNER's job: completeness + legality. Given a strategic goal, the
assembled build must contain every tech prerequisite, the gas/supply/expansion the goal
needs, and must actually complete the requested units and upgrades. Absolute timings
depend on build_data.py values flagged time_verified=False (owner-calibrated), so like
test_timing these assert relationships and structure, not memorized timestamps.
"""

import pytest

from sc2tc.calc.planner import plan_build, resolve_unit, resolve_upgrade


_GEYSER = {"Protoss": "Assimilator", "Terran": "Refinery", "Zerg": "Extractor"}


def _geysers(plan):
    return plan.build_order.count(_GEYSER[plan.race])


# --- name resolution ---------------------------------------------------------

def test_resolve_unit_nicknames():
    assert resolve_unit("Zerg", "muta") == "Mutalisk"
    assert resolve_unit("Protoss", "high templar") == "HighTemplar"
    assert resolve_unit("Protoss", "Zealot") == "Zealot"
    assert resolve_unit("Zerg", "totally not a unit") is None


def test_resolve_upgrade_friendly_and_engine_names():
    assert resolve_upgrade("Protoss", "charge") == "Charge"
    assert resolve_upgrade("Protoss", "ProtossGroundWeaponsLevel1") == "ProtossGroundWeaponsLevel1"
    # loose query prefers the ground line and lowest level
    assert resolve_upgrade("Protoss", "+1 attack") == "ProtossGroundWeaponsLevel1"
    assert resolve_upgrade("Protoss", "+2 attack") == "ProtossGroundWeaponsLevel2"
    assert resolve_upgrade("Protoss", "+1 air attack") == "ProtossAirWeaponsLevel1"


def test_resolve_upgrade_substring_beats_loose_tokens():
    # 'ling speed' must be metabolic boost (movement), NOT adrenal glands (attack speed),
    # even though both aliases contain the tokens {ling, speed}.
    assert resolve_upgrade("Zerg", "ling speed") == "zerglingmovementspeed"
    assert resolve_upgrade("Zerg", "adrenal") == "zerglingattackspeed"


# --- completeness: every tech prerequisite is present ------------------------

def test_charge_pulls_in_full_tech_chain():
    # Charge needs a Twilight Council, which needs a Cyber, which needs a Gateway.
    p = plan_build("Protoss", units=["Zealot"], upgrades=["charge"], bases=1)
    bo = p.build_order
    for req in ("Gateway", "CyberneticsCore", "TwilightCouncil", "Charge"):
        assert req in bo, f"{req} missing from {bo}"
    assert p.result.complete_of("Charge") is not None


def test_plus_one_needs_a_forge_and_gas():
    p = plan_build("Protoss", units=["Zealot"], upgrades=["+1 attack"], bases=1)
    assert "Forge" in p.build_order
    assert "Assimilator" in p.build_order        # +1 costs gas -> needs a gas structure
    assert p.result.complete_of("ProtossGroundWeaponsLevel1") is not None


def test_unit_production_building_always_present():
    # The original bug: a build that "makes zealots" with no Gateway. Can't happen now.
    p = plan_build("Protoss", units=["Zealot"], bases=1)
    assert "Gateway" in p.build_order
    assert p.result.complete_of("Zealot") is not None


def test_stargate_chain_for_air_unit():
    p = plan_build("Protoss", units=["VoidRay"], bases=1)
    for req in ("Gateway", "CyberneticsCore", "Stargate"):
        assert req in p.build_order
    assert p.result.complete_of("VoidRay") is not None


# --- bases / expansion -------------------------------------------------------

def test_bases_adds_expansions():
    one = plan_build("Protoss", units=["Zealot"], bases=1)
    two = plan_build("Protoss", units=["Zealot"], bases=2)
    assert one.build_order.count("Nexus") == 0      # start base isn't in the order
    assert two.build_order.count("Nexus") == 1      # one expansion
    assert plan_build("Protoss", units=["Zealot"], bases=3).build_order.count("Nexus") == 2


# --- supply: no uncleared supply blocks --------------------------------------

def test_no_supply_block_warnings_after_autosupply():
    p = plan_build("Protoss", units=[("Zealot", 8)], upgrades=["charge", "+1 attack"], bases=2)
    assert not any("supply-blocked" in w for w in p.warnings)
    # supply is auto-built by the sim (not queued in the order) — Pylons appear in the steps
    assert any(s.name == "Pylon" for s in p.result.steps)


def test_everything_queued_completes():
    # A fully-assembled plan should leave nothing stuck ('did not complete').
    p = plan_build("Protoss", units=[("Zealot", 6)], upgrades=["charge", "+1 attack"], bases=2)
    assert not any("did not complete" in w for w in p.warnings)


# --- gas: caller-controlled, hard-capped at the 2-geyser physical limit ------

def test_gas_per_base_is_a_flat_caller_knob():
    # Default 1/base (economic); the caller sets it from the build type.
    assert _geysers(plan_build("Protoss", units=["Stalker"], bases=1)) == 1
    assert _geysers(plan_build("Protoss", units=["Stalker"], bases=2)) == 2
    assert _geysers(plan_build("Protoss", units=["Stalker"], bases=2, gas_per_base=2)) == 4


def test_gas_per_base_capped_at_physical_geyser_limit():
    # A base has 2 geysers — asking for 3 can never produce 3/base.
    from sc2tc.calc.planner import MAX_GAS_PER_BASE
    assert MAX_GAS_PER_BASE == 2
    assert _geysers(plan_build("Protoss", units=["Stalker"], bases=1, gas_per_base=3)) == 2


def test_no_gas_structures_when_goal_is_mineral_only():
    # Pure zealots with warpgate OFF need no gas -> never add geysers.
    assert _geysers(plan_build("Protoss", units=["Zealot"], bases=2, gas_per_base=2,
                               warpgate=False)) == 0


# --- warp gate (almost always needed; transforms cost 50/50 each) ------------

def test_warpgate_research_and_transforms_added():
    # Default warpgate=True: research it + morph EVERY gateway into a warp gate.
    p = plan_build("Protoss", units=["Zealot"], upgrades=["charge"], bases=2, production_total=7)
    assert "WarpGateResearch" in p.build_order
    assert p.build_order.count("WarpGate") == p.build_order.count("Gateway") == 7


def test_warpgate_forces_gas_even_for_pure_mineral_army():
    # Research + transforms cost gas, so a warpgate build always takes a geyser.
    assert _geysers(plan_build("Protoss", units=["Zealot"], bases=1)) >= 1


def test_warpgate_can_be_disabled():
    p = plan_build("Protoss", units=["Zealot"], bases=1, warpgate=False)
    assert "WarpGate" not in p.build_order and "WarpGateResearch" not in p.build_order


def test_warpgate_build_completes_no_stall():
    p = plan_build("Protoss", units=["Zealot"], upgrades=["+1 attack"], bases=1)
    assert not any("did not complete" in w or "stalled" in w for w in p.warnings)
    assert p.result.complete_of("WarpGateResearch") is not None


# --- build endpoint + closing note -------------------------------------------

def test_build_done_marks_endpoint_and_closing_note():
    p = plan_build("Protoss", units=["Zealot"], upgrades=["charge"], bases=2)
    # endpoint = when the last planned building/transform/upgrade completes
    planned = set(p.build_order)
    last = max(s.complete_s for s in p.result.steps if s.name in planned)
    assert abs(p.build_done_s - last) < 1e-6
    assert "BUILD DONE" in p.closing and "warp" in p.closing.lower()


def test_table_truncates_at_build_done():
    # The rendered table stops at the build endpoint — no long streamed-army tail.
    p = plan_build("Protoss", units=["Zealot"], upgrades=["charge"], bases=2)
    table = p.table()
    # last unit row in the table starts at/under build_done; the sim itself produced more
    import re
    times = [int(m[0]) * 60 + int(m[1])
             for m in re.findall(r"^\d+\s+(\d+):(\d\d)\s", table, re.M)]
    assert max(times) <= p.build_done_s / 1 + 2
    assert p.result.finished_at > p.build_done_s   # sim ran past the rendered endpoint


def test_production_per_base_race_default():
    # P/T default 4 per base (1 base = 4-gate); explicit count from closure is included.
    p1 = plan_build("Protoss", units=["Zealot"], bases=1)
    assert p1.build_order.count("Gateway") == 4
    p2 = plan_build("Protoss", units=["Zealot"], bases=1, production_per_base=2)
    assert p2.build_order.count("Gateway") == 2


# --- per-race econ macro -----------------------------------------------------

def test_terran_gets_orbital_and_mules():
    p = plan_build("Terran", units=[("Marine", 6)], upgrades=["stim"], bases=1)
    assert "OrbitalCommand" in p.build_order
    assert any("MULE" in n for n in p.result.notes)


def test_zerg_gets_queens_and_injects():
    p = plan_build("Zerg", units=[("Zergling", 6)], bases=2)
    assert p.build_order.count("Queen") >= 1
    assert any("Inject" in n for n in p.result.notes)


# --- continuous army production (composition ratio + supply ceiling) ----------

def _count(plan, name):
    return sum(1 for s in plan.result.steps if s.name == name)


def test_army_holds_the_requested_ratio():
    # Zealot:2, HighTemplar:1 -> ~twice as many zealots as templar WHEN gas allows it (HT is
    # gas-heavy; with only 1 gas/base it skews mineral-ward — that's correct, gas is the knob).
    p = plan_build("Protoss", units=[("Zealot", 2), ("HighTemplar", 1)],
                   upgrades=["charge"], bases=2, gas_per_base=2)
    z, ht = _count(p, "Zealot"), _count(p, "HighTemplar")
    assert ht > 0 and z > 0
    assert 1.6 <= z / ht <= 2.4            # ~2:1, allowing for discretization


def test_gas_starved_comp_skews_mineralward():
    # The honest consequence: a gas-heavy comp on minimal gas can't hold its ratio.
    lo = plan_build("Protoss", units=[("Zealot", 2), ("HighTemplar", 1)],
                    upgrades=["charge"], bases=2, gas_per_base=1)
    hi = plan_build("Protoss", units=[("Zealot", 2), ("HighTemplar", 1)],
                    upgrades=["charge"], bases=2, gas_per_base=2)
    skew = lambda p: _count(p, "Zealot") / _count(p, "HighTemplar")
    assert skew(lo) > skew(hi)            # less gas -> more mineral-ward


def test_army_streams_continuously_not_backloaded():
    # The army must start producing as soon as a production building is up — NOT after the
    # whole econ/tech/upgrade order finishes. First zealot should start well before the
    # last upgrade completes.
    p = plan_build("Protoss", units=["Zealot"], upgrades=["charge", "+1 attack"], bases=2)
    first_zealot = min(s.start_s for s in p.result.steps if s.name == "Zealot")
    charge_done = p.result.complete_of("Charge")
    assert first_zealot < charge_done * 0.6   # army is flowing long before the timing


def test_army_is_not_in_the_explicit_order():
    # Army is produced by the sim (auto_army), not queued — keeps the order econ/tech only.
    p = plan_build("Protoss", units=["Zealot"], bases=1)
    assert "Zealot" not in p.build_order
    assert _count(p, "Zealot") > 0            # but it IS produced


def test_worker_count_capped_at_saturation():
    # worker_cap = 22/base stops worker production at saturation (so army gets the minerals).
    p = plan_build("Protoss", units=[("Zealot", 1)], bases=2)
    assert max(s.workers for s in p.result.curve) <= 2 * 22 + 2   # +slack for in-flight


def test_supply_is_auto_built():
    # The sim auto-builds Overlords (Zerg supply) and keeps the build healthy. Zerg supply
    # rides on scarce larva, so a brief early supply-block can occur, but it must not stall
    # the build — overlords get built and the army flows.
    p = plan_build("Zerg", units=[("Zergling", 3)], bases=2)
    assert _count(p, "Overlord") > 0
    assert _count(p, "Zergling") > 0
    assert not any("did not complete" in w for w in p.warnings)


# --- friendly handling of bad input ------------------------------------------

def test_unknown_unit_is_skipped_with_note_not_crash():
    p = plan_build("Protoss", units=["Zealot", "Flarglmunit"], bases=1)
    assert any("unknown unit" in n.lower() for n in p.notes)
    assert "Gateway" in p.build_order            # the valid part still planned

def test_empty_goal_raises():
    with pytest.raises(ValueError):
        plan_build("Protoss", units=[], upgrades=[], bases=1)


# --- rendered table ----------------------------------------------------------

def test_table_renders_columns_and_workers():
    p = plan_build("Protoss", units=["Zealot"], upgrades=["charge"], bases=2)
    table = p.table()
    assert "Supply" in table and "Time" in table and "Action" in table and "Cost" in table
    assert "Probe" in table                       # worker production is shown (not hidden)
    assert "Charge" in table
