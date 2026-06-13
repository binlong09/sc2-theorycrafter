"""Goal-driven build-order PLANNER + full-table renderer.

The timing calculator (timing.py) *times* a build order you hand it. It does not
*design* one. This module closes that gap: given a strategic GOAL — which units and
upgrades you want, on how many bases — it deterministically assembles a complete,
legal build order (every tech prerequisite, gas, supply, and the expansion included),
simulates it, and renders the full Supply | Time | Action | Cost | Notes table.

Design split (matches CLAUDE.md's core principle):
  - COMPLETENESS / LEGALITY is fact-like and deterministic -> it lives here, derived
    from the catalog's `requires`/`built_by` chains. A build that "makes zealots" can
    never come out without a Gateway again.
  - STRATEGIC INTENT (which army, how aggressive, how many bases) is reasoning -> it is
    the *input* to plan_build, supplied by the caller (the LLM, the CLI, or the owner).

The ordering heuristic is a sensible standard-macro default, NOT a provably-earliest
optimizer (that's a deferred Phase 2). The GM owner verifies and can reorder.
"""

from dataclasses import dataclass, field

from .build_data import get_catalog
from .upgrade_data import REQUIREMENTS
from .timing import simulate, TimingResult
from ..db import _ALIASES, _norm


# Economy items the planner inserts by POLICY (they never appear in a tech closure —
# nothing `requires` an Assimilator or a 2nd Nexus). Per race. (Supply is auto-built by
# the sim, not inserted here.)
_GAS = {"Protoss": "Assimilator", "Terran": "Refinery", "Zerg": "Extractor"}
_BASE = {"Protoss": "Nexus", "Terran": "CommandCenter", "Zerg": "Hatchery"}

# Hard legality cap, not a heuristic: a base has exactly 2 geysers, so you can never take
# more than 2 gas per base. This guardrail keeps the caller (LLM) from ever emitting an
# impossible build (e.g. "3 gas per base"). How much gas WITHIN this cap is strategic
# intent (fast-expand wants minerals -> 1; a tech build or all-in wants 2) and is the
# caller's call via gas_per_base — we don't policy it deterministically.
MAX_GAS_PER_BASE = 2


def _default_production_per_base(race):
    """Default count of the army's production building (Gateway/Barracks/...) PER BASE.
    Race-aware (GM owner's call, 2026-06-12): Protoss/Terran 4 (so 1 base = a 4-gate/4-rax
    all-in, 2 base = a heavy macro count); Zerg 1 (Zerg produces army from LARVA at its
    hatcheries, not from standing production buildings, so this barely applies — extra
    Zerg 'production' is really extra hatcheries, i.e. bases). Override per call if needed.
    """
    return {"Protoss": 4, "Terran": 4, "Zerg": 1}.get(race, 2)


# Worker saturation per base (~2/patch on 8 patches + a few on gas). The planner caps worker
# production here so a long army-production run doesn't balloon worker count past saturation.
_SATURATION_PER_BASE = 22


def _default_army_supply(bases):
    """Default army-supply CEILING — produce the comp until this much army supply, then the
    table stops (you read the army you have at any timestamp off it). Scales with bases,
    capped at the 200 game max. A ceiling, not a target: the point you care about is usually
    the timing row mid-table, not the final count."""
    return min(200, 50 * bases)


# --------------------------------------------------------------------------- #
# name resolution (accept friendly names: "muta", "+1 attack", "charge")
# --------------------------------------------------------------------------- #

def resolve_unit(race, query, catalog=None):
    """Resolve a unit name against the race catalog (kind='unit'/'worker'), honoring
    player nicknames ('muta'->Mutalisk) and spacing/case ('void ray'->VoidRay)."""
    cat = catalog or get_catalog(race)
    if query in cat and cat[query].kind in ("unit", "worker"):
        return query
    target = _ALIASES.get(_norm(query), query)
    nt = _norm(target)
    for name, item in cat.items():
        if item.kind in ("unit", "worker") and _norm(name) == nt:
            return name
    return None


