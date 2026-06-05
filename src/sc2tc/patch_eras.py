"""SC2 build number -> patch_era string lookup.

The replay parser surfaces the game's base_build int (e.g. 89165, 95299, 96883).
The DB tags every fact with a patch_era string (e.g. '5.0.13', '5.0.15', '5.0.16').
This module bridges the two so the extractor can emit patch_era on every replay JSON.

Maintenance: when Blizzard ships a new patch, add the new (build, era) pair below.
The build number is in the replay file (see Zephyrus parser output) and in the
filename of new protocol files Blizzard publishes at github.com/Blizzard/s2protocol
under s2protocol/versions/protocolNNNNN.py.

A build returns None if it's not in the table — emitted as null in the JSON so
downstream filtering can spot the gap and prompt a table update.
"""

# (min_build_inclusive, era_label) — pairs are sorted, then build_to_era()
# returns the era of the highest entry <= the queried build.
#
# Where the boundaries come from: Blizzard publishes a new s2protocol file at each
# game build. The labelled patches below come from SC2 patch notes; the build of
# the first replay that contains a new patch's changes is the boundary build.
_ERA_BOUNDARIES: list[tuple[int, str]] = [
    (84643, "5.0.12"),   # earliest era currently bundled in the parser gamedata
    (87702, "5.0.13"),
    (89165, "5.0.13"),
    (89720, "5.0.14"),
    (92440, "5.0.14"),
    (95299, "5.0.15"),
]


def build_to_era(base_build: int) -> str | None:
    """Return the patch_era for the given SC2 build, or None if unmapped.

    >>> build_to_era(89165)
    '5.0.13'
    >>> build_to_era(96883)   # post-95299, not in table yet
    '5.0.15'                  # falls through to last known era; revisit when 5.0.16 ships
    """
    era: str | None = None
    for boundary, label in _ERA_BOUNDARIES:
        if base_build >= boundary:
            era = label
        else:
            break
    return era


def known_builds() -> list[int]:
    """List of build boundaries currently mapped. Useful for diagnostics."""
    return [b for b, _ in _ERA_BOUNDARIES]
