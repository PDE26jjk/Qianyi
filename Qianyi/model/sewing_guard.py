"""Seams whose two sides the linking run did not pair: flagged, patterns kept out.

A seam's stitches are the samples of the pieces the linking run paired: a piece
of one side and the piece of the other it was linked to. A run nested inside
another seam's run on the same edge can break that: the linking cuts the shared
edge at the outer seam's boundaries, and those cuts are not mirrored onto the
inner seam's other side, so one side is left with pieces the other side has no
partner for. Nothing here changes the linking - that would mean reworking the
merge - and the seam is not stitched either: it is flagged, the two patterns it
joins are marked the way a crossing outline is (no mesh, no simulation start, the
reason shown on the pattern), and the user is left to fix the seam graph.

Sewing a longer side to a shorter one is not one of the ways a seam can fail, and
nothing here looks at lengths or at sample counts: the two sides are paired by
the pieces the linking run left, so a puff sleeve's cap goes into its armhole and
a band onto the edge it trims.

The check is a walk over the pieces, not a stitch, so it can run every time the
seam graph is re-linked - including right after an edit, before any mesh is
built. Everything it writes, it clears again once the seam pairs up: the flags
carry the text this module set, so a mesh error of another kind is left alone.
"""

from __future__ import annotations

from ..utilities.console import console
from .model_data import define_temp_prop
from .pattern import Pattern, VALIDITY_INVALID, VALIDITY_UNKNOWN
from .sewing import Sewing, side_pieces

# The flag a seam carries while its sides do not pair, and the mark this module
# leaves on a pattern so it clears what it wrote and nothing else.
define_temp_prop(Sewing, "stitch_error", "")
define_temp_prop(Pattern, "sewing_error", "")


def piece_key(section) -> tuple:
    """A piece of a walk, named so two seams can be compared by identity."""
    pattern = section.pattern  # a piece names the pattern it belongs to
    edge = section.edge
    return (pattern.global_uuid if pattern is not None else -1,
            edge.global_uuid if edge is not None else -1,
            round(float(section.start_pos), 6), round(float(section.end_pos), 6))


def seam_error(sewing):
    """Why this seam cannot be stitched, or None.

    None covers both "it can be stitched" and "this is not the check's business":
    a side whose boundaries the linking run did not place at all raises when it is
    walked, and that is reported where it happens (`calc_sewing_sections` warns
    about it), not here.

    The two sides are paired by the pieces the linking run left
    (`pair_by_sections`), so a side that is longer, or a join where one side has
    two samples and the other one, is stitched rather than refused, and nothing
    here compares the walks. What is left is a seam the linking run did not pair
    - a piece of one side with no linked piece on the other, which is what
    happens when another seam cuts the same edge and the cut is not mirrored -
    and the seam with nothing to stitch at all, whose drawn runs are gone.
    """
    if not len(sewing.side1.spans) or not len(sewing.side2.spans):
        # A side whose drawn runs were all dropped - an edge it used was removed,
        # say - has nothing to stitch. Saying so is what keeps the seam visible
        # instead of silently stitching nothing.
        which = "one side" if not len(sewing.side1.spans) else "the other side"
        return (f"{which} holds no drawn run left, so there is nothing to stitch: "
                f"draw a run on it, or remove the seam")
    try:
        first = side_pieces(sewing.side1)
        second = side_pieces(sewing.side2)
    except ValueError:
        # A side whose boundaries the linking run did not place at all: that is
        # reported where it happens (`calc_sewing_sections` warns about it).
        return None
    if len(first) != len(second):
        return (f"its two sides were cut into {len(first)} and {len(second)} pieces, "
                f"so the linking run did not pair them: another seam cuts the same "
                f"edge, and the cut is not mirrored onto this one")
    return None


def involved_seams(project, sewing, pieces) -> list:
    """The seams that share a piece with a seam that cannot be paired.

    A seam that runs over the same pieces as the broken one is part of the same
    problem: either one of them has to move. Both are flagged, so the user can
    see which seams to look at.
    """
    keys = {piece_key(piece) for piece in pieces}
    involved = [sewing]
    for other in project.sewings:  # loop: one seam per compare
        if other is sewing:
            continue
        for side in (other.side1, other.side2):
            try:
                walked = [entry[0] for entry in side_pieces(side)]
            except ValueError:
                continue
            if any(piece_key(piece) in keys for piece in walked):
                involved.append(other)
                break
    return involved


def check_sewings(project) -> list:
    """Flag every seam whose two sides do not pair, and mark their patterns.

    Returns the seams that are flagged. Call it after a linking run: the walk it
    makes reads the pieces the run left, including the ones it cut without
    sampling them.
    """
    broken = {}
    for sewing in project.sewings:  # loop: one seam per check
        reason = seam_error(sewing)
        if reason is None:
            continue
        seam_pieces = []
        for side in (sewing.side1, sewing.side2):
            try:
                walked = [entry[0] for entry in side_pieces(side)]
            except ValueError:
                continue
            seam_pieces.extend(walked)
        broken[sewing.global_uuid] = (sewing, reason, seam_pieces)

    flagged = {}
    for sewing, reason, seam_pieces in broken.values():
        for entry in involved_seams(project, sewing, seam_pieces):
            if entry.global_uuid in flagged:
                continue
            flagged[entry.global_uuid] = (entry, reason if entry is sewing
                                          else f"it shares a run with a seam that cannot be "
                                               f"paired ({reason})")

    for sewing in project.sewings:  # loop: one flag per seam, written or cleared
        entry = flagged.get(sewing.global_uuid)
        sewing.stitch_error = entry[1] if entry else ""

    for pattern in project.patterns:  # loop: one mark per pattern, written or cleared
        reasons = [text for sewing, text in flagged.values()
                   if pattern in (sewing.pattern1, sewing.pattern2)]
        if reasons:
            text = reasons[0]
            pattern.sewing_error = text
            pattern.mesh_error = text
            pattern.validity_state = VALIDITY_INVALID
            console.warning(f"pattern {pattern.name or '(unnamed)'}: no mesh: {text}")
        elif pattern.sewing_error:
            # This module wrote that text, so it is this module's to take back;
            # the outline is checked again because its answer may also have been
            # replaced by the mark.
            pattern.sewing_error = ""
            if pattern.mesh_error:
                pattern.mesh_error = None
            if pattern.validity_state == VALIDITY_INVALID:
                pattern.validity_state = VALIDITY_UNKNOWN

    return [sewing for sewing, _reason, _pieces in broken.values()]
