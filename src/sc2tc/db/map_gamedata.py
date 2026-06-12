"""Map the engine game-data dump (extract_gamedata.py output) into unit_stats fields,
and audit it against the hand-seeded values.

The static dump is authoritative for everything except HP/shields (those need a live
unit instance — see extract_gamedata.ROSTER_FOR_HP, which needs a map with start
locations). This module resolves the dump's records into our schema and diffs them
against the current seeds so we can see exactly which hand-entered values were wrong.
"""

import json
from pathlib import Path

from .extract_gamedata import LOOPS_PER_SECOND

_RACE = {1: "Terran", 2: "Zerg", 3: "Protoss"}

# Alternate forms / legacy / summoned-junk to drop so the roster is one row per real unit.
# Burrowed/Changeling are matched by name pattern; these are the exact-name extras
# (transform modes that duplicate a base unit, plus removed BW-era units).
_EXCLUDE_NAMES = {
    "MothershipCore", "DefilerMP", "DevourerMP", "GuardianMP", "CorsairMP", "ScourgeMP",
    "InfestorTerran", "OverlordTransport", "ObserverSiegeMode", "OverseerSiegeMode",
    "WarpPrismPhasing",  # no-weapon transform forms stay excluded (duplicate the base unit)
    # NOTE: SiegeTankSieged/LiberatorAG/HellionTank/VikingAssault/ThorAP are KEPT as distinct
    # rows — their combat stats differ sharply from the base unit and matter for breakpoints.
    "Nuke", "MULE", "Replicant", "TowerMine", "AutoTestAttacker",
    "AutoTestAttackTargetAir", "AutoTestAttackTargetGround",
    # campaign/co-op/summoned junk that slips past the cost/weapon filter
    "GhostAlternate", "GhostNova", "HERC", "HERCPlacement", "WarHound", "ArbiterMP",
    "ScoutMP", "Broodling", "LocustMP", "Interceptor",
}

# Units that fly — an attacker uses its ANTI-AIR weapon against these. GM-curated and
# era-independent (matches the engine's is_flying; verifiable in-game).
FLYERS = {
    "Phoenix", "VoidRay", "Oracle", "Carrier", "Tempest", "Mothership", "Observer", "WarpPrism",
    "VikingFighter", "Medivac", "Liberator", "LiberatorAG", "Banshee", "Raven", "Battlecruiser",
    "Mutalisk", "Corruptor", "BroodLord", "Viper", "Overlord", "Overseer",
}
# Substrings/suffixes that mark transient forms (eggs, cocoons, shades), test units,
# and campaign corpses — never a canonical ladder unit.
_EXCLUDE_PATTERNS = ("Burrowed", "Cocoon", "Egg", "Changeling", "Test",
                     "PhaseShift", "Phased", "ReviveCorpse")


def is_real_unit(rec):
    """True for one canonical, playable mobile unit (excludes structures, burrowed/
    transform/transient forms, changelings, test units, and legacy/campaign units)."""
    name = rec["name"]
    if rec["race"] not in (1, 2, 3):
        return False
    if "structure" in rec["attributes"]:
        return False
    if name in _EXCLUDE_NAMES or any(p in name for p in _EXCLUDE_PATTERNS):
        return False
    # a real unit costs something or has a weapon
    return bool(rec["mineral_cost"] or rec["gas_cost"] or rec["supply_cost"] or rec["weapons"])


def real_unit_names(records):
    return [r["name"] for r in records if is_real_unit(r)]


def load_dump(json_path):
    data = json.loads(Path(json_path).read_text())
    return {u["name"]: u for u in data["units"]}


def _weapon_for(rec, target_types):
    """First weapon usable vs the given target types (1=ground, 2=air, 3=any)."""
    for w in rec.get("weapons", []):
        if w["target_type"] in target_types:
            return w
    return None


