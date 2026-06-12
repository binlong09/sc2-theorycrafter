"""Production catalog — which building makes each unit + its tech prereqs (GM-curated),
merged with engine costs/supply/build-times so the timing calculator can build any
standard army unit (not just the handful that were hand-entered).

Like upgrade_data: the engine gives cost/supply/build_time; the production building and
tech requirements are GM-known and curated here. Workers are kept in build_data; this
covers army units. MORPHS are deferred (the ~5% not covered): Baneling, Ravager, Lurker,
BroodLord, Overseer, Archon (they consume a base unit, which the timing model can't yet
represent). See TODO.md.
"""

import json
from pathlib import Path

from .build_data import BuildItem

LOOPS_PER_SECOND = 22.4  # build_time loops -> seconds (in-game clock)

# unit_name: (race, built_by, prereqs). built_by is a production structure, 'larva',
# or a base name (Nexus/Hatchery) for base-built units.
PRODUCTION = {
    # --- Protoss (Gateway / Robotics / Stargate / Nexus) ---
    "Zealot": ("Protoss", "Gateway", ()),
    "Adept": ("Protoss", "Gateway", ("CyberneticsCore",)),
    "Stalker": ("Protoss", "Gateway", ("CyberneticsCore",)),
    "Sentry": ("Protoss", "Gateway", ("CyberneticsCore",)),
    "HighTemplar": ("Protoss", "Gateway", ("TemplarArchive",)),
    "DarkTemplar": ("Protoss", "Gateway", ("DarkShrine",)),
    "Immortal": ("Protoss", "RoboticsFacility", ()),
    "Colossus": ("Protoss", "RoboticsFacility", ("RoboticsBay",)),
    "Disruptor": ("Protoss", "RoboticsFacility", ("RoboticsBay",)),
    "Observer": ("Protoss", "RoboticsFacility", ()),
    "WarpPrism": ("Protoss", "RoboticsFacility", ()),
    "Phoenix": ("Protoss", "Stargate", ()),
    "VoidRay": ("Protoss", "Stargate", ()),
    "Oracle": ("Protoss", "Stargate", ()),
    "Carrier": ("Protoss", "Stargate", ("FleetBeacon",)),
    "Tempest": ("Protoss", "Stargate", ("FleetBeacon",)),
    "Mothership": ("Protoss", "Nexus", ("FleetBeacon",)),
    # --- Terran (Barracks / Factory / Starport) ---
    "Marine": ("Terran", "Barracks", ()),
    "Reaper": ("Terran", "Barracks", ()),
    "Marauder": ("Terran", "Barracks", ("BarracksTechLab",)),
    "Ghost": ("Terran", "Barracks", ("GhostAcademy", "BarracksTechLab")),
    "Hellion": ("Terran", "Factory", ()),
    "WidowMine": ("Terran", "Factory", ()),
    "Cyclone": ("Terran", "Factory", ()),
    "SiegeTank": ("Terran", "Factory", ("FactoryTechLab",)),
    "Thor": ("Terran", "Factory", ("Armory", "FactoryTechLab")),
    "VikingFighter": ("Terran", "Starport", ()),
    "Medivac": ("Terran", "Starport", ()),
    "Liberator": ("Terran", "Starport", ()),
    "Banshee": ("Terran", "Starport", ("StarportTechLab",)),
    "Raven": ("Terran", "Starport", ("StarportTechLab",)),
    "Battlecruiser": ("Terran", "Starport", ("FusionCore", "StarportTechLab")),
    # --- Zerg (larva, + Hatchery for the Queen) ---
    "Zergling": ("Zerg", "larva", ("SpawningPool",)),
    "Roach": ("Zerg", "larva", ("RoachWarren",)),
    "Hydralisk": ("Zerg", "larva", ("HydraliskDen",)),
    "Mutalisk": ("Zerg", "larva", ("Spire",)),
    "Corruptor": ("Zerg", "larva", ("Spire",)),
    "Infestor": ("Zerg", "larva", ("InfestationPit",)),
    "SwarmHostMP": ("Zerg", "larva", ("InfestationPit",)),
    "Ultralisk": ("Zerg", "larva", ("UltraliskCavern",)),
    "Viper": ("Zerg", "larva", ("Hive",)),
    "Queen": ("Zerg", "Hatchery", ("SpawningPool",)),
}

# Morphs consume an existing base unit. Modeled as one "from scratch" item: the engine
# dump's cost is already the TOTAL (base + morph), and build_time = base build + morph
# time (make the base unit, then morph it). morph_name: (race, base_unit, requires).
# Archon is omitted (merges TWO templars — not a single base unit). See TODO.
MORPHS = {
    "Baneling": ("Zerg", "Zergling", ("SpawningPool", "BanelingNest")),
    "Ravager": ("Zerg", "Roach", ("RoachWarren",)),
    "LurkerMP": ("Zerg", "Hydralisk", ("HydraliskDen", "LurkerDenMP")),
    "BroodLord": ("Zerg", "Corruptor", ("Spire", "GreaterSpire")),
    "Overseer": ("Zerg", "Overlord", ("Lair",)),
}


def load_production(dump_path, race=None):
    """Build {unit_name: BuildItem(kind='unit')} for every produced unit in PRODUCTION,
    pulling cost/supply/build_time from the engine dump."""
    data = json.loads(Path(dump_path).read_text())
    by_name = {u["name"]: u for u in data["units"]}
    items = {}
    for name, (r, bld, prereqs) in PRODUCTION.items():
        if race and r != race:
            continue
        u = by_name.get(name)
        if u is None:
            continue
        items[name] = BuildItem(
            name=name, race=r, mineral_cost=u["mineral_cost"], gas_cost=u["gas_cost"],
            build_time_s=round(u["build_time_game"] / LOOPS_PER_SECOND, 1), kind="unit",
            built_by=bld, supply_cost=u["supply_cost"], requires=tuple(prereqs),
            time_verified=True)
    for name, (r, base, prereqs) in MORPHS.items():
        if race and r != race:
            continue
        m, b = by_name.get(name), by_name.get(base)
        if m is None or b is None:
            continue
        # cost is total-from-scratch; build_time = base build + morph time (sequential).
        bt = round((b["build_time_game"] + m["build_time_game"]) / LOOPS_PER_SECOND, 1)
        items[name] = BuildItem(
            name=name, race=r, mineral_cost=m["mineral_cost"], gas_cost=m["gas_cost"],
            build_time_s=bt, kind="unit", built_by="larva", supply_cost=m["supply_cost"],
            requires=tuple(prereqs), time_verified=True)
    return items
