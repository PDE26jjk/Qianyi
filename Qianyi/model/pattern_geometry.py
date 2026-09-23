"""The pattern-editing commands: divide edges, treat a corner, fan a panel.

Every command measures along the sampled curve, writes its result back as points
(a straight piece stays straight, anything else becomes a fitted cubic spline)
and applies to every member of the panel's instance chain. Nothing here touches
Blender's selection, rebuilds a section or merges two points by deleting one:
the operators are thin wrappers around these functions.
"""

from __future__ import annotations

import math

import numpy as np

from .. import global_data
from ..utilities.curve_fit import (cumulative_length, fit_control_points,
                                   polyline_length, resample_by_arc_length,
                                   slice_by_arc_length)
from .generator import instance_chain
from .geometry import Edge2D, Vertex2D
from .model_data import refresh_all_uuids
from .pattern import boundary_self_intersection

FIT_TOLERANCE_MM = 0.05        # how far a written piece may sit from its shape
FIT_MAX_CONTROL_POINTS = 12    # ... before the closest fit is kept as it stands
# Two points closer than this are the same point: the triangulator does not
# define a result for edges below this scale.
MERGE_THRESHOLD_MM = 0.5
# How finely an arc a command produces is sampled for its crossing test.
CORNER_ARC_SAMPLES = 64
# The polyline a command measures on: the edge's own samples taken again at
# equal arc steps. The edge's render samples are parametric - denser wherever
# the curve's parameter bunches - so a command that cuts by arc length reads
# them through this, where a sample's index and its arc position agree.
MEASURE_SAMPLES = 1024


class GeometryRefused(ValueError):
    """A command refused to run: what it could not do, and what to do instead."""

    def __init__(self, reason, *hints):
        super().__init__(reason)
        self.reason = reason
        self.hints = tuple(hints)


# ------------------------------------------------------------------- shared

def _chain_members(pattern) -> list:
    """The panel and its linked copies, refusing a chain whose shapes drifted.

    The outline and the internal lines are both written to every member by
    index, so a copy that lost a line - or whose line holds a different number
    of edges - would be written with pieces that do not fit it.
    """
    members = instance_chain(pattern)
    primary = members[0]
    for member in members:
        if (len(member.vertices) != len(primary.vertices)
                or len(member.edges) != len(primary.edges)
                or len(member.internal_lines) != len(primary.internal_lines)):
            raise GeometryRefused(
                f"{member.name!r} is a copy of {primary.name!r} with a different shape",
                "copies are edited together; detach or rebuild before editing one")
        for line_index, line in enumerate(primary.internal_lines):
            if len(member.internal_lines[line_index].edges) != len(line.edges):
                raise GeometryRefused(
                    f"{member.name!r} is a copy of {primary.name!r} with a different "
                    f"internal line {line_index}",
                    "copies are edited together; detach or rebuild before editing one")
    return members


def _ensure_shape(pattern, indices, edges=None) -> None:
    """Rebuild the sampled points when one of these edges has none.

    A re-run from the redo panel starts from a state Blender has just rolled
    back to, where the samples may not have been built again yet. `edges` is
    the collection the edges live in - the outline, or one internal line's
    edges; the samples are rebuilt for the whole panel either way.
    """
    edges = pattern.edges if edges is None else edges
    for index in indices:
        if edges[index].render_points is None:
            pattern.forced_update()
            return


def _table(pattern, index, edges=None) -> dict:
    """One edge's sampled polyline and its length.

    The polyline is the edge's own samples taken again at equal arc steps
    (`MEASURE_SAMPLES`): the commands measure, cut and fit by arc length, and
    on a uniform polyline a sample's index and its arc position are the same
    thing - no reader has to remember that the render samples are parametric.
    """
    edges = pattern.edges if edges is None else edges
    points = np.asarray(edges[index].render_points, dtype=np.float64)
    if points.ndim != 2 or len(points) < 2:
        raise GeometryRefused(f"edge {index} of {pattern.name!r} has no shape")
    points = resample_by_arc_length(points, MEASURE_SAMPLES)
    return {"points": points, "length": polyline_length(points)}


