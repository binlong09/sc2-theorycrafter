"""5.0.16 PTR unit dataset — derived from the 5.0.15 baseline by applying a diff.

Only unit-stat changes live here. Game-wide economy / structure changes from
5.0.16 (starting_workers 12->8, mineral patch sizes, CC/Nexus/Hatch supply, etc.)
are NOT unit stats — they belong to the timing calculator's patch config
(see calc/patch_config.py) and are referenced there, parameterized, never hard-coded.

Source of every value below: the 5.0.16 PTR patch notes captured in CLAUDE.md.
Still verified=0 until the GM owner confirms against the live PTR client.

PATCH_ERA tag for this dataset: '5.0.16-ptr'
"""

import copy

from .seed_5015 import UNITS_5015

PATCH_ERA = "5.0.16-ptr"

# Per-unit field overrides straight from the 5.0.16 PTR notes (CLAUDE.md).
# A unit absent here is carried over from 5.0.15 unchanged.
DIFF = {
    # Ghost — heavily reworked: tankier-cost (more supply), squishier (less hp),
    # flat 20 dmg replacing 10(+10 vs Light), longer range.
    "Ghost": {
        "hp": 100,
        "supply_cost": 3,
        "damage": 20,
        "damage_bonus": 0,
        "damage_bonus_type": "",
        "range": 7,
    },
    # Overlord — slower base movement (0.9 -> 0.7).
    "Overlord": {"movement_speed": 0.7},
    # Protoss Gateway pre-warpgate build times (warpgate is now a Gateway speed-up,
    # not a transform — these are the raw Gateway production times).
    "Zealot": {"build_time_s": 28},
    "Adept": {"build_time_s": 28},
    "Stalker": {"build_time_s": 28},
    "Sentry": {"build_time_s": 24},
    "HighTemplar": {"build_time_s": 40},
    "DarkTemplar": {"build_time_s": 40},
}


def _build():
    units = []
    for base in UNITS_5015:
        rec = copy.deepcopy(base)
        rec["patch_era"] = PATCH_ERA
        diff = DIFF.get(rec["unit_name"])
        if diff:
            rec.update(diff)
            rec["source"] = "patch-notes-5.0.16-ptr"
        else:
            rec["source"] = "baseline-carried-5.0.16-ptr"
        units.append(rec)
    return units


UNITS_5016 = _build()
