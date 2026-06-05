"""Breakpoint calculator — how many attack cycles to kill a unit.

Pure math over DB-sourced stats. No LLM, no replays. This is what turns
"+1 zealot one-shots zergling?" into a verified yes/no instead of a vibe.

An *attack cycle* is one full swing of the weapon. A zealot's cycle is two
damage instances (attack_count=2); a marine's is one. Armor is subtracted from
each individual instance, then floored at MIN_DAMAGE_PER_INSTANCE (SC2's 0.5 rule),
which is why high-armor targets blunt multi-instance weapons harder.

Shields (Protoss) are eaten first and take shield_armor; once depleted, hp takes
ground armor. Weapon and armor upgrade *levels* are passed in and applied here.

MODELING LIMITATIONS (documented, owner to refine):
  - A weapon-upgrade level adds `weapon_upgrade_step` to the BASE damage of each
    instance. Some SC2 units also scale their bonus-vs-type with upgrades; that
    per-unit scaling is NOT modeled yet. So bonus-vs-armored breakpoints
    (marauder, stalker) are exact at +0 and slightly conservative above it.
  - Splash, abilities (e.g. Steady Targeting), and damage-point timing are out of
    scope — this is raw weapon-vs-stats math.
"""

import math
from dataclasses import dataclass, asdict

from ..db import connect, get_unit

MIN_DAMAGE_PER_INSTANCE = 0.5  # SC2: a weapon instance never does less than 0.5


@dataclass
class Breakpoint:
    attacker: str
    defender: str
    patch_era: str
    atk_weapon_level: int
    def_armor_level: int
    def_shield_level: int
    instance_damage: float        # damage per single instance after upgrades+bonus, pre-armor
    attack_count: int             # instances per cycle
    bonus_applied: bool           # did the vs-type bonus apply to this defender?
    damage_per_cycle_vs_hp: float # net damage to hp per full cycle (post-armor)
    cycles_to_kill: int           # THE answer: full attack cycles to drop the target
    one_shot: bool                # killed in a single cycle
    two_shot: bool
    defender_total_hp: int        # hp + shields, for context

    def summary(self):
        n = self.cycles_to_kill
        word = "one-shot" if self.one_shot else "two-shot" if self.two_shot else f"{n}-cycle kill"
        return (f"{self.attacker} (+{self.atk_weapon_level} atk) vs "
                f"{self.defender} (+{self.def_armor_level} armor) @ {self.patch_era}: "
                f"{n} attack cycle(s) to kill - {word}.")


def _armor_type_set(row):
    return set(row["armor_type"].lower().split()) if row["armor_type"] else set()


def breakpoint(attacker, defender, atk=0, armor=0, shield=0,
               patch="5.0.16-ptr", conn=None):
    """Cycles for `attacker` to kill `defender` at the given upgrade levels.

    Args:
        attacker, defender: unit names (case-insensitive).
        atk:    attacker weapon-upgrade level (0-3).
        armor:  defender ground-armor-upgrade level (0-3).
        shield: defender shield-upgrade level (Protoss only; 0-3).
        patch:  patch_era tag, e.g. '5.0.16-ptr' or '5.0.15'.
        conn:   optional open sqlite3 connection (one is opened+closed if omitted).

    Returns a Breakpoint. Raises ValueError if a unit is missing for that era,
    or if the attacker deals zero damage to the defender (e.g. Overlord).
    """
    own_conn = conn is None
    if own_conn:
        conn = connect()
    try:
        a = get_unit(conn, attacker, patch)
        d = get_unit(conn, defender, patch)
    finally:
        if own_conn:
            conn.close()

    if a is None:
        raise ValueError(f"No stats for attacker '{attacker}' @ {patch}. Build the DB / add the unit.")
    if d is None:
        raise ValueError(f"No stats for defender '{defender}' @ {patch}. Build the DB / add the unit.")

    # Resolve per-instance damage: base + weapon upgrade, plus vs-type bonus if it applies.
    bonus_applies = bool(a["damage_bonus"]) and (
        a["damage_bonus_type"].lower() in _armor_type_set(d)
    )
    instance_dmg = a["damage"] + a["weapon_upgrade_step"] * atk
    if bonus_applies:
        instance_dmg += a["damage_bonus"]

    if instance_dmg <= 0:
        raise ValueError(f"'{attacker}' has no ground attack (0 damage) — no breakpoint vs '{defender}'.")

    attack_count = a["attack_count"]
    eff_armor = d["armor"] + armor
    eff_shield_armor = d["shield_armor"] + shield

    dmg_to_hp = max(MIN_DAMAGE_PER_INSTANCE, instance_dmg - eff_armor)
    dmg_to_shield = max(MIN_DAMAGE_PER_INSTANCE, instance_dmg - eff_shield_armor)

    # Simulate instance-by-instance: shields first, then hp. Count full cycles.
    hp_pool = float(d["hp"])
    shield_pool = float(d["shields"])
    instances = 0
    while hp_pool > 0:
        if shield_pool > 0:
            shield_pool -= dmg_to_shield
            if shield_pool < 0:  # overflow does NOT carry to hp in SC2
                shield_pool = 0
        else:
            hp_pool -= dmg_to_hp
        instances += 1
        if instances > 100000:  # safety; should never trigger with floor>0
            break

    cycles = math.ceil(instances / attack_count)

    return Breakpoint(
        attacker=a["unit_name"],
        defender=d["unit_name"],
        patch_era=patch,
        atk_weapon_level=atk,
        def_armor_level=armor,
        def_shield_level=shield,
        instance_damage=instance_dmg,
        attack_count=attack_count,
        bonus_applied=bonus_applies,
        damage_per_cycle_vs_hp=round(dmg_to_hp * attack_count, 2),
        cycles_to_kill=cycles,
        one_shot=(cycles == 1),
        two_shot=(cycles == 2),
        defender_total_hp=d["hp"] + d["shields"],
    )


def as_dict(bp):
    return asdict(bp)