def resolve_upgrade(race, query, catalog=None):
    """Resolve an upgrade to its engine name. Accepts the engine name, the curated
    friendly alias ('charge', 'metabolic boost'), or a loose token query ('+1 attack').

    For a loose query that matches several lines (e.g. '+1 attack' hits both ground and
    air), prefer the GROUND/melee line and the lowest level — the common reading. The
    chosen name is exact and engine-grounded; only the *disambiguation* is heuristic.
    """
    import re
    cat = catalog or get_catalog(race)
    if query in cat and cat[query].kind == "upgrade":
        return query
    cands = {n: REQUIREMENTS[n][3] for n in cat
             if cat[n].kind == "upgrade" and n in REQUIREMENTS}
    qn = _norm(query)
    # exact normalized match on engine name or alias
    for ename, alias in cands.items():
        if _norm(ename) == qn or _norm(alias) == qn:
            return ename
    # loose match. tier 0 = query is a contiguous (normalized) substring of the alias
    # ('ling speed' -> 'metabolic boost (ling speed)', NOT 'adrenal glands (ling attack
    # speed)'); tier 1 = every query TOKEN appears somewhere in the alias ('+1 attack').
    qtok = set(re.findall(r"[a-z0-9]+", query.lower()))
    matches = []
    for ename, alias in cands.items():
        atok = set(re.findall(r"[a-z0-9]+", alias.lower()))
        substr = qn and qn in _norm(alias)
        if substr or (qtok and qtok <= atok):
            matches.append((ename, alias, 0 if substr else 1, len(atok - qtok)))
    if matches:
        def rank(m):
            ename, alias, tier, extra = m
            al = alias.lower()
            air = 1 if ("air" in al or "flyer" in al or "ship" in al) else 0
            lvl = re.search(r"level(\d)", ename.lower())
            return (tier, air, int(lvl.group(1)) if lvl else 0, extra, ename)
        matches.sort(key=rank)
        return matches[0][0]
    return None


# --------------------------------------------------------------------------- #
# tech-prerequisite closure + ordering
# --------------------------------------------------------------------------- #

def _closure(catalog, target_names):
    """Walk `requires` + `built_by` chains from the targets. Returns {name: BuildItem}
    for every catalog item that must exist (tech/production structures, upgrade prereqs,
    the targets themselves). Bases/supply/gas are NOT pulled in here — they're policy."""
    closure = {}
    stack = list(target_names)
    while stack:
        name = stack.pop()
        if name in closure or name not in catalog:
            continue
        item = catalog[name]
        closure[name] = item
        for req in item.requires:
            stack.append(req)
        bb = item.built_by
        if bb in catalog and not catalog[bb].is_base:
            stack.append(bb)
    return closure


def _toposort_structures(catalog, names, prioritize):
    """Order structure names so every dependency precedes its dependents. Tie-break:
    a structure that directly produces a requested unit comes first (so the army's
    production building opens the build), then fewer prereqs, then name."""
    names = set(names)

    def deps(n):
        return [r for r in catalog[n].requires if r in names]

    ordered, placed = [], set()

    def key(n):
        return (0 if n in prioritize else 1, len(catalog[n].requires), n)

    while len(placed) < len(names):
        ready = [n for n in names if n not in placed and all(d in placed for d in deps(n))]
        if not ready:  # cycle guard (shouldn't happen with real tech trees)
            ready = [n for n in names if n not in placed]
        nxt = min(ready, key=key)
        ordered.append(nxt)
        placed.add(nxt)
    return ordered


# --------------------------------------------------------------------------- #
# the planner
# --------------------------------------------------------------------------- #

@dataclass
class BuildPlan:
    race: str
    patch_era: str
    goal: dict
    build_order: list                 # the assembled step list fed to simulate()
    result: TimingResult
    notes: list = field(default_factory=list)   # planner-level notes (resolution, policy)

    @property
    def warnings(self):
        return self.result.warnings

    def table(self):
        return render_table(self.result, self.race, self.patch_era,
                            planner_notes=self.notes)


