"""Build-order timing calculator.

Tick-based economic simulation. Given a build order, a race, and a patch era, it
reports when each step *starts* (becomes affordable + a builder is free + tech is
met) and *completes*, plus the mineral/gas/supply curve over time.

It reads the era's `starting_workers` and base supply from patch_config.EconConfig,
so the same build order can be run for 5.0.15 (12 workers, Nexus=15) vs 5.0.16
(8 workers, Nexus=13) and the two timelines compared directly. starting_workers is
NEVER hard-coded — it comes from the EconConfig (CLAUDE.md hard rule).

MODELING NOTES (transparent on purpose; calibrate against PTR replays):
  - Mineral income is the standard 2-workers-per-patch saturation model; rates in
    IncomeRates are community-standard defaults the GM owner can tune in one place.
  - Worker-on-build occupancy is race-accurate in shape: Terran SCV is busy the whole
    build, Protoss probe returns almost immediately, Zerg drone is consumed.
  - Boosters (MULE / Chrono / Inject) are implemented as simplified, parameterized
    effects — enough to compare openers, not frame-perfect. Energy economy is not
    modeled yet; a used booster emits a note. This is the documented next refinement.
  - Patch-mineral depletion is ignored (irrelevant for sub-10-minute openers).
"""

from dataclasses import dataclass, field
from collections import Counter

from .build_data import get_item
from .patch_config import get_econ


@dataclass
class IncomeRates:
    # Per-second mining rates, modeled per-patch-tier (the Nth worker on a patch mines
    # less than the (N-1)th due to queueing at the patch).
    # These mineral rates are the OPTIMAL CEILING: owner measured them with workers settled
    # and perfectly distributed (exactly 2/patch at 16, etc.). Real un-microed play is lower
    # — imperfect distribution turns a 2nd-slot (0.96) into a 3rd-close-slot (0.13), plus
    # early bumping/stealing before workers settle. Model `mining_efficiency` (default 1.0 =
    # ceiling) scales mineral income to represent execution quality; calibrate it from an
    # un-microed game if wanted. Gas is exempt — fixed slots, short trip, nothing to misplay.
    #
    # CALIBRATED to owner's live PTR tests (2026-06-05), single base. Worker slots are
    # filled in descending marginal value (optimal assignment — what a real player does):
    #   8w  (1/patch)               => 8.00/s   -> 1st-per-patch        = 1.00
    #   16w (2/patch)               => 15.67/s  -> 2nd-per-patch        = 0.96
    #   20w (3rd on 4 FAR patches)  => 18.08/s  -> 3rd-on-FAR-patch     = (18.08-15.67)/4 = 0.60
    #   24w (3rd on all 8 patches)  => 18.58/s  -> 3rd-on-CLOSE-patch   = (18.58-18.08)/4 = 0.13
    # CRITICAL: the 3rd worker is NOT a single rate. On a far patch it adds ~0.60; on a
    # close patch only ~0.13 (close patches saturate at 2 because the trip is short). A flat
    # "3rd = 0.36" average misleads on partial oversaturation, so we split it and fill far
    # 3rd-slots first. far_patches_per_base (4/8) is map-dependent — a reasonable default.
    first_worker_per_patch: float = 1.00        # ~60/min, 1st worker on a patch
    second_worker_per_patch: float = 0.96       # ~58/min, 2nd worker on a patch
    third_worker_far_patch: float = 0.60        # ~36/min, 3rd worker on a far patch
    third_worker_close_patch: float = 0.13      # ~8/min,  3rd worker on a close patch
    startup_delay_s: float = 5.0                # initial workers walk out at game start
    mining_efficiency: float = 1.0              # 1.0 = optimal ceiling; <1 models un-microed loss (minerals only)
    # Gas, per-worker on one geyser. CALIBRATED to owner's PTR test (2026-06-05), measured
    # across 2 geysers and halved: 2 workers/geyser=>1.97/s, 3/geyser=>2.67/s per geyser.
    # Gas barely saturates — the 3rd worker still pulls 68% of the first (vs minerals' 13%
    # for the 3rd close-patch worker). Filled highest-value-first, like minerals.
    first_gas_worker: float = 1.03              # ~62/min, 1st worker on a geyser
    second_gas_worker: float = 0.93             # ~56/min, 2nd worker on a geyser
    third_gas_worker: float = 0.70              # ~42/min, 3rd worker on a geyser
    patches_per_base: int = 8
    far_patches_per_base: int = 4               # of the 8, how many are "far" (map-dependent)
    gas_workers_per_geyser: int = 3
    # --- Race macro mechanics (energy-gated; auto-cast when simulate(macro=True)) ---
    # Casters accumulate energy and spend it: Protoss Nexus -> Chrono Boost, Terran Orbital
    # Command -> MULE, Zerg Queen -> Inject Larva. Constants are best-known SC2 values, all
    # tunable + GM-calibratable (like the income rates). Energy regen/start are global.
    energy_regen: float = 0.7875   # energy/sec per caster (SC2 standard)
    caster_start_energy: float = 50.0   # energy a Nexus/Orbital/Queen has when it appears
    caster_max_energy: float = 200.0
    chrono_cost: float = 50.0
    chrono_duration_s: float = 20.0  # one Chrono Boost = +50% work speed for this long
    chrono_saved_s: float = 10.0   # flat shave for the MANUAL Chrono:Target booster (approx)
    mule_cost: float = 50.0
    mule_rate: float = 3.5         # minerals/sec while a MULE is active (~225 over its 64s life)
    mule_duration: float = 64.0
    inject_cost: float = 25.0
    inject_larva: int = 3          # larva added per inject
    inject_delay_s: float = 29.0   # larva appear this long after the inject is cast
    # worker leaves the mineral line to start a Protoss structure for this long, then returns
    protoss_build_occupancy_s: float = 0.0