def engine_stats(rec):
    """Resolve one engine record into unit_stats-shaped fields (ground + air weapons)."""
    w = _weapon_for(rec, (1, 3))       # ground weapon
    aw = _weapon_for(rec, (2, 3))      # anti-air weapon
    bonus = (w["bonus"][0] if w and w["bonus"] else None)
    abonus = (aw["bonus"][0] if aw and aw["bonus"] else None)
    return {
        "race": _RACE.get(rec["race"], str(rec["race"])),
        "armor": int(rec["armor"]),
        "armor_type": " ".join(rec["attributes"]),
        "damage": int(w["damage"]) if w else 0,
        "attack_count": int(w["attacks"]) if w else 1,
        "damage_bonus": int(bonus["damage"]) if bonus else 0,
        "damage_bonus_type": bonus["vs"] if bonus else "",
        "attack_speed": round(w["cooldown"], 3) if w else None,
        "range": round(w["range"], 3) if w else None,
        "air_damage": int(aw["damage"]) if aw else 0,
        "air_attack_count": int(aw["attacks"]) if aw else 1,
        "air_damage_bonus": int(abonus["damage"]) if abonus else 0,
        "air_damage_bonus_type": abonus["vs"] if abonus else "",
        "air_attack_speed": round(aw["cooldown"], 3) if aw else None,
        "air_range": round(aw["range"], 3) if aw else None,
        "is_flyer": 1 if rec["name"] in FLYERS else 0,
        "energy_max": (rec.get("energy_max") or None),  # 0 for non-casters -> NULL
        "sight_range": rec.get("sight_range"),
        "supply_cost": rec["supply_cost"],
        "supply_provided": int(rec["supply_provided"]),
        "mineral_cost": rec["mineral_cost"],
        "gas_cost": rec["gas_cost"],
        "build_time_s": round(rec["build_time_game"] / LOOPS_PER_SECOND, 1),
        "movement_speed": round(rec["movement_speed"], 3) or None,
        # hp/shields only present if the dump captured live instances:
        "hp": rec.get("hp"),
        "shields": rec.get("shields"),
    }


# Fields worth auditing against hand seeds (HP excluded — engine static lacks it).
_AUDIT_FIELDS = ["armor", "armor_type", "damage", "attack_count", "damage_bonus",
                 "damage_bonus_type", "supply_cost", "mineral_cost", "gas_cost",
                 "build_time_s"]


def audit_against_seed(json_path):
    """Diff engine values vs the hand-seeded 5.0.16 rows. Returns list of mismatches."""
    from .seed_5016 import UNITS_5016

    dump = load_dump(json_path)
    mismatches = []
    for seed in UNITS_5016:
        rec = dump.get(seed["unit_name"])
        if rec is None:
            mismatches.append((seed["unit_name"], "MISSING_IN_DUMP", None, None))
            continue
        eng = engine_stats(rec)
        for f in _AUDIT_FIELDS:
            sv, ev = seed.get(f), eng.get(f)
            # normalize armor_type token order before comparing
            if f == "armor_type":
                sv = " ".join(sorted((sv or "").split()))
                ev = " ".join(sorted((ev or "").split()))
            if isinstance(sv, float) or isinstance(ev, float):
                if sv is not None and ev is not None and abs(float(sv) - float(ev)) > 0.6:
                    mismatches.append((seed["unit_name"], f, sv, ev))
            elif sv != ev:
                mismatches.append((seed["unit_name"], f, sv, ev))
    return mismatches


# --- engine-sourced 5.0.16 unit_stats -----------------------------------------
# Two things the static dump can't give us (see audit), supplied by hand:
#   HP/shields  — not in static UnitTypeData (need a live instance). GM-known values;
#                 only Ghost changed in 5.0.16 (125->100). Upgrade to engine-HP later
#                 by debug-spawning on a map with real start locations.
#   ability-attacks — Sentry's beam and Baneling's explosion aren't "weapons", so the
#                 dump shows 0 damage. Override with GM-known values.
HP_OVERRIDE_5016 = {  # name: (hp, shields)
    "Probe": (20, 20), "Zealot": (100, 50), "Adept": (70, 70), "Stalker": (80, 80),
    "Sentry": (40, 40), "HighTemplar": (40, 40), "DarkTemplar": (40, 80),
    "SCV": (45, 0), "Marine": (45, 0), "Marauder": (125, 0), "Reaper": (60, 0),
    "Ghost": (100, 0),  # 5.0.16: 125 -> 100
    "Drone": (40, 0), "Zergling": (35, 0), "Baneling": (30, 0), "Roach": (145, 0),
    "Hydralisk": (90, 0), "Queen": (175, 0), "Overlord": (200, 0),
    # transform combat modes — same HP as the base unit (they aren't spawned for live HP)
    "SiegeTankSieged": (175, 0), "LiberatorAG": (180, 0), "HellionTank": (135, 0),
    "VikingAssault": (135, 0), "ThorAP": (400, 0),
}
ATTACK_OVERRIDE = {  # attacks absent from the static weapons list (ability/special beams)
    "Sentry": {"damage": 6, "attack_count": 1, "range": 5.0, "attack_speed": 1.0},
    "Baneling": {"damage": 16, "attack_count": 1, "damage_bonus": 19,
                 "damage_bonus_type": "light"},
    "Battlecruiser": {"damage": 8, "attack_count": 1, "range": 6.0},
    "VoidRay": {"damage": 6, "attack_count": 1, "damage_bonus": 4,
                "damage_bonus_type": "armored", "range": 6.0},
    # Oracle's Pulsar Beam is a channeled auto-attack (costs energy/s to keep active) so it
    # fits the auto-attack model. GM-VERIFY: live value 15 flat, range 4, ~0.61 cd; not
    # listed as changed in the 5.0.16 notes. verified stays 0 until owner confirms.
    "Oracle": {"damage": 15, "attack_count": 1, "range": 4.0, "attack_speed": 0.61},
    # NOT added (not repeating auto-attacks — would be misleading as a single weapon):
    #   Carrier  — damage is 8 Interceptors x (5x2); model as a swarm, not one weapon.
    #   Disruptor— Purification Nova is a one-shot cooldown ability (145 +55 vs shields AoE).
    #   Liberator AG — anti-ground lives on the LiberatorAG siege mode (a transform row, see
    #   _EXCLUDE_NAMES / TODO 'transform combat modes'), not the base flyer.
}


