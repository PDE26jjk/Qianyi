"""The pattern-editing commands: divide edges, treat a corner, fan a pattern.

Every command measures along the sampled curve, writes its result back as points
(a straight piece stays straight, anything else becomes a fitted cubic spline)
and applies to every member of the pattern's instance chain. Nothing here touches
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
from ..utilities.cubic_spline import cubic_spline_2d_numpy
from ..utilities.geometric_operation import generate_curve_points

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
    """The pattern and the copies that share its Sketch.

    There is nothing to compare: a chain holds one Sketch, so its members cannot
    hold different geometry, and a copy that needs a shape of its own is
    detached first. `members` is still the list the commands need, because the
    derived work - the samples, the mesh - is each member's own.
    """
    return pattern.sketch_members()


def _ensure_shape(pattern, indices, edges=None) -> None:
    """Rebuild the drawn points when one of these edges has none.

    A re-run from the redo panel starts from a state Blender has just rolled
    back to, where the points may not have been built again yet, and the
    commands below measure the curve as it is drawn. `edges` is the collection
    the edges live in - the outline, or one internal line's edges; the stage is
    rebuilt for the whole Sketch either way.
    """
    edges = pattern.edges if edges is None else edges
    for index in indices:
        if edges[index].render_points is None:
            pattern.sketch.update()
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
    the collection the edge lives in - the pattern's outline, or one internal
    line's edges. The new vertices join the pattern's own vertices either way,
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
            target.get_temp_data()
        else:
            target = edge
        target.vertex_index[0] = vertex
        target.vertex_index[1] = next_index
        reached, error = _write_piece(target, piece)
        target.update()
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
        edge.update()


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
    """Signal both patterns of every seam this command moved, so they relink."""
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
    """Whether this object is a vertex of a pattern's outline (not of an edge)."""
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


# --------------------------------------------------------------- dragged edge

# How close to an end a drag may take hold of a curve. The two ends are the
# points the piece shares with its neighbours, so they cannot move, and the
# closer the grab is to one of them the less of the piece the pointer can pull:
# the grab is kept this far inside one rather than refused.
DRAG_END_MARGIN = 0.01
# The samples a drag draws its preview from. Fewer than the edge's own render
# points: this is a shape on screen, remade at the pointer's rate.
DRAG_PREVIEW_SAMPLES = 256
# The samples a drag measures its base curve on. A straight edge's own render
# points are its two ends - there is nothing to sample between them - so the
# base is built here from the form the edge is in.
DRAG_BASE_SAMPLES = 1024
# The rows the falloff is projected onto the edge's own weights over. The
# projection runs on every mouse move, and this many rows answer the same shape
# as the whole base: the falloff and the weights are both smooth in the
# parameter.
DRAG_SOLVE_SAMPLES = 129


def _falloff(parameters, grab):
    """How much of the pointer's offset each parameter of a piece takes.

    One at the grabbed parameter and zero at both ends of the piece, easing in
    between: the shape of one point pulled on a curve whose ends are held. Each
    side is measured against its own distance to its end, so the falloff reaches
    both ends wherever the grab sits.
    """
    parameters = np.asarray(parameters, dtype=np.float64)
    spans = np.where(parameters <= grab, max(grab, 1e-9), max(1.0 - grab, 1e-9))
    fraction = np.clip(np.abs(parameters - grab) / spans, 0.0, 1.0)
    return 0.5 * (1.0 + np.cos(np.pi * fraction))


def _nearest_sample(points, point) -> int:
    """The index of the sample of `points` closest to `point`."""
    offset = np.asarray(points, dtype=np.float64) - np.asarray(point, dtype=np.float64)
    return int(np.argmin((offset * offset).sum(axis=1)))


def _control_knots(points) -> np.ndarray:
    """The parameters a spline's own sampler gives its points, normalized.

    This is the chord-length knot vector `generate_curve_points` builds for a
    piece: its two ends and the control points between them, in order.
    """
    points = np.asarray(points, dtype=np.float64)
    lengths = cumulative_length(points)
    total = float(lengths[-1]) if len(lengths) else 0.0
    if total <= 0.0:
        return np.linspace(0.0, 1.0, len(points))
    return lengths / total


def _curve_samples(points, handle1=None, handle2=None, count=DRAG_PREVIEW_SAMPLES):
    """The polyline a form is drawn as: the call the edge draws itself with."""
    points = np.asarray(points, dtype=np.float64)
    if len(points) == 2 and handle1 is None and handle2 is None:
        return resample_by_arc_length(points, count)
    return np.asarray(generate_curve_points(points, handle1, handle2, count),
                      dtype=np.float64)