@dataclass
class StepResult:
    name: str
    start_s: float
    complete_s: float
    supply_at_start: float


@dataclass
class Sample:
    t: float
    minerals: float
    gas: float
    workers: int
    supply_used: float
    supply_cap: float


@dataclass
class TimingResult:
    race: str
    patch_era: str
    starting_workers: int
    steps: list = field(default_factory=list)       # list[StepResult]
    curve: list = field(default_factory=list)        # list[Sample]
    warnings: list = field(default_factory=list)
    notes: list = field(default_factory=list)        # booster events etc.
    finished_at: float = 0.0

    def start_of(self, name):
        for s in self.steps:
            if s.name == name:
                return s.start_s
        return None

    def complete_of(self, name):
        for s in self.steps:
            if s.name == name:
                return s.complete_s
        return None

    def summary(self):
        lines = [f"{self.race} @ {self.patch_era} - start {self.starting_workers} workers"]
        for s in self.steps:
            lines.append(f"  {self._fmt(s.start_s)} start  {s.name:<16} "
                         f"(done {self._fmt(s.complete_s)}, {s.supply_at_start:g} supply)")
        for w in self.warnings:
            lines.append(f"  ! {w}")
        return "\n".join(lines)

    @staticmethod
    def _fmt(s):
        return f"{int(s)//60}:{int(s) % 60:02d}"


# A base / production structure instance, tracked by when it next becomes free.
class _Producer:
    __slots__ = ("name", "free_at")
    def __init__(self, name, free_at=0.0):
        self.name = name
        self.free_at = free_at


# Build-order tokens that are instant actions, not catalog items to be produced.
_ACTIONS = {"MULE", "Inject", "Chrono", "Gas"}