def _point_on(points, local_length) -> np.ndarray:
    """The point at one arc length along a sampled polyline."""
    lengths = cumulative_length(points)
    local_length = min(max(float(local_length), 0.0), float(lengths[-1]))
    return np.array((np.interp(local_length, lengths, points[:, 0]),
                     np.interp(local_length, lengths, points[:, 1])), dtype=np.float64)


def _piece_lengths(length, cuts) -> list:
    """The arc length of every piece one edge is divided into."""
    bounds = [0.0, *sorted(cuts), float(length)]
    return [bounds[index + 1] - bounds[index] for index in range(len(bounds) - 1)]


def _write_piece(edge, piece) -> tuple:
    """Write a piece as a straight edge, or as a spline through fitted points."""
    control, reached, error = fit_control_points(piece, FIT_TOLERANCE_MM,
                                                FIT_MAX_CONTROL_POINTS)
    if len(control) < 3:
        edge.set_curve("straight")
    else:
        edge.set_curve("spline", points=[(float(point[0]), float(point[1]))
                                         for point in control[1:-1]])
    return reached, error


def _split_edge(pattern, index, cuts, table, edges=None) -> list:
    """Rewrite one edge as the pieces its cuts describe, and return the warnings.

    The first piece keeps the edge object, so a seam that named it still does;
    the pieces after it are new edges, placed after it in the loop. `edges` is
    the collection the edge lives in - the panel's outline, or one internal
    line's edges. The new vertices join the panel's own vertices either way,
    which is the pool an internal line's edges index into as well.
    """
    edges = pattern.edges if edges is None else edges
    bounds = [0.0, *sorted(cuts), table["length"]]
    pieces = [slice_by_arc_length(table["points"], bounds[step], bounds[step + 1])
              for step in range(len(bounds) - 1)]
    # Re-fetch the edge: adding one to the collection moves the wrappers.
    edge = edges[index]
    vertex, end_index = int(edge.vertex_index[0]), int(edge.vertex_index[1])
    warnings = []
    for position, piece in enumerate(pieces):
        if position + 1 == len(pieces):
            next_index = end_index
        else:
            next_index = pattern.add_vertex((float(piece[-1][0]), float(piece[-1][1])))
            pattern.vertices[next_index].get_temp_data()
        if position:
            target = edges.add()
            target.pattern = pattern
            target.get_temp_data()
        else:
            target = edge
        target.vertex_index[0] = vertex
        target.vertex_index[1] = next_index
        reached, error = _write_piece(target, piece)
        target.update(pattern)
        if not reached:
            warnings.append({"edge": index, "piece": position, "error_mm": error})
        if position:
            edges.move(len(edges) - 1, index + position)
        vertex = next_index
    return warnings


def _resample(pattern) -> None:
    """Build every edge's points again from the sections the outline has now.

    The samples are the sampling pass's derived data and the last edit can leave
    an edge holding the points of the shape it had before, which the mesh pass
    then counts against the sections and reports.
    """
    for edge in pattern.edges:
        edge.need_update_points = True
        edge.update(pattern)


def _sewing_end_at(points, pos) -> tuple:
    """Where a seam endpoint sits on an edge: its arc length and its point.

    `pos` is a fraction of the edge's arc length - the fraction the sewing
    picker writes - so it is read against the samples' cumulative arc length,
    landing between the samples rather than snapped to the nearest one. The
    samples themselves are parametric and not arc-uniform, which is exactly
    why the read goes through the lengths and not the sample index.
    """
    points = np.asarray(points, dtype=np.float64)
    lengths = cumulative_length(points)
    target = min(max(float(pos), 0.0), 1.0) * float(lengths[-1])
    lower = min(max(int(np.searchsorted(lengths, target, side="right")) - 1, 0),
                len(points) - 2)
    span = lengths[lower + 1] - lengths[lower]
    weight = min(max((target - lengths[lower]) / span, 0.0), 1.0) if span > 0 else 0.0
    arc = float(lengths[lower] + weight * span)
    point = points[lower] + weight * (points[lower + 1] - points[lower])
    return arc, np.asarray(point, dtype=np.float64)