def _on_chord(ends, handles, tolerance=FIT_TOLERANCE_MM) -> bool:
    """Whether a piece's handles still lie on the chord between its two ends."""
    start = np.asarray(ends[0], dtype=np.float64)
    step = np.asarray(ends[1], dtype=np.float64) - start
    length = float(np.hypot(*step))
    if length <= 0.0:
        return False
    normal = np.array((-step[1], step[0]), dtype=np.float64) / length
    return all(abs(float((np.asarray(handle, dtype=np.float64) - start) @ normal))
               <= tolerance for handle in handles)


def _pair(point) -> tuple:
    """One point as a plain pair: the form `Edge2D.set_curve` takes."""
    return (float(point[0]), float(point[1]))


def _distance_to_polyline(points, point) -> float:
    """The distance from `point` to the closest place on a polyline."""
    points = np.asarray(points, dtype=np.float64)
    point = np.asarray(point, dtype=np.float64)
    starts = points[:-1]
    steps = points[1:] - starts
    squares = (steps * steps).sum(axis=1)
    ratios = np.clip(((point - starts) * steps).sum(axis=1)
                     / np.where(squares > 0.0, squares, 1.0), 0.0, 1.0)
    spots = starts + steps * ratios[:, None]
    return float(np.sqrt(((spots - point) ** 2).sum(axis=1)).min())


