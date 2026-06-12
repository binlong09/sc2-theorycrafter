"""Build-item catalog for the timing calculator.

A BuildItem is anything you can put in a build order: a worker, a supply provider,
a tech/production structure, or a unit. Costs and the *supply provided by bases* are
authoritative (cross-checked against the Zephyrus parser's game-extracted data and the
unit_stats DB). build_time_s values are seeded at BEST CONFIDENCE and flagged
`time_verified=False` — they affect *completion* timings (not affordability) and are
the first thing for the GM owner to calibrate against PTR replays.

Per-era handling:
  - Base supply (Nexus/CC/Hatchery) is NOT stored here — it's read from
    patch_config.EconConfig at simulate() time, so 5.0.15 (15/15/6) vs 5.0.16 (13/13/4)
    come out correct without duplicating data.
  - The only 5.0.16 build-item changes relevant to economic openers are those base
    supply values; structure costs/build-times are unchanged by the patch notes.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BuildItem:
    name: str
    race: str
    mineral_cost: int
    gas_cost: int
    build_time_s: float
    kind: str                       # 'worker' | 'supply' | 'structure' | 'unit'
    built_by: str                   # 'base' | 'worker' | 'larva' | <structure name>
    supply_cost: float = 0.0        # supply this consumes when produced
    supply_provided: int = 0        # supply this grants on completion (0 = read from econ for bases)
    requires: tuple = ()            # prerequisite structures that must be COMPLETE
    provides_gas: bool = False      # gas structure: assigns gas workers on completion
    is_base: bool = False           # a town hall — supply_provided comes from EconConfig
    time_verified: bool = False     # build_time_s confirmed against PTR? (owner calibrates)


def _i(name, race, m, g, t, kind, built_by, **kw):
    return BuildItem(name=name, race=race, mineral_cost=m, gas_cost=g,
                     build_time_s=t, kind=kind, built_by=built_by, **kw)


# build_time_s in real seconds (LotV "faster"). Costs/supply are authoritative;
# build times are approximate pending PTR verification (time_verified=False).
_PROTOSS = [
    _i("Probe", "Protoss", 50, 0, 12, "worker", "base", supply_cost=1, time_verified=True),
    _i("Pylon", "Protoss", 100, 0, 18, "supply", "worker", supply_provided=8),
    _i("Nexus", "Protoss", 400, 0, 71, "structure", "worker", is_base=True),
    _i("Assimilator", "Protoss", 75, 0, 21, "structure", "worker", provides_gas=True),
    _i("Gateway", "Protoss", 150, 0, 46, "structure", "worker"),
    _i("CyberneticsCore", "Protoss", 150, 0, 36, "structure", "worker", requires=("Gateway",)),
    # WarpGate transform: a Gateway morphs into a Warp Gate. 5.0.16 PTR cost 50/50 (was free
    # pre-patch) — cost from CLAUDE.md patch notes (ability-data, not yet engine-extracted);
    # 7s transform time is engine-verified. One per gateway you want to convert.
    _i("WarpGate", "Protoss", 50, 50, 7, "structure", "Gateway", requires=("WarpGateResearch",)),
    _i("Forge", "Protoss", 150, 0, 32, "structure", "worker"),
    _i("TwilightCouncil", "Protoss", 150, 100, 36, "structure", "worker", requires=("CyberneticsCore",)),
    _i("RoboticsFacility", "Protoss", 150, 100, 46, "structure", "worker", requires=("CyberneticsCore",)),
    _i("RoboticsBay", "Protoss", 150, 150, 46, "structure", "worker", requires=("RoboticsFacility",)),
    _i("Stargate", "Protoss", 150, 150, 43, "structure", "worker", requires=("CyberneticsCore",)),
    _i("FleetBeacon", "Protoss", 300, 200, 43, "structure", "worker", requires=("Stargate",)),
    _i("DarkShrine", "Protoss", 150, 150, 71, "structure", "worker", requires=("TwilightCouncil",)),
    _i("TemplarArchive", "Protoss", 150, 200, 36, "structure", "worker", requires=("TwilightCouncil",)),
    # army units come from production_data.py (engine-sourced); workers/structures are here.
]

_TERRAN = [
    _i("SCV", "Terran", 50, 0, 12, "worker", "base", supply_cost=1, time_verified=True),
    _i("SupplyDepot", "Terran", 100, 0, 21, "supply", "worker", supply_provided=8),
    _i("CommandCenter", "Terran", 400, 0, 71, "structure", "worker", is_base=True),
    # Orbital Command — morph from CC (enables MULE). Not is_base: the CC already counts.
    _i("OrbitalCommand", "Terran", 150, 0, 25, "structure", "CommandCenter", requires=("Barracks",)),
    _i("Refinery", "Terran", 75, 0, 21, "structure", "worker", provides_gas=True),
    _i("Barracks", "Terran", 150, 0, 46, "structure", "worker", requires=("SupplyDepot",)),
    _i("Factory", "Terran", 150, 100, 36, "structure", "worker", requires=("Barracks",)),
    _i("EngineeringBay", "Terran", 125, 0, 25, "structure", "worker"),
    _i("Armory", "Terran", 150, 50, 46, "structure", "worker", requires=("Factory",)),
    _i("BarracksTechLab", "Terran", 50, 25, 18, "structure", "worker", requires=("Barracks",)),
    _i("Starport", "Terran", 150, 100, 36, "structure", "worker", requires=("Factory",)),
    _i("FactoryTechLab", "Terran", 50, 25, 18, "structure", "worker", requires=("Factory",)),
    _i("StarportTechLab", "Terran", 50, 25, 18, "structure", "worker", requires=("Starport",)),
    _i("GhostAcademy", "Terran", 150, 50, 29, "structure", "worker", requires=("Barracks",)),
    _i("FusionCore", "Terran", 150, 150, 46, "structure", "worker", requires=("Starport",)),
]

_ZERG = [
    _i("Drone", "Zerg", 50, 0, 12, "worker", "larva", supply_cost=1, time_verified=True),
    _i("Overlord", "Zerg", 100, 0, 18, "supply", "larva", supply_provided=8),
    _i("Hatchery", "Zerg", 300, 0, 71, "structure", "worker", is_base=True),
    _i("Extractor", "Zerg", 25, 0, 21, "structure", "worker", provides_gas=True),
    _i("SpawningPool", "Zerg", 250, 0, 46, "structure", "worker"),  # engine: 250 (was 200)
    _i("EvolutionChamber", "Zerg", 125, 0, 25, "structure", "worker"),
    # Lair/Hive are MORPHS: built_by the prior base (occupies it), cost is the morph delta.
    _i("Lair", "Zerg", 150, 100, 57, "structure", "Hatchery", requires=("SpawningPool",)),
    _i("Hive", "Zerg", 200, 150, 71, "structure", "Lair", requires=("InfestationPit",)),
    _i("RoachWarren", "Zerg", 200, 0, 39, "structure", "worker", requires=("SpawningPool",)),
    _i("BanelingNest", "Zerg", 150, 50, 43, "structure", "worker", requires=("SpawningPool",)),
    _i("HydraliskDen", "Zerg", 150, 100, 29, "structure", "worker", requires=("Lair",)),
    _i("LurkerDenMP", "Zerg", 150, 150, 57, "structure", "worker", requires=("HydraliskDen",)),
    _i("InfestationPit", "Zerg", 150, 100, 36, "structure", "worker", requires=("Lair",)),
    _i("Spire", "Zerg", 200, 150, 66, "structure", "worker", requires=("Lair",)),
    # GreaterSpire is a morph of the Spire (occupies it); needed for Brood Lords.
    _i("GreaterSpire", "Zerg", 100, 150, 26, "structure", "Spire", requires=("Hive",)),
    _i("UltraliskCavern", "Zerg", 200, 200, 46, "structure", "worker", requires=("Hive",)),
]

_CATALOGS = {
    "Protoss": {i.name: i for i in _PROTOSS},
    "Terran": {i.name: i for i in _TERRAN},
    "Zerg": {i.name: i for i in _ZERG},
}

# Upgrades + produced army units are loaded lazily from the engine dump (costs/times
# authoritative there); building/prereq mappings are curated in upgrade_data/production_data.
_UPGRADES = None
_PRODUCTION = None


def _dump_path():
    from pathlib import Path
    return Path(__file__).resolve().parents[3] / "data" / "extracted" / "gamedata_5016.json"


def _upgrades():
    global _UPGRADES
    if _UPGRADES is None:
        from .upgrade_data import load_upgrades
        d = _dump_path()
        _UPGRADES = load_upgrades(d) if d.exists() else {}
    return _UPGRADES


def _production():
    global _PRODUCTION
    if _PRODUCTION is None:
        from .production_data import load_production
        d = _dump_path()
        _PRODUCTION = load_production(d) if d.exists() else {}
    return _PRODUCTION


def get_catalog(race):
    """Return {item_name: BuildItem} for a race: hand-entered structures/workers, plus
    engine-sourced produced army units and researchable upgrades."""
    if race not in _CATALOGS:
        raise KeyError(f"Unknown race '{race}'. Known: {sorted(_CATALOGS)}")
    cat = dict(_CATALOGS[race])
    cat.update({n: u for n, u in _production().items() if u.race == race})
    cat.update({n: u for n, u in _upgrades().items() if u.race == race})
    return cat


def get_item(race, name):
    cat = get_catalog(race)
    if name not in cat:
        raise KeyError(
            f"'{name}' not in {race} build catalog. Known: {sorted(cat)}. "
            "Add it to build_data.py if you need it."
        )
    return cat[name]
