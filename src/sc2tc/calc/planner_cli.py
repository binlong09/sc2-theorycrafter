"""CLI for the goal-driven build-order planner.

    # 2-base +1 charge-zealot timing in PvZ:
    python -m sc2tc.calc.planner_cli Protoss --units Zealot:8 --upgrades "+1 attack" charge --bases 2

    # 1-base Terran bio with stim:
    python -m sc2tc.calc.planner_cli Terran --units Marine:8 Marauder:4 --upgrades stim

    # compare the same goal on live 5.0.15:
    python -m sc2tc.calc.planner_cli Protoss --units Zealot:8 --upgrades charge --bases 2 --patch 5.0.15

Units take an optional count as Name:count (default 6). Unit/upgrade names may be friendly
('muta', '+1 attack', 'charge') — they resolve to the engine names.
"""

import argparse
import sys

from .planner import plan_build

# The table uses Unicode (em-dash, mid-dot); a Windows cp1252 console crashes on those.
# Reconfigure like sc2tc.agent.cli does so the CLI is safe on a bare terminal.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def _parse_units(entries):
    out = []
    for e in (entries or []):
        name, sep, cnt = e.partition(":")
        out.append((name, int(cnt)) if sep and cnt.isdigit() else name)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="SC2 goal-driven build-order planner.")
    p.add_argument("race", choices=["Protoss", "Terran", "Zerg"])
    p.add_argument("--units", nargs="*", default=[],
                   help="army composition RATIO, e.g. Zealot:2 HighTemplar:1 (weights, not counts)")
    p.add_argument("--upgrades", nargs="*", default=[], help="upgrades, e.g. '+1 attack' charge")
    p.add_argument("--bases", type=int, default=1, help="target town-hall count (default 1)")
    p.add_argument("--production-total", type=int, default=None,
                   help="TOTAL of the main production building (the 'N-gate' count)")
    p.add_argument("--production-per-base", type=int, default=None,
                   help="production buildings per base (default: P/T 4, Zerg 1)")
    p.add_argument("--gas-per-base", type=int, default=1,
                   help="geysers per base, 0-2 (1=economic, 2=tech/all-in; capped at 2)")
    p.add_argument("--army-supply", type=int, default=None,
                   help="army-supply ceiling to produce up to (default 50 x bases, capped 200)")
    p.add_argument("--no-warpgate", action="store_true",
                   help="Protoss: skip warp-gate research + transforms")
    p.add_argument("--patch", default="5.0.16-ptr", help="patch era tag")
    p.add_argument("--order", action="store_true", help="also print the raw assembled build order")
    args = p.parse_args(argv)

    plan = plan_build(args.race, units=_parse_units(args.units), upgrades=args.upgrades,
                      bases=args.bases, patch_era=args.patch,
                      production_total=args.production_total,
                      production_per_base=args.production_per_base,
                      gas_per_base=args.gas_per_base, army_supply=args.army_supply,
                      warpgate=not args.no_warpgate)
    print(plan.table())
    if args.order:
        print("\nassembled order:", " ".join(plan.build_order))


if __name__ == "__main__":
    main()