def plan_build(race, units=None, upgrades=None, bases=1, patch_era="5.0.16-ptr",
               *, army_supply=None, production_per_base=None, production_total=None,
               gas_per_base=1, max_time_s=1320.0):
    """Assemble + simulate a complete build order from a strategic goal.

    Args:
        race: 'Protoss' | 'Terran' | 'Zerg'.
        units: the army COMPOSITION as a ratio. Each entry is a name (friendly ok: 'muta',
            'high templar') or a (name, weight) pair — weights are relative, so
            [('Zealot', 2), ('HighTemplar', 1)] produces ~2 zealots per templar. The build
            streams this comp continuously; you read the actual army at any time off the
            table. A bare name defaults to weight 1.
        upgrades: upgrades to research (friendly ok: '+1 attack', 'charge', or the
            engine name). Each is resolved to its engine name + research building.
        bases: target town-hall count (1 = no expansion; 2 = take a natural; ...).
        army_supply: army-supply CEILING to produce up to. Default None = _default_army_supply
            (50 x bases, capped 200). It bounds the table, not your decision-making — the
            timing you care about is usually a row mid-table.
        production_per_base: army production buildings (Gateway/Barracks/...) per base.
            Default None = race default (_default_production_per_base): P/T 4, Zerg 1. The
            closure already guarantees the first one. This sizes how much the economy can
            SPEND (it, not army_size, drives when the army is on the field).
        production_total: TOTAL count of the PRIMARY production building (the one making the
            heaviest unit) — this is how players phrase "7-gate" / "4-gate" / "3-gate expand"
            (a total, not per-base). Overrides production_per_base for that one building;
            any secondary production line keeps the per-base default. None = use per-base.
        gas_per_base: geysers per base when the goal needs gas. STRATEGIC — the caller sets
            it from the build type (fast-expand 1, tech/all-in 2). Default 1; HARD-CAPPED at
            MAX_GAS_PER_BASE (2 = the physical geyser count per base).

    Returns a BuildPlan (carries the build_order, the TimingResult, and a .table()).
    """
    if race not in ("Protoss", "Terran", "Zerg"):
        raise ValueError(f"race must be Protoss/Terran/Zerg, got {race!r}")
    catalog = get_catalog(race)
    notes = []

    # 1) resolve goal --------------------------------------------------------
    ratio = []   # list[(canonical_name, weight)] — the army COMPOSITION
    for entry in (units or []):
        name, weight = (entry if isinstance(entry, (tuple, list)) else (entry, 1))
        canon = resolve_unit(race, name, catalog)
        if canon is None:
            notes.append(f"!! unknown unit {name!r} — skipped (check the name with list_units)")
            continue
        ratio.append((canon, max(1, int(weight))))

    upgrade_names = []
    for u in (upgrades or []):
        canon = resolve_upgrade(race, u, catalog)
        if canon is None:
            notes.append(f"!! unknown upgrade {u!r} — skipped (check list_upgrades)")
            continue
        upgrade_names.append(canon)
        if _norm(u) != _norm(canon):
            notes.append(f"resolved {u!r} -> {canon} ({REQUIREMENTS.get(canon, ('','','',''))[3]})")

    if not ratio and not upgrade_names:
        raise ValueError("nothing to build — pass at least one unit or upgrade")

    # 2) tech closure --------------------------------------------------------
    targets = [n for n, _ in ratio] + upgrade_names
    closure = _closure(catalog, targets)
    tech_structs = [n for n, it in closure.items()
                    if it.kind == "structure" and not it.is_base and not it.provides_gas]
    prod_buildings = {catalog[n].built_by for n, _ in ratio
                      if catalog[n].built_by in catalog}
    ordered_tech = _toposort_structures(catalog, tech_structs, prioritize=prod_buildings)

    gas_needed = any(closure[n].gas_cost for n in closure) or any(
        catalog[n].gas_cost for n, _ in ratio)
    gpb = max(0, min(MAX_GAS_PER_BASE, gas_per_base))   # cap at the 2-geyser physical limit
    ppb = production_per_base if production_per_base is not None else _default_production_per_base(race)

    # 3) assemble the ECONOMY + TECH build order (army is produced continuously by the sim,
    #    not queued; supply is auto-built by the sim — see step 4). Standard-macro phasing.
    gas, base = _GAS[race], _BASE[race]
    bo = []
    # the army's root production building (e.g. Gateway) opens the tech
    root = ordered_tech[0] if ordered_tech else None
    if root:
        bo.append(root)
    if gas_needed:
        bo += [gas] * max(1, gpb)                        # first base's gas
    bo += [base] * max(0, bases - 1)                    # expansion(s)
    bo += ordered_tech[1:]                              # remaining tech in dependency order
    if gas_needed and bases > 1:
        bo += [gas] * (gpb * (bases - 1))               # gas on the expansion(s)
    # per-race ECON macro so chrono/MULE/inject have something to run on (matches the
    # macro=True sim): Terran morphs an Orbital for MULEs; Zerg adds a Queen per base for
    # injects. (Protoss chronos off the Nexus, which always exists.)
    if race == "Terran" and "Barracks" in bo and "OrbitalCommand" not in bo:
        bo.insert(bo.index("Barracks") + 1, "OrbitalCommand")
    if race == "Zerg" and "SpawningPool" in bo:
        at = bo.index("SpawningPool") + 1
        bo[at:at] = ["Queen"] * max(1, bases)
    # extra production buildings (closure already placed one of each). production_total, if
    # given, sets the PRIMARY production line's total (the "N-gate" count); others stay per-base.
    primary_prod = None
    if ratio:
        top_unit = max(ratio, key=lambda nw: nw[1])[0]
        if catalog[top_unit].built_by in prod_buildings:
            primary_prod = catalog[top_unit].built_by
    for pb in sorted(prod_buildings):
        if production_total is not None and pb == primary_prod:
            total = max(1, production_total)
        else:
            total = max(1, ppb * bases)
        bo += [pb] * max(0, total - 1)              # closure already placed one
    # upgrades (their research buildings are now in the order)
    bo += upgrade_names

    # 4) simulate. The sim AUTO-BUILDS supply (no supply blocks) and pumps the army comp
    #    continuously from every idle production building up to the army-supply ceiling —
    #    so the army streams as buildings finish, not back-loaded after a queued army block.
    army_cap = army_supply if army_supply is not None else _default_army_supply(bases)
    wcap = bases * _SATURATION_PER_BASE   # stop workers at ~saturation, then it's all army
    result = simulate(bo, race, patch_era, make_workers=True, worker_priority=True,
                      worker_cap=wcap, auto_supply=True, auto_army=ratio,
                      army_supply_cap=army_cap, macro=True, max_time_s=max_time_s)

    goal = {"composition": ratio, "army_supply": army_cap, "upgrades": upgrade_names, "bases": bases}
    return BuildPlan(race=race, patch_era=patch_era, goal=goal,
                     build_order=bo, result=result, notes=notes)


