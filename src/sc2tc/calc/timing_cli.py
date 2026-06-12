"""Quick CLI for the build-order timing calculator.

    python -m sc2tc.calc.timing_cli Protoss Pylon Gateway CyberneticsCore
    python -m sc2tc.calc.timing_cli Protoss Pylon Gateway --patch 5.0.15 --no-workers
    python -m sc2tc.calc.timing_cli Terran SupplyDepot Barracks Refinery Factory

Boosters are steps too: MULE, Inject, or Chrono:CyberneticsCore.
"""

import argparse

from .timing import simulate


def main(argv=None):
    p = argparse.ArgumentParser(description="SC2 build-order timing calculator.")
    p.add_argument("race", choices=["Protoss", "Terran", "Zerg"])
    p.add_argument("steps", nargs="+", help="build order: item names + boosters")
    p.add_argument("--patch", default="5.0.16-ptr", help="patch era tag")
    p.add_argument("--no-workers", action="store_true",
                   help="don't auto-produce workers (model a worker cut)")
    p.add_argument("--curve", action="store_true", help="also print the resource curve")
    args = p.parse_args(argv)

    r = simulate(args.steps, args.race, args.patch, make_workers=not args.no_workers)
    print(r.summary())
    for n in r.notes:
        print(f"  . {n}")
    if args.curve:
        print("  time   min    gas   wkrs  supply")
        for s in r.curve:
            print(f"  {int(s.t)//60}:{int(s.t) % 60:02d}  {s.minerals:6.0f} {s.gas:5.0f}  "
                  f"{s.workers:4d}  {s.supply_used:g}/{s.supply_cap:g}")


if __name__ == "__main__":
    main()
