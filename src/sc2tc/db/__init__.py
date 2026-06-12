"""DB build + access for the unit_stats table.

Build the SQLite file from the seed datasets:
    python -m sc2tc.db.build            # writes data/sc2tc.db

Query at runtime:
    from sc2tc.db import connect, get_unit
    conn = connect()
    z = get_unit(conn, "Zealot", "5.0.16-ptr")
"""

import sqlite3
from pathlib import Path

# Repo-root/data/sc2tc.db — resolved from this file's location (src/sc2tc/db/).
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "sc2tc.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Columns in insert order — must match schema.sql.
COLUMNS = [
    "unit_name", "race", "patch_era",
    "hp", "shields", "armor", "shield_armor", "armor_type",
    "damage", "attack_count", "damage_bonus", "damage_bonus_type",
    "weapon_upgrade_step", "attack_speed", "range",
    "air_damage", "air_attack_count", "air_damage_bonus", "air_damage_bonus_type",
    "air_attack_speed", "air_range", "is_flyer",
    "energy_max", "sight_range",
    "supply_cost", "mineral_cost", "gas_cost", "build_time_s", "movement_speed",
    "verified", "source",
]


def connect(db_path=DEFAULT_DB_PATH):
    """Open a connection with Row access (dict-like rows)."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def build(db_path=DEFAULT_DB_PATH):
    """(Re)build the unit_stats table from all seed eras. Idempotent."""
    # Each era prefers authoritative engine data (data/extracted/gamedata_<era>.json,
    # dumped by extract_gamedata against the matching client) and falls back to the
    # hand seed if that dump hasn't been generated yet.
    extracted = REPO_ROOT / "data" / "extracted"
    units = []
    for era, dump_name, seed_mod, seed_attr in (
        ("5.0.15", "gamedata_5015.json", ".seed_5015", "UNITS_5015"),       # retail / live
        ("5.0.16-ptr", "gamedata_5016.json", ".seed_5016", "UNITS_5016"),   # PTR
    ):
        dump = extracted / dump_name
        if dump.exists():
            from .map_gamedata import build_unit_stats
            units += build_unit_stats(dump, era)
        else:
            import importlib
            mod = importlib.import_module(seed_mod, __package__)
            units += getattr(mod, seed_attr)

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.execute("DELETE FROM unit_stats")  # full rebuild — DB is regenerable
        rows = [tuple(rec.get(col) for col in COLUMNS) for rec in units]
        placeholders = ", ".join("?" for _ in COLUMNS)
        conn.executemany(
            f"INSERT INTO unit_stats ({', '.join(COLUMNS)}) VALUES ({placeholders})",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return db_path, len(units)


import re

# Common player nicknames -> canonical engine name. The normalizer below already handles
# spacing/case ("void ray"->VoidRay, "siege tank"->SiegeTank, "high templar"->HighTemplar),
# so this only lists shorthands that DON'T normalize directly.
_ALIASES = {
    "ling": "Zergling", "lings": "Zergling", "bling": "Baneling", "blings": "Baneling",
    "bane": "Baneling", "banes": "Baneling", "muta": "Mutalisk", "mutas": "Mutalisk",
    "hydra": "Hydralisk", "hydras": "Hydralisk", "ultra": "Ultralisk", "ultras": "Ultralisk",
    "lurker": "LurkerMP", "lurkers": "LurkerMP", "swarmhost": "SwarmHostMP",
    "swarmhosts": "SwarmHostMP", "corrupter": "Corruptor", "ovie": "Overlord",
    "ovies": "Overlord", "bc": "Battlecruiser", "bcs": "Battlecruiser",
    "hellbat": "HellionTank", "hellbats": "HellionTank", "viking": "VikingFighter",
    "vikings": "VikingFighter", "tank": "SiegeTank", "tanks": "SiegeTank",
    "siegedtank": "SiegeTankSieged", "mine": "WidowMine", "mines": "WidowMine",
    "ht": "HighTemplar", "hts": "HighTemplar", "dt": "DarkTemplar", "dts": "DarkTemplar",
    "obs": "Observer", "prism": "WarpPrism", "lib": "Liberator", "libs": "Liberator",
    "vr": "VoidRay", "muta lisk": "Mutalisk",
}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def resolve_unit_name(conn, name, patch_era):
    """Map a player's unit name to the canonical DB name, or None. Tries exact (case-
    insensitive), then a nickname alias, then a normalized match (ignoring spaces/case)."""
    row = conn.execute(
        "SELECT unit_name FROM unit_stats WHERE LOWER(unit_name)=LOWER(?) AND patch_era=?",
        (name, patch_era)).fetchone()
    if row:
        return row[0]
    n = _ALIASES.get(_norm(name))
    n = _norm(n) if n else _norm(name)
    for (dbname,) in conn.execute(
            "SELECT unit_name FROM unit_stats WHERE patch_era=?", (patch_era,)).fetchall():
        if _norm(dbname) == n:
            return dbname
    return None


def get_unit(conn, unit_name, patch_era):
    """Fetch one unit's stats for a patch era. Returns a sqlite3.Row or None.

    Resolves nicknames/spacing ('muta'->Mutalisk, 'sieged tank'->SiegeTankSieged) via
    resolve_unit_name so player-typed names work.
    """
    canonical = resolve_unit_name(conn, unit_name, patch_era)
    if canonical is None:
        return None
    return conn.execute(
        "SELECT * FROM unit_stats WHERE unit_name = ? AND patch_era = ?",
        (canonical, patch_era),
    ).fetchone()


def list_eras(conn):
    cur = conn.execute("SELECT DISTINCT patch_era FROM unit_stats ORDER BY patch_era")
    return [r[0] for r in cur.fetchall()]
