"""Quick CLI for the breakpoint calculator.

    python -m sc2tc.calc.cli zealot zergling --atk 1 --patch 5.0.16-ptr
    python -m sc2tc.calc.cli marauder roach          # defaults: atk0 armor0, 5.0.16-ptr
"""

import argparse

from .breakpoints import breakpoint


def main(argv=None):
    p = argparse.ArgumentParser(description="SC2 breakpoint (hits-to-kill) calculator.")
    p.add_argument("attacker")
    p.add_argument("defender")
    p.add_argument("--atk", type=int, default=0, help="attacker weapon upgrade level (0-3)")
    p.add_argument("--armor", type=int, default=0, help="defender ground armor upgrade level (0-3)")
    p.add_argument("--shield", type=int, default=0, help="defender shield upgrade level (0-3)")
    p.add_argument("--patch", default="5.0.16-ptr", help="patch era tag")
    args = p.parse_args(argv)

    bp = breakpoint(args.attacker, args.defender, atk=args.atk, armor=args.armor,
                    shield=args.shield, patch=args.patch)
    print(bp.summary())
    print(f"  instance damage: {bp.instance_damage} x{bp.attack_count}"
          f"  (vs-type bonus {'applied' if bp.bonus_applied else 'not applicable'})")
    print(f"  net damage per cycle vs hp: {bp.damage_per_cycle_vs_hp}")
    print(f"  defender pool (hp+shields): {bp.defender_total_hp}")


if __name__ == "__main__":
    main()
