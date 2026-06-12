"""Authoritative game-data extractor — dumps the SC2 client's static Data to JSON.

This is the backbone of the patch-update pipeline (Task 4). Instead of hand-seeding
unit stats, we launch the *installed PTR client* and read its engine-resolved static
data (UnitTypeData), which carries build_time, costs, supply, armor, movement_speed,
attributes (= armor_type), and weapons (damage, attacks, range, bonus-vs-attribute).
Re-run after each patch -> authoritative values in minutes, tagged by patch_era.

USAGE (once a map exists in <SC2 install>/Maps):
    set SC2PATH=D:\\StarCraft II Public Test         # the PTR client = 5.0.16 data
    python -m sc2tc.db.extract_gamedata --map Empty --out data/extracted/gamedata_5016.json

REQUIREMENTS:
    - burnysc2 (python-sc2) installed.
    - SC2PATH pointing at the client whose patch you want (PTR for 5.0.16).
    - One .SC2Map in <SC2PATH>/Maps (the map content is irrelevant; we only need the
      client to reach the 'in_game' state where the Data request is served).

TIME UNITS — READ THIS:
    build_time is recorded RAW from the engine and labeled `build_time_game`. SC2 has
    a 1.4x gap between "game-time" (the in-game clock players use) and real wall time.
    Our income model is calibrated in game-clock seconds, so build times must match that
    clock. Before trusting these values, verify ONE structure against the in-game clock
    (start it, read the finish time) to confirm whether the engine value is already in
    game-clock seconds or needs the 1.4x conversion. Do not guess — verify, then set
    BUILD_TIME_TO_CLOCK below and re-map.
"""

import argparse
import json
import os
from pathlib import Path

# Engine build_time is in GAME LOOPS. Dividing by 22.4 (loops/sec at Faster) reproduces
# every known build time exactly (Probe 12.1, Zealot 28.0, Nexus 71.4, HighTemplar 40.0),
# i.e. the seconds players read off the in-game clock. Pending one live confirmation:
# start a Pylon and check it finishes at ~0:18 on the clock (22.4) and not ~0:25 (16).
LOOPS_PER_SECOND = 22.4
BUILD_TIME_TO_CLOCK = 1.0 / LOOPS_PER_SECOND

# s2clientprotocol Attribute enum -> our armor_type tags.
_ATTRIBUTES = {
    1: "light", 2: "armored", 3: "biological", 4: "mechanical", 5: "robotic",
    6: "psionic", 7: "massive", 8: "structure", 9: "hover", 10: "heroic", 11: "summoned",
}


def _unit_record(proto):
    """Flatten one UnitTypeData proto into a plain dict (ground weapon emphasized)."""
    attrs = [_ATTRIBUTES.get(a, str(a)) for a in proto.attributes]
    rec = {
        "unit_id": proto.unit_id,
        "name": proto.name,
        "race": int(proto.race),
        "mineral_cost": proto.mineral_cost,
        "gas_cost": proto.vespene_cost,
        "supply_cost": round(proto.food_required, 2),
        "supply_provided": round(proto.food_provided, 2),
        "build_time_game": round(proto.build_time, 3),          # RAW engine value
        "build_time_clock": round(proto.build_time * BUILD_TIME_TO_CLOCK, 3),
        "armor": proto.armor,
        "movement_speed": round(proto.movement_speed, 3),
        "sight_range": round(proto.sight_range, 3),
        "attributes": attrs,                                    # -> armor_type
        "weapons": [],
    }
    for w in proto.weapons:
        rec["weapons"].append({
            "target_type": int(w.type),                         # 1 ground, 2 air, 3 any
            "damage": round(w.damage, 3),
            "attacks": w.attacks,                               # instances per cycle
            "range": round(w.range, 3),
            "cooldown": round(w.speed, 3),
            "bonus": [{"vs": _ATTRIBUTES.get(b.attribute, str(b.attribute)),
                       "damage": round(b.bonus, 3)} for b in w.damage_bonus],
        })
    return rec


