"""Game-wide economy / structure constants, per patch era.

These are NOT unit stats (they don't belong in unit_stats) — they're the global
parameters the timing calculator (Task 3) reads: starting workers, mineral patch
sizes, structure supply, etc. Every era is a full EconConfig so the timing model
can be run for 5.0.15 vs 5.0.16 and the two outputs compared directly.

CRITICAL (CLAUDE.md): starting_workers must always be a parameter. Never hard-code
8 (or 12) anywhere downstream — read it from the EconConfig for the chosen era.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EconConfig:
    patch_era: str
    starting_workers: int
    large_mineral_patch: int
    small_mineral_patch: int
    total_minerals_per_base: int
    vespene_geyser: int
    rich_vespene_harvest_return: int
    # Structure supply provided (the supply your base/tech adds).
    command_center_supply: int
    nexus_supply: int
    hatchery_supply: int
    source: str = ""
    notes: dict = field(default_factory=dict)


ECON_5015 = EconConfig(
    patch_era="5.0.15",
    starting_workers=12,
    large_mineral_patch=1800,
    small_mineral_patch=900,
    total_minerals_per_base=10800,
    vespene_geyser=2250,
    rich_vespene_harvest_return=8,
    command_center_supply=15,
    nexus_supply=15,
    hatchery_supply=6,
    source="baseline-live-5.0.15",
)

# 5.0.16 PTR — the economy overhaul. Source: CLAUDE.md patch notes.
ECON_5016 = EconConfig(
    patch_era="5.0.16-ptr",
    starting_workers=8,            # <-- headline change; everything downstream reads this
    large_mineral_patch=1600,
    small_mineral_patch=1200,
    total_minerals_per_base=11200,
    vespene_geyser=2500,
    rich_vespene_harvest_return=6,
    command_center_supply=13,
    nexus_supply=12,               # ENGINE-VERIFIED: Nexus=12, CC=13 (asymmetric! CLAUDE.md said both 13)
    hatchery_supply=4,             # 33% supply cut per hatch — big Zerg impact
    source="patch-notes-5.0.16-ptr",
)

ECON_BY_ERA = {c.patch_era: c for c in (ECON_5015, ECON_5016)}


def get_econ(patch_era):
    """Return the EconConfig for a patch era. Raises KeyError if unknown."""
    try:
        return ECON_BY_ERA[patch_era]
    except KeyError:
        raise KeyError(
            f"No economy config for era '{patch_era}'. Known: {sorted(ECON_BY_ERA)}"
        )