def simulate(build_order, race, patch_era="5.0.16-ptr", *,
             rates=None, make_workers=True, macro=False, max_time_s=600.0, dt=1.0,
             sample_interval_s=5.0, starting_minerals=50, starting_gas=0):
    """Run a build order and return a TimingResult.

    Args:
        build_order: list of step names. A step is a catalog item ("Gateway",
            "Probe", "Pylon", ...) or a booster: "MULE", "Inject", or "Chrono:Name"
            (e.g. "Chrono:CyberneticsCore").
        race: 'Protoss' | 'Terran' | 'Zerg'.
        patch_era: era tag understood by patch_config (e.g. '5.0.16-ptr', '5.0.15').
        make_workers: if True (default), idle bases keep producing workers as long as
            doing so does not delay the next queued item. Set False to model worker cuts.
        macro: if True, auto-cast race macro mechanics from available energy — Protoss
            chronos in-progress production, Terran MULEs from each Orbital Command, Zerg
            injects from each Queen. Realistic econ; default False keeps a clean baseline.
        rates: IncomeRates override.
    """
    rates = rates or IncomeRates()
    econ = get_econ(patch_era)

    # base + supply names per race
    base_name = {"Protoss": "Nexus", "Terran": "CommandCenter", "Zerg": "Hatchery"}[race]
    worker_name = {"Protoss": "Probe", "Terran": "SCV", "Zerg": "Drone"}[race]
    base_supply = {"Protoss": econ.nexus_supply, "Terran": econ.command_center_supply,
                   "Zerg": econ.hatchery_supply}[race]

    # --- initial state -------------------------------------------------------
    t = 0.0
    minerals = float(starting_minerals)
    gas = float(starting_gas)
    mineral_workers = econ.starting_workers
    gas_workers = 0
    supply_used = float(econ.starting_workers)
    supply_cap = float(base_supply)
    structures = Counter({base_name: 1})
    producers = {base_name: [_Producer(base_name, 0.0)]}
    num_geysers = 0
    larva = 3.0 if race == "Zerg" else 0.0
    larva_regen_t = 0.0
    if race == "Zerg":
        supply_cap += 8  # starting Overlord

    occupied = []     # list of return-times for workers temporarily off minerals (P/T builds)
    pending = []      # in-progress: list of dicts {at, item}
    mules = []        # list of mule expiry times
    chrono_pending = Counter()  # item_name -> count of queued chrono speedups

    # macro energy: Protoss Nexus pool, Terran Orbital pool, per-Queen energy list.
    nexus_energy = rates.caster_start_energy if race == "Protoss" else 0.0
    orbital_energy = 0.0          # Terran: filled when an OrbitalCommand completes
    queen_energy = []             # Zerg: one entry per completed Queen
    larva_pending = []            # Zerg: list of (mature_at, amount) from injects

    queue = list(build_order)
    steps = []
    curve = []
    warnings = []
    notes = []
    sample_at = 0.0

    def mineral_income_per_s():
        # MULEs ignore the startup ramp (they only ever drop mid-game).
        mule = rates.mule_rate * len(mules)
        if t < rates.startup_delay_s:
            return mule  # initial workers still walking out to the patches
        bases = structures_base_count()
        far = rates.far_patches_per_base
        close = rates.patches_per_base - far
        # Marginal worker slots, highest-value first (optimal assignment), scaled by bases:
        # every patch's 1st slot, then every 2nd slot, then far 3rd-slots, then close 3rd-slots.
        slots = [
            (rates.patches_per_base * bases, rates.first_worker_per_patch),
            (rates.patches_per_base * bases, rates.second_worker_per_patch),
            (far * bases, rates.third_worker_far_patch),
            (close * bases, rates.third_worker_close_patch),
        ]
        remaining, income = mineral_workers, 0.0
        for count, rate in slots:
            take = min(remaining, count)
            income += take * rate
            remaining -= take
            if remaining <= 0:
                break
        # efficiency scales worker mining only; MULE income is reliable (auto-mined)
        return income * rates.mining_efficiency + mule

    def gas_income_per_s():
        # Same slot-filling shape as minerals: fill the 1st slot of each geyser, then
        # 2nd, then 3rd. Lets the 3rd gas worker carry a distinct (measured) rate.
        slots = [
            (num_geysers, rates.first_gas_worker),
            (num_geysers, rates.second_gas_worker),
            (num_geysers, rates.third_gas_worker),
        ]
        remaining, income = gas_workers, 0.0
        for count, rate in slots:
            take = min(remaining, count)
            income += take * rate
            remaining -= take
            if remaining <= 0:
                break
        return income

    def structures_base_count():
        return structures[base_name]

    def free_producer(name):
        for p in producers.get(name, []):
            if p.free_at <= t + 1e-9:
                return p
        return None

    def blocked_reasons(item, ignore_minerals=False):
        """All reasons `item` can't start now. Empty == startable.

        ignore_minerals drops the mineral/gas check — used by the worker-saving
        heuristic to tell "only short on minerals" apart from "also tech/supply/builder
        blocked" (which `can_start`'s first-reason can't distinguish)."""
        reasons = []
        if not ignore_minerals:
            if minerals + 1e-9 < item.mineral_cost or gas + 1e-9 < item.gas_cost:
                reasons.append("resources")
        if item.supply_cost and supply_used + item.supply_cost > supply_cap + 1e-9:
            reasons.append("supply")
        if any(structures[req] < 1 for req in item.requires):
            reasons.append("tech")
        if item.built_by == "base" and free_producer(base_name) is None:
            reasons.append("base-busy")
        elif item.built_by == "larva" and larva < 1:
            reasons.append("larva")
        elif item.built_by == "worker" and mineral_workers < 1:
            reasons.append("no-worker")
        elif item.built_by not in ("base", "larva", "worker") and free_producer(item.built_by) is None:
            reasons.append("producer-busy")
        return reasons

    def can_start(item):
        reasons = blocked_reasons(item)
        return (not reasons), (reasons[0] if reasons else "")

    def start(item):
        nonlocal minerals, gas, supply_used, mineral_workers, larva
        minerals -= item.mineral_cost
        gas -= item.gas_cost
        supply_used += item.supply_cost
        build_time = item.build_time_s
        if chrono_pending[item.name] > 0:
            chrono_pending[item.name] -= 1
            build_time = max(1.0, build_time - rates.chrono_saved_s)
            notes.append(f"{TimingResult._fmt(t)} Chrono applied to {item.name} "
                         f"(-{rates.chrono_saved_s:g}s)")
        # occupy builder. prod = the producing structure (chrono-able), if any.
        prod = None
        if item.built_by == "base":
            prod = free_producer(base_name)
            prod.free_at = t + build_time
        elif item.built_by == "larva":
            larva -= 1
        elif item.built_by == "worker":
            if race == "Terran":
                occupied.append(t + build_time)        # SCV busy whole build
                mineral_workers -= 1
            elif race == "Protoss":
                if rates.protoss_build_occupancy_s > 0:
                    occupied.append(t + rates.protoss_build_occupancy_s)
                    mineral_workers -= 1
            elif race == "Zerg":
                mineral_workers -= 1                     # drone consumed...
                supply_used -= 1                         # ...freeing its supply
        else:
            prod = free_producer(item.built_by)
            prod.free_at = t + build_time
        step = StepResult(item.name, t, t + build_time, supply_used)
        steps.append(step)
        pending.append({"at": t + build_time, "item": item, "producer": prod, "step": step})

    def complete(item, at):
        nonlocal supply_cap, mineral_workers, gas_workers, num_geysers, orbital_energy
        if item.kind == "worker":
            mineral_workers += 1
        elif item.kind == "supply":
            supply_cap += item.supply_provided
        elif item.kind == "upgrade":
            structures[item.name] += 1  # mark researched so later upgrades can require it
        if item.kind in ("structure", "supply") or item.is_base:
            structures[item.name] += 1  # count ALL buildings (incl supply) so they satisfy prereqs
            if item.kind != "supply" or item.is_base:
                producers.setdefault(item.name, []).append(_Producer(item.name, at))
            if item.is_base:
                supply_cap += base_supply
            if item.provides_gas:
                num_geysers += 1
                moved = min(rates.gas_workers_per_geyser, mineral_workers)
                mineral_workers -= moved
                gas_workers += moved
        # macro casters power up when they appear
        if item.name == "OrbitalCommand":
            orbital_energy += rates.caster_start_energy
        elif item.name == "Queen":
            queen_energy.append(rates.caster_start_energy)

    def set_gas_workers(target):
        """Move workers between the mineral line and gas to reach `target` in gas.
        Capped by geyser capacity (3/geyser). Reassignment is modeled as instant
        (real micro costs a few seconds of travel — a documented simplification)."""
        nonlocal gas_workers, mineral_workers
        target = max(0, min(target, num_geysers * rates.gas_workers_per_geyser))
        delta = target - gas_workers
        if delta > 0:                       # pull from minerals into gas
            move = min(delta, mineral_workers)
            mineral_workers -= move
            gas_workers += move
        elif delta < 0:                     # pull out of gas back to minerals
            gas_workers += delta            # delta is negative
            mineral_workers -= delta
        notes.append(f"{TimingResult._fmt(t)} gas workers -> {gas_workers} "
                     f"(minerals line: {mineral_workers})")

    def apply_booster(token):
        """Apply an instant build-order action. Returns True if consumed, False if it
        should WAIT in the queue (e.g. Gas:N before a geyser exists)."""
        nonlocal larva
        head = token.split(":")[0]
        if head == "Gas":
            _, _, n = token.partition(":")
            if not n.isdigit():
                warnings.append(f"{TimingResult._fmt(t)} Gas action needs a count, e.g. Gas:2 — ignored")
                return True
            if int(n) > 0 and num_geysers == 0:
                return False  # wait for a gas structure to finish, then apply
            set_gas_workers(int(n))
            return True
        if token == "MULE":
            if race != "Terran":
                warnings.append(f"{TimingResult._fmt(t)} MULE used by non-Terran — ignored")
                return True
            mules.append(t + rates.mule_duration)
            notes.append(f"{TimingResult._fmt(t)} MULE dropped (+{rates.mule_rate:g}/s for "
                         f"{rates.mule_duration:g}s; energy not modeled)")
        elif token == "Inject":
            if race != "Zerg":
                warnings.append(f"{TimingResult._fmt(t)} Inject used by non-Zerg — ignored")
                return True
            larva += rates.inject_larva
            notes.append(f"{TimingResult._fmt(t)} Inject (+{rates.inject_larva} larva; "
                         "queen energy not modeled)")
        else:  # Chrono:Target
            _, _, target = token.partition(":")
            if race != "Protoss":
                warnings.append(f"{TimingResult._fmt(t)} Chrono used by non-Protoss — ignored")
                return True
            if not target:
                warnings.append(f"{TimingResult._fmt(t)} Chrono with no target — ignored")
                return True
            chrono_pending[target] += 1
            notes.append(f"{TimingResult._fmt(t)} Chrono queued for next {target} "
                         "(nexus energy not modeled)")
        return True

    def do_macro():
        """Regen caster energy and auto-cast the race macro mechanic (called per tick)."""
        nonlocal nexus_energy, orbital_energy
        cap = rates.caster_max_energy
        if race == "Protoss":
            nexus_energy = min(cap, nexus_energy + structures["Nexus"] * rates.energy_regen * dt)
            if nexus_energy >= rates.chrono_cost:
                # chrono the longest-remaining in-progress production (made by a structure)
                target = None
                for ev in pending:
                    if ev["item"].built_by != "worker" and ev["at"] - t > 1.0:
                        if target is None or ev["at"] > target["at"]:
                            target = ev
                if target is not None:
                    # +50% for chrono_duration_s. If the item finishes within the boost
                    # (remaining <= 1.5*D) it saves remaining/3; else it saves 0.5*D.
                    rem = target["at"] - t
                    d = rates.chrono_duration_s
                    save = rem / 3.0 if rem <= 1.5 * d else 0.5 * d
                    save = min(save, rem - 0.5)
                    target["at"] -= save
                    target["step"].complete_s = target["at"]   # keep the reported time honest
                    if target.get("producer"):
                        target["producer"].free_at = max(t, target["producer"].free_at - save)
                    nexus_energy -= rates.chrono_cost
                    notes.append(f"{TimingResult._fmt(t)} Chrono -> {target['item'].name}")
        elif race == "Terran":
            orbital_energy = min(cap, orbital_energy + structures["OrbitalCommand"] * rates.energy_regen * dt)
            if structures["OrbitalCommand"] >= 1 and orbital_energy >= rates.mule_cost:
                mules.append(t + rates.mule_duration)
                orbital_energy -= rates.mule_cost
                notes.append(f"{TimingResult._fmt(t)} MULE")
        elif race == "Zerg":
            for i in range(len(queen_energy)):
                queen_energy[i] = min(cap, queen_energy[i] + rates.energy_regen * dt)
                if queen_energy[i] >= rates.inject_cost:
                    queen_energy[i] -= rates.inject_cost
                    larva_pending.append((t + rates.inject_delay_s, rates.inject_larva))
                    notes.append(f"{TimingResult._fmt(t)} Inject (+{rates.inject_larva} larva)")

    # --- main loop -----------------------------------------------------------
    stall_guard = 0
    while t <= max_time_s:
        # 1) completions
        still = []
        for ev in pending:
            if ev["at"] <= t + 1e-9:
                complete(ev["item"], ev["at"])
            else:
                still.append(ev)
        pending = still
        # workers returning from builds (Terran/Protoss occupancy)
        if occupied:
            ret = [x for x in occupied if x > t + 1e-9]
            mineral_workers += len(occupied) - len(ret)
            occupied[:] = ret
        # larva regen (Zerg): +1 / 11s up to 3 per hatch (natural), plus injected larva
        if race == "Zerg":
            cap = 3 * structures_base_count()
            if larva < cap and t - larva_regen_t >= 11.0:
                larva = min(cap, larva + 1)
                larva_regen_t = t
            if larva_pending:  # injected larva that have now matured (bypass the 3-cap)
                matured = [a for at, a in larva_pending if at <= t + 1e-9]
                larva += sum(matured)
                larva_pending[:] = [(at, a) for at, a in larva_pending if at > t + 1e-9]
        # expire mules
        if mules:
            mules[:] = [m for m in mules if m > t + 1e-9]
        # macro auto-cast (energy regen + chrono/MULE/inject)
        if macro:
            do_macro()

        # 2) process queue front(s) — start everything startable this tick, in order
        progressed = False
        while queue:
            token = queue[0]
            if token.split(":")[0] in _ACTIONS:
                if not apply_booster(token):
                    break  # action must wait (e.g. Gas:N before a geyser exists)
                queue.pop(0)
                progressed = True
                continue
            item = get_item(race, token)
            reasons = blocked_reasons(item)
            if not reasons:
                start(item)
                queue.pop(0)
                progressed = True
                # auto-worker after committing the step (below) — recheck loop
            else:
                # supply-blocked = could afford but capped on supply (not also mineral-short)
                if "supply" in reasons and "resources" not in reasons:
                    msg = (f"{TimingResult._fmt(t)} supply-blocked before {item.name} "
                           f"({int(supply_used)}/{int(supply_cap)})")
                    if msg not in warnings:
                        warnings.append(msg)
                break  # front not startable; wait (we hold resources for it)

        # 3) optional continuous worker production (doesn't delay the queued front item)
        if make_workers:
            wi = get_item(race, worker_name)
            while not blocked_reasons(wi):
                # Save (skip the worker) ONLY if the next queued item is ready except for
                # minerals — i.e. building the worker would actually delay it. If the next
                # item is also tech/supply/builder-gated, the worker doesn't delay it.
                if queue and queue[0].split(":")[0] not in _ACTIONS:
                    nitem = get_item(race, queue[0])
                    purely_mineral_gated = not blocked_reasons(nitem, ignore_minerals=True)
                    short_after_worker = (minerals - wi.mineral_cost + 1e-9) < nitem.mineral_cost
                    if purely_mineral_gated and short_after_worker:
                        break
                start(wi)
                progressed = True

        # 4) sample the curve
        if t >= sample_at - 1e-9:
            curve.append(Sample(t=t, minerals=round(minerals, 1), gas=round(gas, 1),
                                workers=mineral_workers + gas_workers,
                                supply_used=supply_used, supply_cap=supply_cap))
            sample_at += sample_interval_s

        # 5) accrue income over dt
        minerals += mineral_income_per_s() * dt
        gas += gas_income_per_s() * dt

        # termination: queue drained and nothing in progress
        if not queue and not pending:
            break
        stall_guard = 0 if progressed else stall_guard + 1
        if stall_guard > int(max_time_s / dt) + 2:
            if queue:
                warnings.append(f"stalled — could not start: {queue[0]} (check tech/resources/supply)")
            break
        t += dt

    # Anything still queued when the loop ends never started — surface it (e.g. an
    # upgrade with no gas structure, or a missing tech building), don't fail silently.
    if queue:
        item = None if queue[0].split(":")[0] in _ACTIONS else get_item(race, queue[0])
        why = "needs a gas structure / tech building or more resources" if (
            item and item.gas_cost and num_geysers == 0) else "check resources/tech/builder"
        warnings.append(f"did not complete: {queue} — {why}")

    return TimingResult(race=race, patch_era=patch_era,
                        starting_workers=econ.starting_workers,
                        steps=steps, curve=curve, warnings=warnings,
                        notes=notes, finished_at=t)