def _sewing_ends(pattern, edges) -> list:
    """Every seam endpoint that sits on one of these `(index, points)` edges.

    Kept for the commands that only touch the outline: the indices are turned
    into the uuid-keyed form the shared remap reads, while the edges are still
    the ones the seams named - callers resolve before they write.
    """
    return _sewing_ends_on(pattern, [(pattern.edges[index].global_uuid, points)
                                     for index, points in edges])


def _sewing_ends_on(pattern, entries) -> list:
    """Every seam endpoint on one of these `(edge uuid, sampled points)` edges.

    Keyed by uuid rather than by index, so a command that divides outline edges
    and internal line edges in one go collects the ends of both, and a seam
    that named an internal line is moved with the rest.
    """
    run = {uuid_value: np.asarray(points, dtype=np.float64)
           for uuid_value, points in entries}
    ends = []
    for sewing_index, sewing in enumerate(pattern.project.sewings):
        for side_index, side in enumerate(sewing.sides):
            for which, uuid_value, pos in ((1, side.line1_uuid, side.pos1),
                                           (2, side.line2_uuid, side.pos2)):
                points = run.get(uuid_value)
                if points is None:
                    continue
                arc, point = _sewing_end_at(points, pos)
                ends.append({"sewing": sewing_index, "side": side_index, "which": which,
                             "uuid": uuid_value, "arc": arc, "point": point})
    return ends


def _remap_sewing_ends(pattern, ends, pieces, trimmed=False) -> int:
    """Put every seam endpoint back on the piece that replaced its edge.

    Kept for the commands whose pieces are keyed by outline index: the index
    reads back the uuid the seam named, because the first piece a split leaves
    behind is the edge object itself. `_remap_sewing_ends_on` is the shared
    body.
    """
    return _remap_sewing_ends_on(
        pattern, ends,
        {pattern.edges[index].global_uuid: table for index, table in pieces.items()},
        trimmed)


def _remap_sewing_ends_on(pattern, ends, pieces, trimmed=False) -> int:
    """Put every seam endpoint back on the piece that replaced its edge.

    `pieces` maps the uuid of the edge a seam named to the
    `(uuid, start arc, end arc)` table of the pieces that replaced it. The
    endpoint keeps the place it was drawn at: the position of the point on the
    new edge closest to the point it had. `trimmed` is for a command that
    only shortens an edge, whose single piece holds no share of the original.
    """
    if not ends:
        return 0
    moved = 0
    for end in ends:
        table = pieces.get(end["uuid"])
        if not table:
            continue
        chosen = None
        last = len(table) - 1
        for position, (uuid_value, arc_start, arc_end) in enumerate(table):
            if ((trimmed and last == 0)
                    or arc_start - 1e-9 <= end["arc"] < arc_end - 1e-9
                    or (position == last and end["arc"] <= arc_end + 1e-9)):
                chosen = (uuid_value, global_data.get_obj_by_uuid(uuid_value, check_uuid=False))
                break
        if chosen is None or chosen[1] is None:
            continue
        points = chosen[1].render_points
        if points is None:
            continue
        points = np.asarray(points, dtype=np.float64)
        index = int(np.sqrt(((points - end["point"]) ** 2).sum(axis=1)).argmin())
        # The stored fraction is of arc length, and the samples are not
        # arc-uniform, so the nearest sample's own arc position is what goes
        # back into `pos` - not its index between the samples.
        lengths = cumulative_length(points)
        pos = float(lengths[index] / lengths[-1]) if lengths[-1] > 0 else 0.0
        side = pattern.project.sewings[end["sewing"]].sides[end["side"]]
        if end["which"] == 1:
            side.line1_uuid, side.pos1 = chosen[0], pos
        else:
            side.line2_uuid, side.pos2 = chosen[0], pos
        moved += 1
    return moved