class EdgeDrag:
    """One edge's shape while the pointer drags it.

    The pointer's offset moves the point of the curve the drag was started on,
    and the rest of the piece follows with a smooth falloff that dies at both
    ends: what it looks like is one point of the outline pulled while the corners
    it shares with its neighbours stay where they are.

    The falloff is laid out along the curve's own parameter and then written in
    what the edge can express - the two Bernstein weights of a line or a Bezier,
    the control points' own influence for a spline - and scaled so that the
    grabbed point lands exactly on the pointer rather than near it. The edge is
    written back in the form it had: nothing is added, removed, or turned into
    another form, and the two ends never move.

    The base curve is read once, when the drag starts, so every frame of one drag
    measures the same shape from the same grab.
    """

    def __init__(self, edge, grab_point):
        self.edge_uuid = edge.global_uuid
        self.kind = edge.kind
        self.handle_types = (edge.handle1_type, edge.handle2_type)
        self.handles = (np.asarray(edge.handle1.co[:], dtype=np.float64),
                        np.asarray(edge.handle2.co[:], dtype=np.float64))
        if self.kind == "straight":
            # A straight edge carries its handles wherever it was made; the
            # curve it draws is the chord, whose two handles are a third and two
            # thirds of the way along it. A drag starts from the curve on
            # screen, not from unused numbers beside it.
            start = np.asarray(edge.vertex0.co[:], dtype=np.float64)
            step = (np.asarray(edge.vertex1.co[:], dtype=np.float64) - start) / 3.0
            self.handles = (start + step, start + 2.0 * step)
        self.controls = np.asarray([point.co[:] for point in edge.spline_points],
                                   dtype=np.float64).reshape((-1, 2))
        # The base curve is what the edge draws now, taken in one piece: the
        # edge's own render points leave a straight edge as its two ends, and a
        # drag has to measure between them.
        ends = np.vstack((edge.vertex0.co[:], self.controls, edge.vertex1.co[:]))
        vectors = tuple(None if kind == "VECTOR" else handle
                        for kind, handle in zip(self.handle_types, self.handles))
        self.vectors = vectors
        self.base = _curve_samples(ends, vectors[0], vectors[1], DRAG_BASE_SAMPLES)
        if len(self.base) < 3 or polyline_length(self.base) <= 0.0:
            raise GeometryRefused("this edge has no length to drag")
        self.parameters = np.linspace(0.0, 1.0, len(self.base))
        self.grab_index = _nearest_sample(self.base, grab_point)
        self.grab_point = self.base[self.grab_index].copy()
        self.grab = float(np.clip(self.parameters[self.grab_index], DRAG_END_MARGIN,
                                  1.0 - DRAG_END_MARGIN))
        self.knots = _control_knots(ends)
        # Every frame of the drag solves over this slice of the base, not over
        # all of it: the shape it answers is the same and the work is a fraction.
        self.solve = slice(None, None, max(len(self.base) // DRAG_SOLVE_SAMPLES, 1))

    def weights(self) -> np.ndarray:
        """The falloff along the piece, one value per sample of the base curve."""
        return _falloff(self.parameters, self.grab)

    def form(self, offset) -> dict:
        """What the edge becomes when the pointer is `offset` from the grab.

        ``kind`` is the edge's own form and the rest is what `Edge2D.set_curve`
        takes for it, together with the polyline that form is drawn as and how
        far that polyline ends up from the pointer. The two are the same shape -
        the preview is drawn from the call the write uses - so `miss` is the
        distance the pointer's own point is left at, which the log keeps.
        """
        offset = np.asarray(offset, dtype=np.float64)
        form = self._spline_form(offset) if self.kind == "spline" else self._bezier_form(offset)
        wanted = self.grab_point + offset
        form["miss"] = _distance_to_polyline(form["samples"], wanted)
        return form

    def _bezier_form(self, offset) -> dict:
        """The two handles a drag moves, and the curve they describe."""
        step = self.parameters[self.solve][:, None]
        inverse = 1.0 - step
        weight1 = (3.0 * inverse ** 2 * step)[:, 0]
        weight2 = (3.0 * inverse * step ** 2)[:, 0]
        solution, _residuals, _rank, _singular = np.linalg.lstsq(
            np.column_stack((weight1, weight2)), self.weights()[self.solve], rcond=None)
        first, second = float(solution[0]), float(solution[1])
        # The projection answers the shape of the falloff; the grabbed point is
        # then put exactly under the pointer, which is what makes the piece
        # follow it instead of bending somewhere near it.
        at_grab = (first * 3.0 * (1.0 - self.grab) ** 2 * self.grab
                   + second * 3.0 * (1.0 - self.grab) * self.grab ** 2)
        if abs(at_grab) > 1e-9:
            first, second = first / at_grab, second / at_grab
        moved = (self.handles[0] + first * offset, self.handles[1] + second * offset)
        if self.kind == "straight" and _on_chord((self.base[0], self.base[-1]), moved):
            # A drag along the line leaves the piece the line it was: the ends
            # cannot separate and every control point is still on the chord.
            return {"kind": "straight", "points": None, "handles": (None, None),
                    "handle_types": ("VECTOR", "VECTOR"),
                    "samples": _curve_samples(self.base[[0, -1]])}
        # A handle the drag moved cannot stay a vector one: a vector handle is
        # drawn as the straight line to the other end, whatever it is set to.
        types = tuple("FREE" if value == "VECTOR" else value
                      for value in self.handle_types)
        return {"kind": "bezier", "points": None,
                "handles": (_pair(moved[0]), _pair(moved[1])),
                "handle_types": types,
                "samples": _curve_samples(self.base[[0, -1]], moved[0], moved[1])}

    def _spline_form(self, offset) -> dict:
        """The control points a drag moves, and the curve they describe."""
        weights = _falloff(self.knots[1:-1], self.grab)
        reach = self._influence(weights)
        scale = 1.0 / reach if abs(reach) > 1e-9 else 1.0
        points = self.controls + (weights * scale)[:, None] * offset
        ends = np.vstack((self.base[0], points, self.base[-1]))
        return {"kind": "spline", "points": [_pair(point) for point in points],
                "handles": (_pair(self.handles[0]), _pair(self.handles[1])),
                "handle_types": self.handle_types,
                "samples": _curve_samples(ends, *self.vectors)}

    def _influence(self, weights) -> float:
        """How far a spline moves at the grab when its control points move.

        A spline through control points is linear in their places, so one
        evaluation with the weights themselves as the control values answers how
        much the grabbed point takes: this is the factor the drag divides by, and
        without it that point would land beside the pointer instead of on it.
        """
        values = np.zeros((2, len(weights) + 2), dtype=np.float64)
        values[1, 1:-1] = weights
        samples = cubic_spline_2d_numpy(
            self.knots, values,
            bc0_type="natural" if self.handle_types[0] == "VECTOR" else "constant",
            bc0_d=0.0,
            bcn_type="natural" if self.handle_types[1] == "VECTOR" else "constant",
            bcn_d=0.0,
            sample_count=len(self.base))
        return float(samples[self.grab_index][1])

    def apply(self, offset) -> dict:
        """Write the dragged form into the edge and answer what was written."""
        form = self.form(offset)
        edge = global_data.get_obj_by_uuid(self.edge_uuid, check_uuid=False)
        if edge is None:
            raise GeometryRefused("the edge this drag was started on is gone")
        if form["kind"] == "spline":
            edge.set_curve("spline", points=form["points"],
                           handle1=form["handles"][0], handle2=form["handles"][1],
                           handle1_type=form["handle_types"][0],
                           handle2_type=form["handle_types"][1])
        elif form["kind"] == "bezier":
            edge.set_curve("bezier", handle1=form["handles"][0],
                           handle2=form["handles"][1],
                           handle1_type=form["handle_types"][0],
                           handle2_type=form["handle_types"][1])
        else:
            edge.set_curve("straight", handle1_type="VECTOR", handle2_type="VECTOR")
        return form


# ------------------------------------------------------------------------ fan
