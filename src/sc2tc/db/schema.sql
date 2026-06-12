-- SC2 Theorycrafter — unit stats schema.
--
-- Every row is tagged to a patch_era. The same unit_name appears once per era,
-- so "zealot @ 5.0.16" and "zealot @ 5.0.15" are distinct rows. This is what makes
-- patch-diff queries ("what changed for the zealot?") and era-scoped breakpoint
-- tables possible without ever retraining anything.

-- Full rebuild each time — the DB is regenerable from seeds/dumps, and dropping ensures
-- schema changes (new columns) actually take effect.
DROP TABLE IF EXISTS unit_stats;

CREATE TABLE IF NOT EXISTS unit_stats (
    -- identity
    unit_name           TEXT    NOT NULL,
    race                TEXT    NOT NULL,          -- Protoss | Terran | Zerg
    patch_era           TEXT    NOT NULL,          -- e.g. '5.0.15', '5.0.16-ptr'

    -- defensive
    hp                  INTEGER NOT NULL,
    shields             INTEGER NOT NULL DEFAULT 0,
    armor               INTEGER NOT NULL DEFAULT 0,
    shield_armor        INTEGER NOT NULL DEFAULT 0, -- Protoss shields take separate armor
    armor_type          TEXT    NOT NULL DEFAULT '', -- space-joined tags: 'light biological'

    -- offensive (ground weapon; air handled later if needed)
    damage              INTEGER NOT NULL DEFAULT 0, -- per attack instance, before upgrades
    attack_count        INTEGER NOT NULL DEFAULT 1, -- instances per attack cycle (zealot=2)
    damage_bonus        INTEGER NOT NULL DEFAULT 0, -- extra dmg per instance vs bonus type
    damage_bonus_type   TEXT    NOT NULL DEFAULT '', -- armor tag the bonus applies to
    weapon_upgrade_step INTEGER NOT NULL DEFAULT 1, -- +dmg per instance per weapon-upgrade level
    attack_speed        REAL,                        -- seconds between attack cycles (game speed)
    range               REAL,

    -- anti-air weapon (separate from ground; a "target_type=Any" weapon fills both)
    air_damage          INTEGER NOT NULL DEFAULT 0,
    air_attack_count    INTEGER NOT NULL DEFAULT 1,
    air_damage_bonus    INTEGER NOT NULL DEFAULT 0,
    air_damage_bonus_type TEXT  NOT NULL DEFAULT '',
    air_attack_speed    REAL,
    air_range           REAL,
    is_flyer            INTEGER NOT NULL DEFAULT 0,   -- defender plane: 1 = attacked by anti-air

    -- caster / vision (from engine dump)
    energy_max          REAL,                        -- nullable: only casters have energy
    sight_range         REAL,

    -- economy / production
    supply_cost         REAL,
    mineral_cost        INTEGER,
    gas_cost            INTEGER,
    build_time_s        REAL,
    movement_speed      REAL,                        -- nullable: only filled when confident

    -- provenance: GM owner verifies seeded values; patch-note-exact values vs baseline
    verified            INTEGER NOT NULL DEFAULT 0,  -- 0 = pending owner sanity-check
    source              TEXT    NOT NULL DEFAULT '', -- 'patch-notes-5.0.16' | 'baseline-live' | ...

    PRIMARY KEY (unit_name, patch_era)
);

CREATE INDEX IF NOT EXISTS idx_unit_era  ON unit_stats (patch_era);
CREATE INDEX IF NOT EXISTS idx_unit_race ON unit_stats (race, patch_era);
