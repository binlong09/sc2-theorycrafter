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
    # Import here to avoid a circular import at module load.
    from .seed_5015 import UNITS_5015
    from .seed_5016 import UNITS_5016

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.execute("DELETE FROM unit_stats")  # full rebuild — DB is regenerable
        rows = [tuple(rec.get(col) for col in COLUMNS) for rec in (UNITS_5015 + UNITS_5016)]
        placeholders = ", ".join("?" for _ in COLUMNS)
        conn.executemany(
            f"INSERT INTO unit_stats ({', '.join(COLUMNS)}) VALUES ({placeholders})",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return db_path, len(UNITS_5015) + len(UNITS_5016)


def get_unit(conn, unit_name, patch_era):
    """Fetch one unit's stats for a patch era. Returns a sqlite3.Row or None.

    Case-insensitive on unit_name so 'zealot' and 'Zealot' both resolve.
    """
    cur = conn.execute(
        "SELECT * FROM unit_stats WHERE LOWER(unit_name) = LOWER(?) AND patch_era = ?",
        (unit_name, patch_era),
    )
    return cur.fetchone()


def list_eras(conn):
    cur = conn.execute("SELECT DISTINCT patch_era FROM unit_stats ORDER BY patch_era")
    return [r[0] for r in cur.fetchall()]