# --------------------------------------------------------------------------- #
# full-table renderer
# --------------------------------------------------------------------------- #

def _fmt_t(s):
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def _chrono_index(notes):
    """Parse chrono events from sim notes into a list of (time_seconds, target_name)."""
    import re
    out = []
    for n in notes:
        m = re.match(r"(\d+):(\d{2}) Chrono (?:->|applied to) (\S+)", n)
        if m:
            out.append((int(m.group(1)) * 60 + int(m.group(2)), m.group(3)))
    return out


def render_table(result, race, patch_era, planner_notes=None):
    """Render a TimingResult as the Supply | Time | Action | Cost | Notes table, with
    worker production and chrono-boost flags shown. Consecutive identical steps group
    into 'Name xN'."""
    catalog = get_catalog(race)
    chronos = _chrono_index(result.notes)

    def cost_str(item, n):
        parts = []
        if item.mineral_cost:
            parts.append(f"{item.mineral_cost * n}m")
        if item.gas_cost:
            parts.append(f"{item.gas_cost * n}g")
        return "/".join(parts) if parts else "—"

    steps = sorted(result.steps, key=lambda s: (s.start_s, s.name))

    # group consecutive identical names
    rows = []
    i = 0
    while i < len(steps):
        j = i
        while j + 1 < len(steps) and steps[j + 1].name == steps[i].name \
                and steps[j + 1].start_s - steps[j].start_s < 1.5:
            j += 1
        grp = steps[i:j + 1]
        s = grp[0]
        item = catalog.get(s.name)
        n = len(grp)
        action = s.name if n == 1 else f"{s.name} x{n}"
        cost = cost_str(item, n) if item else "—"
        pre_supply = s.supply_at_start - (item.supply_cost * n if item else 0)
        # chrono note matching this group (by name, near its start)
        note = ""
        for k, (ct, cname) in enumerate(chronos):
            if cname == s.name and grp[0].start_s - 2 <= ct <= grp[-1].complete_s + 2:
                note = "Chrono Boost"
                chronos.pop(k)
                break
        rows.append((int(round(pre_supply)), _fmt_t(s.start_s), action, cost, note))
        i = j + 1

    # layout
    w_sup = max(6, max((len(str(r[0])) for r in rows), default=6))
    w_time = max(4, max((len(r[1]) for r in rows), default=4))
    w_act = max(6, max((len(r[2]) for r in rows), default=6))
    w_cost = max(4, max((len(r[3]) for r in rows), default=4))
    head = f"{'Supply':<{w_sup}}  {'Time':<{w_time}}  {'Action':<{w_act}}  {'Cost':<{w_cost}}  Notes"
    lines = [head, "-" * len(head)]
    for sup, tm, act, cost, note in rows:
        lines.append(f"{sup:<{w_sup}}  {tm:<{w_time}}  {act:<{w_act}}  {cost:<{w_cost}}  {note}".rstrip())

    out = [f"{race} @ {patch_era} — start {result.starting_workers} workers", "", *lines]
    for n in (planner_notes or []):
        out.append(f"  · {n}")
    for w in result.warnings:
        out.append(f"  ! {w}")
    return "\n".join(out)
