"""Tool definitions + dispatch — the bridge between an LLM and the verified data.

Each tool wraps a pure calculator or a DB read. The model NEVER answers from its
weights; when it needs a number, it calls one of these, which read the engine-sourced
DB. Tools return concise text. Schemas are provider-neutral here; backends.py adapts
them to Claude (`input_schema`) and Ollama/OpenAI (`function.parameters`) shapes.
"""

from ..db import connect, get_unit
from ..calc.breakpoints import breakpoint as _breakpoint
from ..calc.timing import simulate as _simulate


# --- tool implementations (each returns a short string) ----------------------

def get_unit_stats(unit_name, patch_era="5.0.16-ptr"):
    conn = connect()
    try:
        u = get_unit(conn, unit_name, patch_era)
    finally:
        conn.close()
    if u is None:
        return f"No unit named '{unit_name}' in {patch_era}. Call list_units to see valid names."

    def _weapon(dmg, cnt, bdmg, btype, rng):
        if not dmg:
            return None
        bonus = f" (+{bdmg} vs {btype})" if bdmg else ""
        return f"{dmg} x{cnt}{bonus}, range {rng}"

    weapons = []
    g = _weapon(u["damage"], u["attack_count"], u["damage_bonus"], u["damage_bonus_type"], u["range"])
    a = _weapon(u["air_damage"], u["air_attack_count"], u["air_damage_bonus"],
                u["air_damage_bonus_type"], u["air_range"])
    if g:
        weapons.append("ground " + g)
    if a:
        weapons.append("anti-air " + a)
    atk = "; ".join(weapons) if weapons else "no attack"
    flags = []
    if u["is_flyer"]:
        flags.append("flyer")
    if u["energy_max"]:
        flags.append(f"energy {int(u['energy_max'])}")
    flag_str = f", {', '.join(flags)}" if flags else ""
    return (f"{u['unit_name']} @ {patch_era}: {u['race']}, "
            f"hp {u['hp']}/shields {u['shields']}, armor {u['armor']} ({u['armor_type']}){flag_str}, "
            f"attack: {atk}, cost {u['mineral_cost']}m/{u['gas_cost']}g, supply {u['supply_cost']}, "
            f"build {u['build_time_s']}s. [source: {u['source']}]")


def compute_breakpoint(attacker, defender, atk_upgrade=0, defender_armor_upgrade=0,
                       defender_shield_upgrade=0, patch_era="5.0.16-ptr"):
    try:
        bp = _breakpoint(attacker, defender, atk=atk_upgrade, armor=defender_armor_upgrade,
                         shield=defender_shield_upgrade, patch=patch_era)
    except ValueError as e:
        return f"ERROR: {e}"
    return (f"{bp.summary()} Per instance: {bp.instance_damage} x{bp.attack_count} "
            f"(vs-type bonus {'applied' if bp.bonus_applied else 'n/a'}); "
            f"net {bp.damage_per_cycle_vs_hp}/cycle vs hp; "
            f"defender pool {bp.defender_total_hp} (hp+shields).")


def simulate_build_order(build_order, race, patch_era="5.0.16-ptr", make_workers=True):
    # macro mechanics (chrono/MULE/inject) are ALWAYS modeled — every real player uses them,
    # so there is no meaningful non-macro build. Not exposed as a toggle.
    try:
        r = _simulate(build_order, race, patch_era, make_workers=make_workers, macro=True)
    except Exception as e:
        return f"ERROR: {e}"
    fmt = lambda s: f"{int(s)//60}:{int(s) % 60:02d}"
    lines = [f"{race} @ {patch_era}, start {r.starting_workers} workers:"]
    for s in r.steps:
        if s.name not in ("Probe", "SCV", "Drone"):  # skip auto-workers for brevity
            lines.append(f"  {fmt(s.start_s)} start {s.name} (done {fmt(s.complete_s)})")
    for w in r.warnings:
        lines.append(f"  ! {w}")
    return "\n".join(lines) if len(lines) > 1 else lines[0] + " (no notable steps)"


def list_upgrades(race=None):
    """List researchable upgrades: engine name, friendly alias, research building, cost, time."""
    from ..calc.build_data import get_catalog
    from ..calc.upgrade_data import REQUIREMENTS
    races = [race] if race else ["Protoss", "Terran", "Zerg"]
    lines = []
    for r in races:
        for name, item in get_catalog(r).items():
            if item.kind == "upgrade":
                alias = REQUIREMENTS.get(name, (None, None, None, ""))[3]
                lines.append(f"{name} [{alias}]: at {item.built_by}, "
                             f"{item.mineral_cost}m/{item.gas_cost}g, research {item.build_time_s}s")
    return f"{len(lines)} upgrades — " + " | ".join(lines) if lines else "No upgrades loaded."