def build_unit_stats(json_path, patch_era):
    """Engine-sourced unit_stats rows for every real unit in a dump, tagged to patch_era.

    Works for any era (e.g. '5.0.16-ptr' from the PTR client, '5.0.15' from retail).
    HP comes from live instances captured during extraction; if a unit lacked a live
    capture, it falls back to HP_OVERRIDE_5016, else None. Ability-attacks (Sentry,
    Baneling, Battlecruiser, VoidRay) are patched from ATTACK_OVERRIDE — same units
    across eras, so the override applies to all."""
    dump = load_dump(json_path)
    rows = []
    for rec in dump.values():
        if not is_real_unit(rec):
            continue
        name = rec["name"]
        s = engine_stats(rec)
        live_hp = rec.get("hp") is not None  # engine HP present (debug-spawn worked)?
        fb_hp, fb_sh = HP_OVERRIDE_5016.get(name, (None, None))
        row = {
            "unit_name": name, "patch_era": patch_era,
            "hp": int(rec["hp"]) if live_hp else fb_hp,
            "shields": int(rec["shields"]) if live_hp else fb_sh,
            "shield_armor": 0,
            "race": s["race"], "armor": s["armor"], "armor_type": s["armor_type"],
            "damage": s["damage"], "attack_count": s["attack_count"],
            "damage_bonus": s["damage_bonus"], "damage_bonus_type": s["damage_bonus_type"],
            "weapon_upgrade_step": 1, "attack_speed": s["attack_speed"], "range": s["range"],
            "air_damage": s["air_damage"], "air_attack_count": s["air_attack_count"],
            "air_damage_bonus": s["air_damage_bonus"],
            "air_damage_bonus_type": s["air_damage_bonus_type"],
            "air_attack_speed": s["air_attack_speed"], "air_range": s["air_range"],
            "is_flyer": s["is_flyer"],
            "energy_max": s["energy_max"], "sight_range": s["sight_range"],
            "supply_cost": s["supply_cost"], "mineral_cost": s["mineral_cost"],
            "gas_cost": s["gas_cost"], "build_time_s": s["build_time_s"],
            "movement_speed": s["movement_speed"], "verified": 1 if live_hp else 0,
            "source": f"engine-{patch_era}" + (
                "" if live_hp else " (hp:gm-known)" if fb_hp is not None else " (hp:none)"),
        }
        if name in ATTACK_OVERRIDE:
            row.update(ATTACK_OVERRIDE[name])
            row["source"] += " (attack:gm-known)"
            row["verified"] = 0  # hand-supplied attack — needs GM sanity-check
        rows.append(row)
    return rows


def main():
    import argparse
    p = argparse.ArgumentParser(description="Audit hand-seeded unit_stats vs engine dump.")
    p.add_argument("--dump", default="data/extracted/gamedata_5016.json")
    args = p.parse_args()
    rows = audit_against_seed(args.dump)
    if not rows:
        print("No mismatches — hand seeds agree with the engine.")
        return
    print(f"{len(rows)} mismatch(es): unit / field / seed -> engine")
    for name, field, sv, ev in rows:
        print(f"  {name:16} {field:18} {sv!r:>22} -> {ev!r}")


if __name__ == "__main__":
    main()
