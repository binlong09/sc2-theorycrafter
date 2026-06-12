"""Breakpoint tests — known-correct answers for the GM owner to sanity-check.

Each assertion is a fact a GM-level player can confirm by eye. If the owner says
a number is wrong, the fix goes in the DB seed (the stat), not here. These pin the
*math*; the seed pins the *stats*.

Run:  pytest        (pyproject sets pythonpath=src)
"""

import pytest

from sc2tc.db import build, connect
from sc2tc.calc.breakpoints import breakpoint


@pytest.fixture(scope="module")
def conn():
    build()  # regenerate DB from seeds so tests never depend on stale state
    c = connect()
    yield c
    c.close()


# --- No-shield, no-bonus headline cases (exact, high confidence) --------------

def test_zealot_does_not_one_shot_zergling(conn):
    # 8(x2)=16 vs 35hp -> 3 instances? no: 8,8,8,8,8=40 -> 5 instances -> 3 cycles.
    bp = breakpoint("zealot", "zergling", atk=0, patch="5.0.16-ptr", conn=conn)
    assert bp.cycles_to_kill == 3
    assert not bp.one_shot

def test_plus1_zealot_two_shots_zergling(conn):
    # CLAUDE.md's illustrative "+1 one-shots" is actually a TWO-shot: 9(x2)=18, 35hp.
    bp = breakpoint("zealot", "zergling", atk=1, patch="5.0.16-ptr", conn=conn)
    assert bp.cycles_to_kill == 2
    assert bp.two_shot and not bp.one_shot

def test_marine_kills_zergling_in_six(conn):
    # 6 dmg, no bonus, 35hp -> ceil(35/6)=6.
    assert breakpoint("marine", "zergling", conn=conn).cycles_to_kill == 6

def test_zergling_kills_drone_in_eight(conn):
    # 5 dmg vs 40hp -> ceil(40/5)=8.
    assert breakpoint("zergling", "drone", conn=conn).cycles_to_kill == 8


# --- Bonus-vs-armored cases (exact at +0) -------------------------------------

def test_marauder_bonus_applies_to_roach(conn):
    # Roach is armored: 10+10=20, -1 armor = 19; 145hp -> ceil(145/19)=8.
    bp = breakpoint("marauder", "roach", conn=conn)
    assert bp.bonus_applied
    assert bp.cycles_to_kill == 8

def test_marauder_bonus_does_not_apply_to_zergling(conn):
    # Zergling is light, not armored -> no bonus: 10-0=10, 35hp -> ceil(35/10)=4.
    bp = breakpoint("marauder", "zergling", conn=conn)
    assert not bp.bonus_applied
    assert bp.cycles_to_kill == 4


# --- Upgrades change the answer ----------------------------------------------

def test_armor_upgrade_blunts_multi_instance_weapon(conn):
    # Zealot 8(x2) vs +3 armor zergling: each instance 8-3=5; 35hp -> 7 instances -> 4 cycles.
    base = breakpoint("zealot", "zergling", atk=0, armor=0, conn=conn).cycles_to_kill
    armored = breakpoint("zealot", "zergling", atk=0, armor=3, conn=conn).cycles_to_kill
    assert armored > base
    assert armored == 4


# --- Shields are eaten first --------------------------------------------------

def test_shields_counted_before_hp(conn):
    # Zealot total effective pool is 150 (100hp + 50 shields).
    bp = breakpoint("zealot", "zealot", conn=conn)
    assert bp.defender_total_hp == 150
    # 8(x2): shields have 0 shield-armor -> 8/instance, 50sh -> 7 instances.
    # hp has 1 armor -> 7/instance, 100hp -> 15 instances. 22 instances -> 11 cycles.
    assert bp.cycles_to_kill == 11


# --- Patch-era awareness ------------------------------------------------------

def test_ghost_rework_changes_damage_across_eras(conn):
    # 5.0.15 ghost: 10(+10 vs light). 5.0.16 ghost: flat 20, no bonus.
    old = breakpoint("ghost", "zergling", patch="5.0.15", conn=conn)
    new = breakpoint("ghost", "zergling", patch="5.0.16-ptr", conn=conn)
    assert old.bonus_applied and old.instance_damage == 20  # 10 + 10 vs light
    assert not new.bonus_applied and new.instance_damage == 20  # flat 20
    # Both 20 vs a 35hp ling -> 2 cycles; the point is the bonus mechanic differs.
    assert old.cycles_to_kill == new.cycles_to_kill == 2


# --- Error handling -----------------------------------------------------------

def test_attacker_uses_air_weapon_vs_flyer(conn):
    # Queen's ground attack is 4x2, but a flying Overlord is hit by its air weapon (9x1).
    bp = breakpoint("Queen", "Overlord", conn=conn)
    assert bp.instance_damage == 9 and bp.attack_count == 1

def test_ground_only_unit_cannot_hit_flyer(conn):
    with pytest.raises(ValueError):
        breakpoint("Zealot", "Phoenix", conn=conn)

def test_air_attacker_vs_flyer(conn):
    # Phoenix (5x2, +5 vs light) vs a Mutalisk (light): 20/cycle vs 120 hp -> 6 cycles.
    assert breakpoint("Phoenix", "Mutalisk", conn=conn).cycles_to_kill == 6


def test_sieged_tank_breakpoint(conn):
    # Siege mode is a distinct row: 40 (+30 vs armored) = 70, -1 Roach armor = 69; 145hp -> 3.
    bp = breakpoint("SiegeTankSieged", "Roach", conn=conn)
    assert bp.instance_damage == 70 and bp.cycles_to_kill == 3
    # and it works as a defender too (HP override = base tank's 175).
    assert breakpoint("Marauder", "SiegeTankSieged", conn=conn).cycles_to_kill == 10


def test_caster_energy_and_sight_stored(conn):
    from sc2tc.db import get_unit
    ht = get_unit(conn, "HighTemplar", "5.0.16-ptr")
    assert ht["energy_max"] == 200 and ht["sight_range"] == 10
    assert get_unit(conn, "Zealot", "5.0.16-ptr")["energy_max"] is None  # non-caster

def test_oracle_has_curated_attack(conn):
    # Oracle's Pulsar Beam (15) is a GM-flagged override — fits the auto-attack model.
    bp = breakpoint("Oracle", "Drone", conn=conn)
    assert bp.instance_damage == 15


def test_no_attack_unit_raises(conn):
    with pytest.raises(ValueError):
        breakpoint("overlord", "zergling", conn=conn)

def test_unknown_unit_raises(conn):
    with pytest.raises(ValueError):
        breakpoint("carrier", "zergling", conn=conn)
