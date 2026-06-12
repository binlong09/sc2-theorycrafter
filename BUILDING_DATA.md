# Building Data — for GM review

All structures the timing model knows, exported from `src/sc2tc/calc/build_data.py`.
Edit there to change them. **Review focus: the `Built by` column** — that is where
add-on-style mismodeling hides. `built_by` should be: `worker` (an SCV/Probe/Drone
builds it), `base`/a base name (town hall), or a **parent structure** when it is a
morph/add-on that ties up that building instead of a worker.

Legend: ⚠️ = likely mismodeled · † build time not yet PTR-verified · Ⓐ = base · Ⓖ = provides gas

## Protoss

| Building | Min | Gas | Build s | Built by | Requires | Flags |
|---|---|---|---|---|---|---|
| WarpGate | 50 | 50 | 7† | Gateway | WarpGateResearch |  |
| Assimilator | 75 | 0 | 21† | worker | — | Ⓖ |
| CyberneticsCore | 150 | 0 | 36† | worker | Gateway |  |
| DarkShrine | 150 | 150 | 71† | worker | TwilightCouncil |  |
| FleetBeacon | 300 | 200 | 43† | worker | Stargate |  |
| Forge | 150 | 0 | 32† | worker | — |  |
| Gateway | 150 | 0 | 46† | worker | — |  |
| Nexus | 400 | 0 | 71† | worker | — | Ⓐ |
| Pylon | 100 | 0 | 18† | worker | — | supply |
| RoboticsBay | 150 | 150 | 46† | worker | RoboticsFacility |  |
| RoboticsFacility | 150 | 100 | 46† | worker | CyberneticsCore |  |
| Stargate | 150 | 150 | 43† | worker | CyberneticsCore |  |
| TemplarArchive | 150 | 200 | 36† | worker | TwilightCouncil |  |
| TwilightCouncil | 150 | 100 | 36† | worker | CyberneticsCore |  |

## Terran

| Building | Min | Gas | Build s | Built by | Requires | Flags |
|---|---|---|---|---|---|---|
| OrbitalCommand | 150 | 0 | 25† | CommandCenter | Barracks |  |
| Armory | 150 | 50 | 46† | worker | Factory |  |
| Barracks | 150 | 0 | 46† | worker | SupplyDepot |  |
| ⚠️ BarracksTechLab | 50 | 25 | 18† | worker | Barracks | ⚠️ add-on |
| CommandCenter | 400 | 0 | 71† | worker | — | Ⓐ |
| EngineeringBay | 125 | 0 | 25† | worker | — |  |
| Factory | 150 | 100 | 36† | worker | Barracks |  |
| ⚠️ FactoryTechLab | 50 | 25 | 18† | worker | Factory | ⚠️ add-on |
| FusionCore | 150 | 150 | 46† | worker | Starport |  |
| GhostAcademy | 150 | 50 | 29† | worker | Barracks |  |
| Refinery | 75 | 0 | 21† | worker | — | Ⓖ |
| Starport | 150 | 100 | 36† | worker | Factory |  |
| ⚠️ StarportTechLab | 50 | 25 | 18† | worker | Starport | ⚠️ add-on |
| SupplyDepot | 100 | 0 | 21† | worker | — | supply |

## Zerg

| Building | Min | Gas | Build s | Built by | Requires | Flags |
|---|---|---|---|---|---|---|
| Lair | 150 | 100 | 57† | Hatchery | SpawningPool |  |
| Hive | 200 | 150 | 71† | Lair | InfestationPit |  |
| GreaterSpire | 100 | 150 | 26† | Spire | Hive |  |
| Overlord | 100 | 0 | 18† | larva | — | supply |
| BanelingNest | 150 | 50 | 43† | worker | SpawningPool |  |
| EvolutionChamber | 125 | 0 | 25† | worker | — |  |
| Extractor | 25 | 0 | 21† | worker | — | Ⓖ |
| Hatchery | 300 | 0 | 71† | worker | — | Ⓐ |
| HydraliskDen | 150 | 100 | 29† | worker | Lair |  |
| InfestationPit | 150 | 100 | 36† | worker | Lair |  |
| LurkerDenMP | 150 | 150 | 57† | worker | HydraliskDen |  |
| RoachWarren | 200 | 0 | 39† | worker | SpawningPool |  |
| SpawningPool | 250 | 0 | 46† | worker | — |  |
| Spire | 200 | 150 | 66† | worker | Lair |  |
| UltraliskCavern | 200 | 200 | 46† | worker | Hive |  |

---

**Known issue flagged above:** the three Tech Labs show `built_by = worker`, but add-ons
are built by their **parent production building** (Barracks/Factory/Starport), occupying
it for the build with **no SCV**. Reactors are missing entirely. Morphs (Lair/Hive/
OrbitalCommand/WarpGate/GreaterSpire) correctly list their parent as `built_by`.

Build times marked † are best-confidence, not yet calibrated against PTR replays.

---

## Engine cross-check — discrepancies to review

Structure costs/times in `build_data.py` are **hand-entered**; the engine dump has the real
values. Diffing the two (`build_data -> engine`):

### Genuine discrepancies (non-morph) — likely build_data errors, verify & fix
| Building | Field | build_data | engine | Note |
|---|---|---|---|---|
| **Extractor** | min | 25 | **75** | big gap — is this a 5.0.16 economy change, or a build_data error? (Assimilator/Refinery already agree at 75) |
| **Hatchery** | min | 300 | **325** | engine higher (already noted earlier) |
| **Factory** | build s | 36 | **42.9** | engine slower |

### Morphs — engine cost is CUMULATIVE (base + morph), so a raw diff is expected
These use the morph *delta* on purpose. Most look right, but one is suspect:
| Building | build_data | engine (cumulative) | Implied delta | Status |
|---|---|---|---|---|
| OrbitalCommand | 150 | 550 (=CC 400+150) | 150 ✓ | ok |
| Lair | 150 | 475 (=Hatch 325+150) | 150 ✓ | ok |
| Hive | 200/150 | 675/250 (=Lair+200/150) | 200/150 ✓ | ok |
| WarpGate | 50/50 | 150/0 | — | intentional (📋 CLAUDE.md PTR 50/50, not engine) |
| **GreaterSpire** | 100/150, 26s | 350/350, **71.4s** | delta 150/200 | ⚠️ **verify** — my delta (100/150) and time (26s) disagree with the engine; likely wrong |

**Recommendation:** engine-source the non-morph structure costs/times (like we did for units
and upgrades) so hand-entry drift can't happen, and fix GreaterSpire. This is the same class
of issue as the add-ons — hand-entered data that's quietly off.