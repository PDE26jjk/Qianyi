"""Sewings: create, read, recolour and remove seams.

The direction of a seam is the add-on's own: both calls here forward to the
sewing the editor uses, including its two flags, and derive nothing themselves.
An edge is named as ``(pattern, index)`` or ``(pattern, label)``.
"""

from __future__ import annotations

from . import _address as address
from .errors import QyapiError
from ..model.qianyi_project import edge_point_at, normalize_sewing_color


def list(project=None):  # noqa: A001 - the surface's name for this call
    """Every seam in the project, both sides of each."""
    project = address.project_or_refuse(project)
    return address.jsonify({"project": project.name,
                            "sewings": address.sewing_entries(project)})


def of(pattern, project=None):
    """The seams that touch one pattern, plus that pattern's side of each."""
    project = address.project_or_refuse(project)
    target = address.pattern_or_refuse(project, pattern)
    return address.jsonify({"pattern": target.name,
                            "sewings": address.sewing_entries(project, target)})


def sew(edge_a, edge_b, flip=False, color=None, project=None):
    """Stitch two edges with the add-on's own one-to-one sewing.

    The flag is that sewing's own: off pairs each edge's first point, on pairs
    the first edge's first point with the second edge's second. It is passed
    straight through and nothing about the direction is decided here.
    """
    project = address.project_or_refuse(project)
    first, first_index, first_pattern = _resolve(project, edge_a)
    second, second_index, second_pattern = _resolve(project, edge_b)
    sewing = project.add_sewing1to1(first, second, reverse=bool(flip), color=color,
                                    pattern1=first_pattern, pattern2=second_pattern)
    return _created(project, sewing,
                    f"sew {first_pattern.name}[{first_index}] to "
                    f"{second_pattern.name}[{second_index}]")


def sew_at(pattern_a, edge_a, position_a, pattern_b, edge_b, position_b,
           color=None, project=None):
    """Stitch two edges from a position (0..1) on each, the way a click would.

    The positions pick the end of their edge, and the add-on's own click-based
    sewing decides the direction from there.
    """
    project = address.project_or_refuse(project)
    first, first_index, first_pattern = _resolve(project, (pattern_a, edge_a))
    second, second_index, second_pattern = _resolve(project, (pattern_b, edge_b))
    sewing = _stitch(project, (first, first_pattern), float(position_a),
                     (second, second_pattern), float(position_b), color)
    return _created(project, sewing,
                    f"sew {first_pattern.name}[{first_index}] to "
                    f"{second_pattern.name}[{second_index}]")


def set_color(index, color, project=None):
    """Recolour one seam."""
    project = address.project_or_refuse(project)
    sewing = _sewing_at(project, index)
    sewing.color = normalize_sewing_color(color)
    address.write_done(f"recolour a sewing of {project.name}")
    return address.jsonify(address.sewing_entry(project, sewing, int(index)))


def add_span(index, side, pattern, edge, end_edge=None, pos1=0.0, pos2=1.0,
             reverse=False, project=None):
    """Append one drawn run to a side of a seam, and report the new mapping.

    `side` is 1 or 2 and the run is appended after the ones already there, which
    is the order the side is stitched in. `edge` and `end_edge` are named the way
    every other edge is: an index or a label of `pattern`. The report says how
    many runs each side holds, the stitch count the mapping has now, how many
    pairs that changed, and any reason the seam cannot be paired.
    """
    project = address.project_or_refuse(project)
    target = address.pattern_or_refuse(project, pattern)
    line1, _index = address.edge_or_refuse(target, edge)
    line2, _index = address.edge_or_refuse(target, end_edge if end_edge is not None
                                           else edge)
    report = project.add_sewing_span(index, side, line1, float(pos1), line2,
                                     float(pos2), bool(reverse))
    address.write_done(f"add a drawn run to a sewing of {project.name}")
    return address.jsonify(report)


def remove_span(index, side, span, project=None):
    """Drop one drawn run from a side of a seam, and report the new mapping."""
    project = address.project_or_refuse(project)
    report = project.remove_sewing_span(index, side, span)
    address.write_done(f"remove a drawn run from a sewing of {project.name}")
    return address.jsonify(report)


def move_span(index, side, span, offset, project=None):
    """Move one drawn run earlier (a negative offset) or later in the order."""
    project = address.project_or_refuse(project)
    report = project.move_sewing_span(index, side, span, offset)
    address.write_done(f"reorder a sewing of {project.name}")
    return address.jsonify(report)


def remove(index, project=None):
    """Remove one seam."""
    project = address.project_or_refuse(project)
    sewing = _sewing_at(project, index)
    entry = address.sewing_entry(project, sewing, int(index))
    # The project's own removal: it links the seams that are left again (and lets
    # the guard look at them), which a bare `sewings.remove()` would leave stale.
    project.remove_sewing(int(index))
    address.write_done(f"remove a sewing of {project.name}")
    entry["removed"] = True
    entry["sewings_left"] = len(project.sewings)
    return address.jsonify(entry)


# --- internals -------------------------------------------------------------

def _sewing_at(project, index):
    index = int(index)
    if not 0 <= index < len(project.sewings):
        raise QyapiError(f"the project has {len(project.sewings)} sewings",
                         (f"index {index} is out of range",
                          "qyapi.sewings.list() has the indexes"))
    return project.sewings[index]


def _resolve(project, reference):
    """An edge from ``(pattern, index_or_label)``; returns (edge, index, pattern)."""
    try:
        pattern_name, edge_reference = reference
    except Exception as error:
        raise QyapiError(
            f"an edge is named as (pattern, index) or (pattern, label), got {reference!r}"
        ) from error
    pattern = address.pattern_or_refuse(project, pattern_name)
    edge, index = address.edge_or_refuse(pattern, edge_reference)
    return edge, index, pattern


def _stitch(project, first, first_position, second, second_position, color):
    """The add-on's own sewing, given the two edge ends the caller selected.

    `edge_point_at` is the add-on's helper for "the end this position refers
    to"; the sewing then decides the direction from the two points, which is
    what it does when the editor clicks them. Each edge is passed with the pattern
    the position was asked on: one edge serves its whole instance chain, so the
    pair of patterns is what says which members are being stitched.
    """
    edge_a, pattern_a = first
    edge_b, pattern_b = second
    point_a = edge_point_at(edge_a, float(first_position))
    point_b = edge_point_at(edge_b, float(second_position))
    return project.add_sewing1to1_from_points(edge_a, point_a, edge_b, point_b,
                                              color=color, pattern1=pattern_a,
                                              pattern2=pattern_b)


def _created(project, sewing, message):
    if sewing is None:
        reason = getattr(project, "last_sewing_error", "") or "unknown reason"
        raise QyapiError(f"that seam was refused: {reason}",
                         ("the add-on refuses a seam whose two edges overlap",
                          "or whose side has no sections to stitch",
                          "qyapi.patterns.get() shows the edges of a pattern"))
    address.write_done(message)
    return address.jsonify(address.sewing_entry(project, sewing, sewing.get_index()))