def list_units(race=None, patch_era="5.0.16-ptr"):
    conn = connect()
    try:
        if race:
            rows = conn.execute(
                "SELECT unit_name FROM unit_stats WHERE patch_era=? AND LOWER(race)=LOWER(?) ORDER BY unit_name",
                (patch_era, race)).fetchall()
        else:
            rows = conn.execute(
                "SELECT unit_name FROM unit_stats WHERE patch_era=? ORDER BY race, unit_name",
                (patch_era,)).fetchall()
    finally:
        conn.close()
    names = [r[0] for r in rows]
    return f"{len(names)} units @ {patch_era}: " + ", ".join(names) if names else f"No units for {patch_era}."


# --- tool registry (name, description, JSON-schema params, fn) ----------------

TOOLS = [
    {
        "name": "compute_breakpoint",
        "description": "Compute how many attack cycles (hits) for an attacker unit to kill a "
                       "defender unit, accounting for upgrades. Use for any 'how many hits', "
                       "'does X one-shot/two-shot Y', or breakpoint question.",
        "parameters": {
            "type": "object",
            "properties": {
                "attacker": {"type": "string", "description": "Attacker unit name, e.g. Zealot"},
                "defender": {"type": "string", "description": "Defender unit name, e.g. Zergling"},
                "atk_upgrade": {"type": "integer", "description": "Attacker weapon upgrade level 0-3", "default": 0},
                "defender_armor_upgrade": {"type": "integer", "description": "Defender armor upgrade 0-3", "default": 0},
                "defender_shield_upgrade": {"type": "integer", "description": "Defender shield upgrade 0-3 (Protoss)", "default": 0},
                "patch_era": {"type": "string", "description": "Patch era tag", "default": "5.0.16-ptr"},
            },
            "required": ["attacker", "defender"],
        },
        "fn": compute_breakpoint,
    },
    {
        "name": "get_unit_stats",
        "description": "Look up the verified stats (hp, shields, armor, armor type, damage, "
                       "range, cost, supply, build time) for one unit at a patch era.",
        "parameters": {
            "type": "object",
            "properties": {
                "unit_name": {"type": "string", "description": "Unit name, e.g. Stalker"},
                "patch_era": {"type": "string", "description": "Patch era tag", "default": "5.0.16-ptr"},
            },
            "required": ["unit_name"],
        },
        "fn": get_unit_stats,
    },
    {
        "name": "simulate_build_order",
        "description": "Simulate a build order and report when each structure/unit/UPGRADE starts "
                       "and completes, plus supply blocks. Use for 'when can I afford X', build "
                       "timing, and 'earliest +1 attack / upgrade' questions. Build order may "
                       "include upgrade names (from list_upgrades); the calculator auto-requires "
                       "the research building, so include that building (and an Assimilator/"
                       "Refinery/Extractor if the upgrade costs gas) earlier in the order.",
        "parameters": {
            "type": "object",
            "properties": {
                "build_order": {"type": "array", "items": {"type": "string"},
                                "description": "Ordered structures/units/upgrades, e.g. [\"Pylon\","
                                "\"Assimilator\",\"Forge\",\"ProtossGroundWeaponsLevel1\"]. Do NOT "
                                "include workers (Probe/SCV/Drone) — they are auto-produced — and "
                                "do NOT add a 2nd base unless expanding. Keep it minimal."},
                "race": {"type": "string", "enum": ["Protoss", "Terran", "Zerg"]},
                "patch_era": {"type": "string", "description": "Patch era tag", "default": "5.0.16-ptr"},
                "make_workers": {"type": "boolean", "description": "Continuously produce workers", "default": True},
            },
            "required": ["build_order", "race"],
        },
        "fn": simulate_build_order,
    },
    {
        "name": "list_units",
        "description": "List the valid unit names available in the DB, optionally filtered by race. "
                       "Call this when unsure of exact unit names (names are CamelCase, no spaces).",
        "parameters": {
            "type": "object",
            "properties": {
                "race": {"type": "string", "enum": ["Protoss", "Terran", "Zerg"]},
                "patch_era": {"type": "string", "description": "Patch era tag", "default": "5.0.16-ptr"},
            },
            "required": [],
        },
        "fn": list_units,
    },
    {
        "name": "list_upgrades",
        "description": "List researchable upgrades with their engine name, friendly alias, research "
                       "BUILDING, cost, and research time. Call this for any upgrade/research/tech "
                       "question (e.g. '+1 attack') to get the exact name and which building "
                       "researches it, then feed that into simulate_build_order for timing.",
        "parameters": {
            "type": "object",
            "properties": {"race": {"type": "string", "enum": ["Protoss", "Terran", "Zerg"]}},
            "required": [],
        },
        "fn": list_upgrades,
    },
]

_BY_NAME = {t["name"]: t for t in TOOLS}


def dispatch(name, args):
    """Execute a tool by name with a dict of arguments. Always returns a string."""
    tool = _BY_NAME.get(name)
    if tool is None:
        return f"ERROR: unknown tool '{name}'"
    try:
        return str(tool["fn"](**(args or {})))
    except TypeError as e:
        return f"ERROR: bad arguments for {name}: {e}"