def _upgrade_record(proto):
    """Flatten one UpgradeData proto. research_time is in game loops (like build_time)."""
    return {
        "upgrade_id": proto.upgrade_id,
        "name": proto.name,
        "mineral_cost": proto.mineral_cost,
        "gas_cost": proto.vespene_cost,
        "research_time_game": round(proto.research_time, 3),
        "research_time_s": round(proto.research_time * BUILD_TIME_TO_CLOCK, 3),  # clock seconds
        "ability_id": proto.ability_id,
    }


def build_dump_bot():
    """Construct the dumper bot lazily so importing this module doesn't require sc2."""
    from sc2.bot_ai import BotAI
    from sc2.ids.unit_typeid import UnitTypeId

    class _DumpBot(BotAI):
        out_path = None  # set by caller

        def _write(self):
            Path(self.out_path).parent.mkdir(parents=True, exist_ok=True)
            data = {"units": self._records, "upgrades": getattr(self, "_upgrades", [])}
            Path(self.out_path).write_text(json.dumps(data, indent=2))

        async def on_start(self):
            # 1) static data dump (costs/supply/build_time/armor/weapons/speed + upgrades).
            # Written immediately so a later spawn failure can't lose it.
            self._records = [_unit_record(u._proto) for u in self.game_data.units.values()]
            self._upgrades = [_upgrade_record(u._proto) for u in self.game_data.upgrades.values()]
            self._by_id = {r["unit_id"]: r for r in self._records}
            self._name_to_id = {r["name"]: r["unit_id"] for r in self._records}
            self._write()
            # 2) spawn every real unit under our control to read live HP. Spawning in
            # on_start gives both players units before the win-check fires. Needs a map
            # with real start locations (Melee init) so the bots start with bases too.
            from .map_gamedata import is_real_unit
            pos = self.game_info.map_center
            cmds = [[UnitTypeId(r["unit_id"]), 1, pos, 1]
                    for r in self._records if is_real_unit(r)]
            cmds.append([UnitTypeId(self._name_to_id["SCV"]), 1, pos, 2])  # keep opponent alive
            print(f"Spawning {len(cmds)} units for HP capture")
            await self.client.debug_create_unit(cmds)

        async def on_step(self, iteration):
            if iteration < 2:
                return  # let the spawned units materialize
            # 3) read max HP/shield/energy off the instances, merge into the records
            got = 0
            for u in self.all_own_units:
                rec = self._by_id.get(int(u.type_id.value))
                if rec is not None and "hp" not in rec:
                    rec["hp"] = round(u.health_max, 1)
                    rec["shields"] = round(u.shield_max, 1)
                    rec["energy_max"] = round(u.energy_max, 1)
                    got += 1
            self._write()
            print(f"Dumped {len(self._records)} records ({got} with live HP) -> {self.out_path}")
            await self.client.quit()

    return _DumpBot


def main(argv=None):
    p = argparse.ArgumentParser(description="Dump SC2 client static data to JSON.")
    p.add_argument("--map", default="Empty", help="map name in <SC2PATH>/Maps (content irrelevant)")
    p.add_argument("--out", default="data/extracted/gamedata.json", help="output JSON path")
    args = p.parse_args(argv)

    if "SC2PATH" not in os.environ:
        raise SystemExit("Set SC2PATH to the client install (e.g. 'D:\\StarCraft II Public Test').")

    from sc2 import maps
    from sc2.main import run_game
    from sc2.data import Race, Difficulty
    from sc2.player import Bot, Computer

    DumpBot = build_dump_bot()
    bot = DumpBot()
    bot.out_path = args.out
    run_game(
        maps.get(args.map),
        [Bot(Race.Protoss, bot), Computer(Race.Terran, Difficulty.VeryEasy)],
        realtime=False,
    )


if __name__ == "__main__":
    main()
