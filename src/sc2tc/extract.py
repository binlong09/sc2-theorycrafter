"""Extract a structured build-order timeline from a .SC2Replay file.

Output: one JSON per replay matching the schema in the project plan
(schema_version=1). Replays are tagged with base_build + patch_era so
downstream training-data curation can filter by balance era.

CLI:
  python -m sc2tc.extract --replay <path> [--out <file>]
  python -m sc2tc.extract --dir <dir>     [--out-dir <dir>] [--limit-seconds N]

The extractor builds on the Zephyrus parser (sibling repo). It does NOT
re-decode replay events — Zephyrus already gives us a structured per-object
view via Player.objects + Player.upgrades.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zephyrus_sc2_parser import parse_replay

from sc2tc.patch_eras import build_to_era


SCHEMA_VERSION = 1

# Unit names that should not appear in a build order (transient game objects).
LARVA_LIKE: set[str] = {
    "Larva", "Egg", "Broodling", "Locust", "LocustMP", "LocustMPFlying",
    "AdeptPhaseShift",
}

WORKERS: set[str] = {"SCV", "Probe", "Drone", "MULE"}


@dataclass
class ExtractError(Exception):
    path: Path
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _supply_at_gameloop(timeline: list[dict], player_id: int, gameloop: int) -> int:
    """Look up the most recent supply snapshot at-or-before `gameloop`."""
    best = 0
    for tick in timeline:
        ps = tick.get(player_id)
        if not ps:
            continue
        if ps["gameloop"] <= gameloop:
            best = ps["supply"]
        else:
            break
    return best


def _classify(obj: Any) -> str:
    if "BUILDING" in obj.type:
        return "building"
    if "WORKER" in obj.type:
        return "worker"
    return "unit"


def _build_events(player: Any, timeline: list[dict]) -> list[dict]:
    events: list[dict] = []
    for obj in player.objects.values():
        if obj.init_time is None:
            continue
        if obj.name in LARVA_LIKE:
            continue
        gameloop = obj.init_time
        events.append({
            "time_s": int(gameloop / 22.4),
            "gameloop": gameloop,
            "supply": _supply_at_gameloop(timeline, player.player_id, gameloop),
            "name": obj.name,
            "kind": _classify(obj),
            "mineral_cost": obj.mineral_cost,
            "gas_cost": obj.gas_cost,
        })
    events.sort(key=lambda e: (e["gameloop"], e["name"]))
    return events


def _upgrade_events(player: Any) -> list[dict]:
    out = []
    for up in player.upgrades:
        # Upgrade.completed_at is stringified gameloop in current Zephyrus
        try:
            gameloop = int(up.completed_at)
        except (TypeError, ValueError):
            continue
        out.append({
            "time_s": int(gameloop / 22.4),
            "gameloop": gameloop,
            "name": up.name,
        })
    out.sort(key=lambda e: e["gameloop"])
    return out


def extract_replay(
    path: Path,
    *,
    limit_seconds: int | None = None,
    local: bool = True,
    network: bool = True,
) -> dict:
    """Parse one replay and return the training-data-shaped dict."""
    if not path.exists():
        raise ExtractError(path, "file does not exist")

    try:
        replay = parse_replay(str(path), local=local, tick=112, network=network)
    except Exception as e:
        raise ExtractError(path, f"parse failed: {type(e).__name__}: {e}") from e

    meta = replay.metadata
    summary = replay.summary
    base_build = meta.get("base_build")
    winner_pid = meta.get("winner")

    players_out: list[dict] = []
    for pid, player in replay.players.items():
        build_order = _build_events(player, replay.timeline)
        upgrades = _upgrade_events(player)
        if limit_seconds is not None:
            build_order = [e for e in build_order if e["time_s"] <= limit_seconds]
            upgrades = [e for e in upgrades if e["time_s"] <= limit_seconds]

        result = "win" if winner_pid == pid else "loss" if winner_pid is not None else "unknown"

        players_out.append({
            "pid": pid,
            "name": player.name,
            "race": player.race,
            "mmr": summary.get("mmr", {}).get(pid),
            "apm": summary.get("apm", {}).get(pid),
            "sq": summary.get("sq", {}).get(pid),
            "result": result,
            "build_order": build_order,
            "upgrades": upgrades,
        })

    played_at = meta["played_at"]
    return {
        "schema_version": SCHEMA_VERSION,
        "replay_hash": _sha256(path),
        "base_build": base_build,
        "patch_era": build_to_era(base_build) if base_build is not None else None,
        "map": meta["map"],
        "played_at": played_at.isoformat() if hasattr(played_at, "isoformat") else str(played_at),
        "game_length_s": meta["game_length"],
        "winner_pid": winner_pid,
        "players": players_out,
    }


def _write_json(data: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _cmd_replay(args: argparse.Namespace) -> int:
    path = Path(args.replay)
    data = extract_replay(
        path,
        limit_seconds=args.limit_seconds,
        local=args.local,
        network=args.network,
    )
    if args.out:
        _write_json(data, Path(args.out))
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        print()
    return 0


def _cmd_dir(args: argparse.Namespace) -> int:
    src = Path(args.dir)
    if not src.is_dir():
        print(f"error: {src} is not a directory", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    replays = sorted(src.glob("*.SC2Replay"))
    if not replays:
        print(f"no .SC2Replay files in {src}", file=sys.stderr)
        return 1

    ok = 0
    fail = 0
    for r in replays:
        try:
            data = extract_replay(
                r,
                limit_seconds=args.limit_seconds,
                local=args.local,
                network=args.network,
            )
        except ExtractError as e:
            print(f"SKIP {r.name}: {e.reason}", file=sys.stderr)
            fail += 1
            continue
        dest = out_dir / f"{data['replay_hash']}.json"
        _write_json(data, dest)
        ok += 1
        print(f"  {r.name} -> {dest.name}", file=sys.stderr)

    print(f"\nextracted {ok} replays, {fail} skipped", file=sys.stderr)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sc2tc.extract", description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=False)

    # Flat invocation: --replay or --dir at the top level
    parser.add_argument("--replay", help="path to a single .SC2Replay")
    parser.add_argument("--dir", help="directory of .SC2Replay files to batch extract")
    parser.add_argument("--out", help="output JSON path (default: stdout, --replay mode only)")
    parser.add_argument("--out-dir", default="data/extracted", help="output directory (--dir mode)")
    parser.add_argument("--limit-seconds", type=int, default=None,
                        help="cap build_order/upgrades at this many in-game seconds")
    parser.add_argument("--local", action="store_true", default=True,
                        help="parse replays even without MMR (default true)")
    parser.add_argument("--no-local", dest="local", action="store_false")
    parser.add_argument("--network", action="store_true", default=True,
                        help="allow network for map dimension lookups (default true)")
    parser.add_argument("--no-network", dest="network", action="store_false")

    args = parser.parse_args(argv)

    if bool(args.replay) == bool(args.dir):
        parser.error("specify exactly one of --replay or --dir")

    if args.replay:
        return _cmd_replay(args)
    return _cmd_dir(args)


if __name__ == "__main__":
    sys.exit(main())
