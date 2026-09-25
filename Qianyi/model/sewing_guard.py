"""Seams whose two sides cannot be paired: flagged, and their patterns kept out.

A seam's stitches are the two sides' walks zipped together, which needs both
walks to take the same number of samples. A run nested inside another seam's run
on the same edge can break that: the linking cuts the shared edge at the outer
seam's boundaries, and those cuts are not mirrored onto the inner seam's other
side, so one walk crosses five pieces and the other three. Nothing here changes
the linking - that would mean reworking the merge - and nothing here refuses the
seam either: the seam is flagged, the two patterns it joins are marked the way a
crossing outline is (no mesh, no simulation start, the reason shown on the
pattern), and the user is left to fix the seam graph.

The check is a walk over the pieces, not a stitch, so it can run every time the
seam graph is re-linked - including right after an edit, before any mesh is
built. Everything it writes, it clears again once the seam pairs up: the flags
carry the text this module set, so a mesh error of another kind is left alone.
"""

from __future__ import annotations

import math

from ..utilities.console import console
from .model_data import define_temp_prop
from .pattern import Pattern, VALIDITY_INVALID, VALIDITY_UNKNOWN
from .sewing import Sewing

# The flag a seam carries while its sides do not pair, and the mark this module
# leaves on a pattern so it clears what it wrote and nothing else.
define_temp_prop(Sewing, "stitch_error", "")
define_temp_prop(Pattern, "sewing_error", "")

# How many pieces one walk may visit before the check calls it a loop: a walk is
# over the pieces of one chain, and no pattern has this many.
WALK_LIMIT = 10000


def piece_samples(piece, pattern) -> int:
    """How many samples a piece takes in the walk.

    A piece carries the count it was sampled as. A piece that carries none is one
    a linking run has just cut: the sampling pass would give it one sample per
    granularity step, capped below at one, which is what the walk will take.
    """
    if piece.seg > 0:
        return piece.seg
    length = float(piece.absolute_length())
    step = max(float(pattern.granularity), 1e-6)
    return max(math.ceil(length / step), 1)


def side_walk(side) -> tuple:
    """One side of a seam as the stitch walk would read it.

    Returns ``(pieces, samples)``: the pieces the walk visits in order, and how
    many samples they add up to - the count the stitch walk would produce, which
    is what has to match the other side's.
    """
    pattern = side.pattern
    if pattern is None:
        raise ValueError("this sewing side names no pattern")
    start = pattern.boundary_section(side.line1, side.pos1, side.reverse)
    end = pattern.boundary_section(side.line2, side.pos2, side.reverse)
    pieces = []
    samples = 0
    section = start
    started = False
    while (section is not end or not started) and len(pieces) < WALK_LIMIT:
        following = section.prev if side.reverse else section.next
        size = piece_samples(section, pattern)
        # The walk carries the sample at its far end as well: the first piece of
        # a backwards walk, the last one of a forwards walk.
        if side.reverse:
            if not started:
                size += 1
        elif following is end:
            size += 1
        pieces.append(section)
        samples += size
        section = following
        started = True
    if len(pieces) >= WALK_LIMIT:
        raise ValueError("this sewing side walks in a loop")
    return pieces, samples


def piece_key(section) -> tuple:
    """A piece of a walk, named so two seams can be compared by identity."""
    pattern = section.pattern  # a piece names the pattern it belongs to
    edge = section.edge
    return (pattern.global_uuid if pattern is not None else -1,
            edge.global_uuid if edge is not None else -1,
            round(float(section.start_pos), 6), round(float(section.end_pos), 6))


def pattern_name(pattern) -> str:
    """A pattern's name for a message, saying so when it is not there any more."""
    return (pattern.name or "(unnamed pattern)") if pattern is not None else "(a pattern that is gone)"


def seam_error(sewing):
    """Why this seam's two sides cannot be paired, or None.

    None covers both "they pair" and "this is not the check's business": a side
    whose boundaries the linking run did not place at all raises when it is
    walked, and that is reported where it happens (`calc_sewing_sections` warns
    about it), not here.
    """
    try:
        _first, first_samples = side_walk(sewing.side1)
        _second, second_samples = side_walk(sewing.side2)
    except ValueError:
        return None
    if first_samples == second_samples:
        return None
    return (f"its two sides are walked at {first_samples} and {second_samples} samples, so "
            f"they cannot be paired: this seam's run is nested inside another seam's run on "
            f"{pattern_name(sewing.side1.pattern)} or {pattern_name(sewing.side2.pattern)}, and "
            f"the shared edge is cut where the two sides of it no longer line up")


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
                walked, _samples = side_walk(side)
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
                walked, _samples = side_walk(side)
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