def _mark_sewings(pattern, ends) -> int:
    """Signal both panels of every seam this command moved, so they relink."""
    marked = set()
    for end in ends:
        if end["sewing"] in marked:
            continue
        marked.add(end["sewing"])
        sewing = pattern.project.sewings[end["sewing"]]
        for attribute in ("pattern1", "pattern2"):
            target = getattr(sewing, attribute, None)
            if target is not None:
                target.need_sewing_update = True
    return len(marked)


# ------------------------------------------------------------------- division

def _edges_of_uuids(uuids) -> list:
    """The edges among these uuids, skipping the ones that do not resolve."""
    edges = []
    for uuid_value in uuids:
        try:
            edge = global_data.get_obj_by_uuid(uuid_value, check_uuid=True)
        except Exception:
            edge = None
        if isinstance(edge, Edge2D):
            edges.append(edge)
    return edges


def _piece_table(pattern, index, lengths) -> list:
    """The pieces one divided outline edge was written as: (uuid, start, end)."""
    return _piece_table_on(pattern.edges, index, lengths)


def _piece_table_on(edges, index, lengths) -> list:
    """The pieces one divided edge was written as: (uuid, start arc, end arc)."""
    table, arc = [], 0.0
    for position, length in enumerate(lengths):
        table.append((edges[index + position].global_uuid, arc, arc + length))
        arc += length
    return table


# --------------------------------------------------------------------- corner

def is_outline_vertex(obj) -> bool:
    """Whether this object is a vertex of a panel's outline (not of an edge)."""
    if not isinstance(obj, Vertex2D):
        return False
    try:
        return ".vertices[" in obj.path_from_id()
    except Exception:
        return False


def _unit(vector) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float64)
    length = float(np.hypot(*vector))
    return np.zeros(2) if length <= 1e-12 else vector / length


def _cross(a, b) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _perp_ccw(vector) -> np.ndarray:
    return np.array((-vector[1], vector[0]), dtype=np.float64)


def _bezier_points(p0, c1, c2, p1, count) -> np.ndarray:
    steps = np.linspace(0.0, 1.0, count)[:, None]
    inverse = 1.0 - steps
    return (inverse ** 3 * p0 + 3.0 * inverse ** 2 * steps * c1
            + 3.0 * inverse * steps ** 2 * c2 + steps ** 3 * p1)


def _arc_between(start, end, centre, radius) -> dict:
    """The Bezier that reproduces the circular arc from `start` to `end`.

    The arc is taken the short way round; both ends sit on the circle, so the
    handles that make a cubic reproduce it are `4/3 * tan(sweep / 4)` of the
    radius along the tangents.
    """
    v1 = np.asarray(start, dtype=np.float64) - centre
    v2 = np.asarray(end, dtype=np.float64) - centre
    sweep = math.atan2(_cross(v1, v2), float(np.dot(v1, v2)))
    scale = (4.0 / 3.0) * math.tan(sweep / 4.0) * radius
    handle1 = np.asarray(start, dtype=np.float64) + _perp_ccw(v1) / radius * scale
    handle2 = np.asarray(end, dtype=np.float64) - _perp_ccw(v2) / radius * scale
    return {"centre": centre, "handle1": handle1, "handle2": handle2,
            "sweep": sweep, "radius": radius,
            "points": _bezier_points(np.asarray(start, dtype=np.float64), handle1,
                                     handle2, np.asarray(end, dtype=np.float64),
                                     CORNER_ARC_SAMPLES)}


# ------------------------------------------------------------------------ fan


