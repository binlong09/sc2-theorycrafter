"""Baseline unit dataset — live patch 5.0.15.

This is the "before" era used for patch-diff and era-comparison queries. 5.0.16
(PTR) is derived from this baseline by applying a small diff (see seed_5016.py),
so changed values live in exactly one place.

HONESTY NOTE (read before trusting any number):
    Combat-relevant fields — hp, shields, armor, armor_type, damage, attack_count,
    damage_bonus, damage_bonus_type — are seeded at best confidence because the
    breakpoint calculator depends on them. Fields the calculator does NOT need yet
    (attack_speed, range, movement_speed, exact build_time) are left None where not
    certain rather than guessed. Every row is verified=0: the GM owner sanity-checks
    before any output is trusted. Per CLAUDE.md, the DB is the source of truth — so
    correct it here, not in the model.

PATCH_ERA tag for this dataset: '5.0.15'
"""

PATCH_ERA = "5.0.15"

# Field order mirrors schema.sql. Helper builds full records from partial dicts so
# the data below stays readable — only meaningful fields are spelled out per unit.
_DEFAULTS = {
    "shields": 0,
    "armor": 0,
    "shield_armor": 0,
    "armor_type": "",
    "damage": 0,
    "attack_count": 1,
    "damage_bonus": 0,
    "damage_bonus_type": "",
    "weapon_upgrade_step": 1,
    "attack_speed": None,
    "range": None,
    "supply_cost": None,
    "mineral_cost": None,
    "gas_cost": None,
    "build_time_s": None,
    "movement_speed": None,
    "verified": 0,
    "source": "baseline-live-5.0.15",
}


def _u(unit_name, race, hp, **kw):
    rec = {"unit_name": unit_name, "race": race, "hp": hp, "patch_era": PATCH_ERA}
    rec.update(_DEFAULTS)
    rec.update(kw)
    return rec


# --- Protoss -----------------------------------------------------------------
# Protoss carry shields (shield_armor upgrades separately). armor_type tags are
# space-joined and matched case-insensitively by the breakpoint engine.
PROTOSS = [
    _u("Probe", "Protoss", 20, shields=20, armor=0, armor_type="light mechanical",
       damage=5, supply_cost=1, mineral_cost=50, gas_cost=0, build_time_s=12),
    _u("Zealot", "Protoss", 100, shields=50, armor=1, armor_type="light biological",
       damage=8, attack_count=2, range=0.1, supply_cost=2, mineral_cost=100,
       gas_cost=0, build_time_s=27, movement_speed=3.15),
    _u("Adept", "Protoss", 70, shields=70, armor=1, armor_type="light biological",
       damage=10, damage_bonus=12, damage_bonus_type="light", range=4,
       supply_cost=2, mineral_cost=100, gas_cost=25, build_time_s=30),
    _u("Stalker", "Protoss", 80, shields=80, armor=1, armor_type="armored mechanical",
       damage=13, damage_bonus=5, damage_bonus_type="armored", range=6,
       supply_cost=2, mineral_cost=125, gas_cost=50, build_time_s=27),
    _u("Sentry", "Protoss", 40, shields=40, armor=1,
       armor_type="light mechanical psionic", damage=6, range=5, supply_cost=2,
       mineral_cost=50, gas_cost=100, build_time_s=23),
    _u("HighTemplar", "Protoss", 40, shields=40, armor=0,
       armor_type="light biological psionic", damage=4, range=6, supply_cost=2,
       mineral_cost=50, gas_cost=150, build_time_s=32),
    _u("DarkTemplar", "Protoss", 40, shields=80, armor=1,
       armor_type="light biological psionic", damage=45, range=0.1, supply_cost=2,
       mineral_cost=125, gas_cost=125, build_time_s=32),
]

# --- Terran ------------------------------------------------------------------
TERRAN = [
    _u("SCV", "Terran", 45, armor=0, armor_type="light biological mechanical",
       damage=5, supply_cost=1, mineral_cost=50, gas_cost=0, build_time_s=12),
    _u("Marine", "Terran", 45, armor=0, armor_type="light biological",
       damage=6, range=5, supply_cost=1, mineral_cost=50, gas_cost=0,
       build_time_s=18, movement_speed=3.15),
    _u("Marauder", "Terran", 125, armor=1, armor_type="armored biological",
       damage=10, damage_bonus=10, damage_bonus_type="armored", range=6,
       supply_cost=2, mineral_cost=100, gas_cost=25, build_time_s=21),
    _u("Reaper", "Terran", 60, armor=0, armor_type="light biological",
       damage=4, attack_count=2, range=5, supply_cost=1, mineral_cost=50,
       gas_cost=50, build_time_s=32),
    # Ghost — pre-5.0.16 baseline. Heavily reworked in 5.0.16 (see diff).
    _u("Ghost", "Terran", 125, armor=0, armor_type="biological psionic",
       damage=10, damage_bonus=10, damage_bonus_type="light", range=6,
       supply_cost=2, mineral_cost=150, gas_cost=125, build_time_s=29),
]

# --- Zerg --------------------------------------------------------------------
ZERG = [
    _u("Drone", "Zerg", 40, armor=0, armor_type="light biological",
       damage=5, supply_cost=1, mineral_cost=50, gas_cost=0, build_time_s=12),
    _u("Zergling", "Zerg", 35, armor=0, armor_type="light biological",
       damage=5, range=0.1, supply_cost=0.5, mineral_cost=25, gas_cost=0,
       build_time_s=17, movement_speed=4.13),
    _u("Baneling", "Zerg", 30, armor=0, armor_type="biological",
       damage=16, damage_bonus=19, damage_bonus_type="light", supply_cost=0.5,
       mineral_cost=25, gas_cost=25, build_time_s=14),
    _u("Roach", "Zerg", 145, armor=1, armor_type="armored biological",
       damage=16, range=4, supply_cost=2, mineral_cost=75, gas_cost=25,
       build_time_s=27),
    _u("Hydralisk", "Zerg", 90, armor=0, armor_type="light biological",
       damage=12, range=5, supply_cost=2, mineral_cost=100, gas_cost=50,
       build_time_s=24),
    _u("Queen", "Zerg", 175, armor=1, armor_type="biological psionic",
       damage=8, range=5, supply_cost=2, mineral_cost=150, gas_cost=0,
       build_time_s=36),
    _u("Overlord", "Zerg", 200, armor=0, armor_type="armored biological",
       damage=0, supply_cost=0, mineral_cost=100, gas_cost=0, build_time_s=18,
       movement_speed=0.9),
]

UNITS_5015 = PROTOSS + TERRAN + ZERG
