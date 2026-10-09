"""Cut the selected internal line's pattern in two, along that line.

The cut is a boundary rewrite, not a boolean: the line crosses the outline
twice, those crossings split the outline into two arcs, and the stretch of the
line between them closes each arc - one arc read forwards, the other backwards -
so the two new outlines carry the same cut geometry and their areas add up to
the area the source had. A line that crosses the outline anywhere but exactly
twice, and a closed line, are refused with the reason before anything is written.

Everything else follows the geometry: each half inherits the source's fabric,
granularity, grain, collision layer, position and mirror flag, every member of
the source's chain gets its own pair of halves, each other internal line is
placed in the half it lies in (a line the cut crosses becomes one line on each
side, and a closed line the cut would split is refused), and every seam side is
moved to the piece that replaced the edge it named. The cut can be sewn along
through `sew_along_cut`, off by default, which is the operator's own property.
"""

import numpy as np
from bpy.props import BoolProperty
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators
from ..model import pattern_geometry
from ..model.generator import refuse_generated_edit
from ..model.internal_line import InternalLine
from ..model.model_data import owner_pattern, refresh_all_uuids
from ..model.pattern import crossing_check_enabled
from ..model.pattern_geometry import GeometryRefused, MERGE_THRESHOLD_MM, _write_piece
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.console import console
from ..utilities.curve_fit import cumulative_length, point_at_length, polyline_length
from ..utilities.curve_fit import slice_by_arc_length
from ..utilities.node_tree import get_active_node_tree
from ._2d_operator_base import Operator2DBase

class NODE_OT_cut_along_line(Operator2DBase):
    """Cut the selected internal line's pattern in two, along that line

    The command acts on the internal line the selection names: the line crosses
    the outline twice, and the two arcs those crossings leave become two patterns
    that share the cut as their boundary. It is not registered for Blender's
    adjust-last-operation panel: a cut takes the patterns it worked on away, so
    re-running it from that panel is not something it can be asked for again.
    The two things it can do - cut, and cut with a seam along the cut - are two
    entries in the editor's own right-button menu instead, and the whole cut is
    one undo step.
    """

    bl_idname = Operators.CutAlongLine2D
    bl_label = "cut along line"
    bl_options = {'UNDO'}

    sew_along_cut: BoolProperty(
        name="Sew along the cut",
        description="Create a seam between the two halves along the cut",
        default=False,
    )

    def invoke(self, context: Context, event: Event):
        ensure_edit_mode(context, "EDGE", "EDGE_VERTEX")
        return self.execute(context)

    def execute(self, context: Context):
        project = get_active_node_tree(context)
        if project is None:
            return {'CANCELLED'}
        try:
            pattern, line = selected_cut_target(project)
        except pattern_geometry.GeometryRefused as refused:
            return self.refuse(refused)
        if refuse_generated_edit(self, project, pattern):
            return {'CANCELLED'}
        try:
            report = cut_pattern(
                pattern, line, sew_along_cut=bool(self.sew_along_cut),
                check_crossing=crossing_check_enabled(context))
        except pattern_geometry.GeometryRefused as refused:
            return self.refuse(refused)
        self.report({'INFO'}, describe(report))
        return {'FINISHED'}

    def refuse(self, refused) -> dict:
        """Report a refusal as one line: the reason, then the hints."""
        message = refused.reason
        if refused.hints:
            message += " - " + "; ".join(refused.hints)
        self.report({'ERROR'}, message)
        return {'CANCELLED'}


def describe(report) -> str:
    """One line for the info area: what the cut produced."""
    halves = report["halves"]
    message = (f"cut {report['pattern']} into {len(halves)} pattern(s) of "
               f"{report['areas'][0]:.1f} and {report['areas'][1]:.1f} mm^2")
    if report["lines_split"]:
        message += f", {report['lines_split']} internal line(s) split with them"
    elif report["lines_moved"]:
        message += f", {report['lines_moved']} internal line(s) followed their half"
    if report["lines_dropped"]:
        message += (f", {report['lines_dropped']} piece(s) of an internal line were "
                    f"outside the outline")
    if report["dropped_sewings"]:
        message += (f", dropped {len(report['dropped_sewings'])} seam(s): "
                    + ", ".join(report["dropped_sewings"]))
    if report["seam"]:
        message += f", sewn along the cut as {report['seam']}"
    return message


def selected_cut_target(project) -> tuple:
    """The pattern and the internal line the selection names.

    The selection is stored as uuids and the uuid map is not something Blender's
    undo restores, so a selection that does not resolve is retried once after the
    map is rebuilt - which is what a re-run from the redo panel needs.
    """
    uuids = [entry.uuid for entry in project.selected_edges]
    if not uuids:
        raise pattern_geometry.GeometryRefused(
            "no edge is selected", "select an edge of the internal line to cut along")
    edges = pattern_geometry._edges_of_uuids(uuids)
    if len(edges) < len(uuids):
        refresh_all_uuids()
        edges = pattern_geometry._edges_of_uuids(uuids)
    lines = []
    for edge in edges:  # loop: one selected edge per check
        parent = edge.get_parent()
        if isinstance(parent, InternalLine) and parent not in lines:
            lines.append(parent)
    if not lines:
        if not edges:
            # The selection outlived the edges it named - a cut run from the redo
            # panel is the case: the halves the first run wrote took the line's
            # edges with them.
            raise pattern_geometry.GeometryRefused(
                "the selection names edges the model no longer has",
                "select the internal line to cut along again")
        # The refusal is the model's: it knows how to say an outline edge is not
        # a line, and it names the pattern the selection belongs to.
        pattern = owner_pattern(edges[0])
        cut_line_of(pattern, edges[0])
    if len(lines) > 1:
        raise pattern_geometry.GeometryRefused(
            "edges of several internal lines are selected",
            "a cut runs along one line; select the edges of a single line")
    pattern = owner_pattern(lines[0])
    if pattern is None:
        raise pattern_geometry.GeometryRefused(
            "that internal line belongs to no pattern",
            "it was left behind by an edit; it is not part of a pattern any more")
    return pattern, lines[0]

# ------------------------------------------------- the command's own computation

class _Chain:
    """One chain of edges, with the polyline and the arc offset of each of them.

    A cut is measured along a curve, so every edge is read once at equal arc
    steps; reading the chain as a whole is what makes an arc length comparable
    across its edges.
    """

    def __init__(self, sketch, edges, is_loop):
        self.edges = list(edges)
        self.is_loop = bool(is_loop)
        self.points = [np.asarray(sketch.measured_points(edge), dtype=np.float64)
                       for edge in self.edges]
        self.lengths = [polyline_length(points) for points in self.points]
        offsets = np.cumsum([0.0, *self.lengths])
        self.offsets = offsets[:-1]
        self.total = float(offsets[-1]) if self.edges else 0.0

    def arc_of(self, index, t) -> float:
        """The arc length from the chain's start to a place on one of its edges."""
        return float(self.offsets[index]) + float(t) * self.lengths[index]

    def place(self, arc) -> tuple:
        """``(edge index, arc within that edge)`` for a chain arc length.

        A place on a vertex answers with the edge that ends there, so a walk in
        the chain's own order carries on from the next edge and no zero-length
        piece is written for it.
        """
        if not self.edges or self.total <= 0.0:
            return 0, 0.0
        arc = self.wrap(arc)
        for index, offset in enumerate(self.offsets):
            if arc <= float(offset) + self.lengths[index] + 1e-9:
                return index, min(max(arc - float(offset), 0.0), self.lengths[index])
        return len(self.edges) - 1, self.lengths[-1]

    def wrap(self, arc) -> float:
        """One arc length on this chain, brought inside it."""
        arc = float(arc)
        if self.is_loop and self.total > 0.0:
            arc -= self.total * np.floor(arc / self.total)
        return min(max(arc, 0.0), self.total)

    def polygon(self) -> list:
        """The chain's own points, for the tests that ask what holds a point."""
        if not self.edges:
            return []
        joined = self.points[0]
        for points in self.points[1:]:  # loop: one joint per further edge
            joined = np.vstack((joined, points[1:]))
        return [(float(point[0]), float(point[1])) for point in joined]


def _segment(chain, index, start, end, reverse=False) -> dict:
    """One piece of a chain, read the way it is walked.

    ``start`` and ``end`` are arc lengths on the edge itself, lower first;
    `reverse` says the piece is walked the other way, which is what the half on
    the far side of a cut does with the cut they share.
    """
    points = _cleaned(slice_by_arc_length(chain.points[index], float(start), float(end)))
    if reverse:
        points = points[::-1]
    return {"edge": chain.edges[index], "start": float(start), "end": float(end),
            "length": chain.lengths[index], "reverse": bool(reverse),
            "points": np.asarray(points, dtype=np.float64)}


def _cleaned(points) -> np.ndarray:
    """A piece's points with the repeats at its ends dropped.

    Reading a place a hair past a sample gives the sample and then the place, and
    a step that short makes the crossing test report the outline as crossing
    itself.
    """
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 2:
        return points
    keep = [0]
    for index in range(1, len(points)):  # loop: one point per step
        if float(np.linalg.norm(points[index] - points[keep[-1]])) > 1e-3:
            keep.append(index)
    return points[keep]


def _turned(segments) -> list:
    """The same run read the other way: the pieces in reverse, each turned."""
    # The points are copied, not reversed in place: the two halves share the
    # pieces of the cut, and sealing one half's joints must not move the other's.
    return [dict(segment, reverse=not segment["reverse"],
                 points=np.ascontiguousarray(segment["points"][::-1]))
            for segment in reversed(segments)]


def _sealed(segments) -> list:
    """One run whose pieces meet exactly, piece by piece.

    The pieces either side of a joint are read from two different curves - the
    outline and the cut - so their readings of the crossing they share differ by
    a fraction of a millimetre. Averaging the pair gives both halves the same
    point at the same crossing.
    """
    for position, segment in enumerate(segments):  # loop: one joint per piece
        following = segments[(position + 1) % len(segments)]
        joint = 0.5 * (segment["points"][-1] + following["points"][0])
        segment["points"][-1] = joint
        following["points"][0] = joint
    return segments


def _span(chain, arc_from, arc_to) -> list:
    """The pieces between two arc lengths of a chain, walked forwards.

    The walk carries the distance it still has to cover rather than stopping on
    the edge it ends on, so a span that starts and ends on one edge - the long
    way round a loop - comes out as the two pieces it is.
    """
    count = len(chain.edges)
    if count == 0 or chain.total <= 0.0:
        return []
    if chain.is_loop:
        travelled = (float(arc_to) - float(arc_from)) % chain.total
        if travelled <= 1e-12:
            travelled = chain.total
    else:
        travelled = max(float(arc_to) - float(arc_from), 0.0)
    index, local = chain.place(arc_from)
    segments, guard = [], 0
    while travelled > 1e-9 and guard < count * 2 + 4:
        guard += 1
        room = chain.lengths[index] - local
        if room <= 1e-9:  # the place sits on this edge's far end
            index, local = (index + 1) % count, 0.0
            continue
        step = min(room, travelled)
        segments.append(_segment(chain, index, local, local + step))
        travelled -= step
        index, local = (index + 1) % count, 0.0
    return segments


def _crossings(chain_a, chain_b) -> list:
    """Where two chains cross, as ``(arc along a, arc along b)``.

    What each section contributes is the edge's own points minus the end it
    shares with the next piece, which is the layout the mesh path hands the
    engine, so a returned ``(section, t)`` reads the way the engine means it.
    The engine answers with the arcs as fractions, turned into lengths here.
    """
    runs, sizes, section_points = [], [], []
    for chain in (chain_a, chain_b):
        size = 0
        for index, points in enumerate(chain.points):
            last = not chain.is_loop and index + 1 == len(chain.edges)
            run = points if last else points[:-1]
            runs.append(run)
            section_points.append(len(run))
            size += len(run)
        sizes.append(size)
    from Qianyi_DP import pattern_helper
    found = pattern_helper.get_all_intersections(
        np.concatenate(runs).astype(np.float32),
        np.array(sizes, dtype=np.int32),
        np.array([int(chain_a.is_loop), int(chain_b.is_loop)], dtype=np.int8),
        np.array([len(chain_a.edges), len(chain_b.edges)], dtype=np.int32),
        np.array(section_points, dtype=np.int32))
    places = []
    for entry in found:  # loop: one crossing per answer
        if int(entry["curve_a"]) == 0:
            places.append((chain_a.arc_of(int(entry["section_a"]), float(entry["t_a"])),
                           chain_b.arc_of(int(entry["section_b"]), float(entry["t_b"]))))
        else:
            places.append((chain_a.arc_of(int(entry["section_b"]), float(entry["t_b"])),
                           chain_b.arc_of(int(entry["section_a"]), float(entry["t_a"]))))
    return places


def _inside(polygon, point) -> bool:
    """Whether a point is inside a closed polygon, by the even-odd rule."""
    if len(polygon) < 3:
        return False
    x, y = float(point[0]), float(point[1])
    inside = False
    x1, y1 = polygon[-1]
    for x2, y2 in polygon:  # loop: one edge of the polygon per crossing test
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
        x1, y1 = x2, y2
    return inside


def _area(polygon) -> float:
    """The signed area a closed polygon encloses."""
    if len(polygon) < 3:
        return 0.0
    points = np.asarray(polygon, dtype=np.float64)
    x, y = points[:, 0], points[:, 1]
    index = np.arange(len(points))
    following = (index + 1) % len(points)
    return float(0.5 * np.sum(x[index] * y[following] - x[following] * y[index]))


def _polygon(segments) -> list:
    """One run's points as a closed polygon, for the tests on it.

    A run closes on the point its first piece started from, which is dropped from
    the end: a polygon that names its first point twice has a zero-length edge,
    and the crossing test reports that as a crossing.
    """
    if not segments:
        return []
    joined = segments[0]["points"]
    for segment in segments[1:]:  # loop: one joint per further piece
        joined = np.vstack((joined, segment["points"][1:]))
    if len(joined) > 1 and np.allclose(joined[0], joined[-1], atol=1e-9):
        joined = joined[:-1]
    return [(float(point[0]), float(point[1])) for point in joined]


def cut_line_of(pattern, obj):
    """The internal line a selection names, or a refusal that says what it names.

    A cut runs along an internal line, so an outline edge is refused by name: the
    outline is what a cut ends on, and it is already a boundary.
    """
    from ..model.internal_line import InternalLine

    if pattern is None:
        raise GeometryRefused("that edge belongs to no pattern",
                              "it was left behind by an edit; select the line again")
    parent = obj.get_parent() if hasattr(obj, "get_parent") else None
    if isinstance(parent, InternalLine):
        return parent
    if parent is not None:
        raise GeometryRefused(f"the selected edge is an outline edge of {pattern.name!r}",
                "a cut runs along an internal line, and its ends land on the outline")
    raise GeometryRefused("that selection is not an edge of a pattern",
            "select an edge of the internal line to cut along")


def plan_cut(pattern, line, *, check_crossing=True) -> dict:
    """Work out the two halves without writing anything.

    Everything a cut can refuse is refused here, before the first write: how many
    times the line crosses the outline, the two arcs those crossings leave, the
    half each other internal line would go to, and whether either half would
    cross itself.
    """
    from ..model.generator import generation_lock

    sketch = pattern.require_sketch()
    if line is None:
        raise GeometryRefused("no internal line is selected", "select the line to cut along")
    if line.is_loop:
        raise GeometryRefused("this internal line is closed",
                "a closed line inside the pattern is already a hole, and the cut "
                "does not change it")
    locked = generation_lock(pattern.project, pattern)
    if locked is not None:
        raise GeometryRefused(locked)
    if len(sketch.edges) < 3:
        raise GeometryRefused(f"{pattern.name!r} has no outline to cut",
                "a cut needs an outline the line can cross twice")
    # The stage this plan reads is the geometry as it is now: what an internal
    # line was cut into where it crosses the outline is what the pieces below
    # are taken from.
    sketch.update()
    outline = _Chain(sketch, sketch.edges, True)
    cut = _Chain(sketch, line.edges, False)
    if cut.total <= MERGE_THRESHOLD_MM:
        raise GeometryRefused("this internal line has no length",
                "a cut runs along a line with two ends on the outline")

    places = sorted(_crossings(outline, cut), key=lambda place: place[1])
    # Two crossings on the line at almost the same place are one crossing: a line
    # that grazes the outline at a vertex reports two.
    distinct = []
    for place in places:  # loop: one crossing per answer
        if distinct and abs(place[1] - distinct[-1][1]) <= MERGE_THRESHOLD_MM:
            continue
        distinct.append(place)
    places = distinct
    if len(places) == 0:
        raise GeometryRefused(f"this line does not cross the outline of {pattern.name!r}",
                "a cut runs from one side of the outline to the other")
    if len(places) == 1:
        raise GeometryRefused(f"this line crosses the outline of {pattern.name!r} once",
                "a cut needs exactly two crossings, one at each of its ends")
    if len(places) > 2:
        raise GeometryRefused(f"this line crosses the outline of {pattern.name!r} {len(places)} times",
                "a cut needs exactly two crossings")

    first, second = places
    cut_span = _span(cut, first[1], second[1])
    if not cut_span:
        raise GeometryRefused("the stretch of this line between its two crossings is empty")
    if not _inside(outline.polygon(), _middle_of(cut_span)):
        raise GeometryRefused(f"this line touches the outline of {pattern.name!r} rather than "
                f"crossing it",
                "a cut runs through the pattern between its two crossings")

    arc_a = _span(outline, first[0], second[0])
    arc_b = _span(outline, second[0], first[0])
    if not arc_a or not arc_b:
        raise GeometryRefused("the two crossings sit on top of each other",
                "a cut needs two places on the outline, with material between them")
    # An outline that runs clockwise has its material on the other side of the
    # walk, so the two loops are closed the other way round; either way the
    # halves come out counter-clockwise, and no existing point order is touched.
    clockwise = _area(outline.polygon()) < 0.0
    halves = {"a": {"segments": arc_a + (_turned(cut_span) if not clockwise
                                         else list(cut_span))},
              "b": {"segments": arc_b + (list(cut_span) if not clockwise
                                         else _turned(cut_span))}}
    for half in halves.values():  # loop: one sealed run per half
        _sealed(half["segments"])
    polygons = {key: _polygon(half["segments"]) for key, half in halves.items()}
    areas = {key: _area(polygon) for key, polygon in polygons.items()}
    if areas["a"] <= 0.0 or areas["b"] <= 0.0:
        raise GeometryRefused(f"cutting {pattern.name!r} here would leave a half with no area",
                "a cut needs material on both sides of it")
    if check_crossing:
        from ..model.pattern import boundary_self_intersection
        for key in ("a", "b"):
            crossed, _where = boundary_self_intersection(np.asarray(polygons[key]))
            if crossed:
                raise GeometryRefused(f"cutting {pattern.name!r} here would leave an outline that "
                        f"crosses itself",
                        "move the line, or turn Check Self-Intersection off to write "
                        "it anyway")
    for half in halves.values():
        half["lines"] = []
        # The pieces of the cut the two halves share, so each half can name the
        # run of its own outline that the cut wrote.
        half["cut"] = cut_span
    moved, split, dropped = _assign_lines(sketch, line, halves, polygons, outline,
                                          (first[1], second[1]))
    return {"pattern": pattern, "sketch": sketch, "line": line, "cut": cut_span,
            "outline": outline, "halves": halves, "polygons": polygons,
            "areas": areas, "moved": moved, "split": split, "dropped": dropped}


def _middle_of(segments) -> np.ndarray:
    """A point about half way along a run of pieces, for the tests on it."""
    lengths = [polyline_length(segment["points"]) for segment in segments]
    half = sum(lengths) / 2.0
    for segment, length in zip(segments, lengths):
        if half <= length + 1e-9:
            return point_at_length(segment["points"], half)
        half -= length
    return np.asarray(segments[-1]["points"][-1], dtype=np.float64)


def _line_spans(chain, splits) -> list:
    """One chain cut at these arc lengths, as the runs covering the whole of it.

    Each run is a list of pieces, because a split lands in the middle of an edge
    often enough that a run is not one edge's worth of curve. A closed chain is
    cut into the pieces between its splits, wrapping round; an open one is cut
    from its start to its end, and the pieces beyond its first and last split are
    parts of it too.
    """
    if not chain.edges or chain.total <= 0.0:
        return []
    cuts = sorted({chain.wrap(arc) for arc in splits
                   if 1e-9 < chain.place(arc)[1] < chain.lengths[chain.place(arc)[0]] - 1e-9})
    if not chain.is_loop:
        bounds = [0.0, *cuts, chain.total]
        return [_span(chain, bounds[position], bounds[position + 1])
                for position in range(len(bounds) - 1)]
    if not cuts:
        return [_span(chain, 0.0, chain.total)]
    spans = []
    for position, arc in enumerate(cuts):
        following = cuts[(position + 1) % len(cuts)]
        if position + 1 == len(cuts):
            following += chain.total
        spans.append(_span(chain, arc, following))
    return spans


def _half_of(polygons, source, point):
    """Which half holds a point: ``None`` when neither does."""
    inside = {key: _inside(polygons[key], point) for key in polygons}
    if inside.get("a") and inside.get("b"):
        raise GeometryRefused("an internal line lies along this cut rather than on one side of it",
                "move the line, or remove it first")
    for key in ("a", "b"):
        if inside.get(key):
            return key
    if _inside(source, point):
        raise GeometryRefused("an internal line cannot be placed on either side of this cut",
                "the cut and the outline meet in a way the editor cannot follow")
    return None


def _assign_lines(sketch, cut_line, halves, polygons, outline, interval) -> tuple:
    """Place every other internal line of the sketch in the half that holds it.

    Each line is cut at its crossings with the outline and with the stretch of
    the cut that becomes the new boundary, and every piece is placed by its own
    middle, so a line the cut crosses comes out as one line on each side. A piece
    outside the outline is dropped, and a closed line the cut would split is
    refused: its arcs would end on the new boundary, where an internal line
    cannot keep them.
    """
    cut = _Chain(sketch, cut_line.edges, False)
    moved, split, dropped = 0, 0, 0
    for line in sketch.internal_lines:  # loop: one further line per pass
        if line.global_uuid == cut_line.global_uuid or len(line.edges) == 0:
            continue
        chain = _Chain(sketch, line.edges, line.is_loop)
        if chain.total <= 0.0:
            continue
        # The split is at the arc on this line, not at the arc the same crossing
        # sits at on the other chain, and only where the line crosses the
        # stretch of the cut that becomes the new boundary.
        splits = [on_line for _on_outline, on_line in _crossings(outline, chain)]
        splits.extend(on_line for on_cut, on_line in _crossings(cut, chain)
                      if interval[0] - 1e-9 <= on_cut <= interval[1] + 1e-9)
        runs, current = [], None
        for span in _line_spans(chain, splits):  # loop: one run per split piece
            side = _half_of(polygons, outline.polygon(), _middle_of(span))
            if side is None:
                dropped += 1
                current = None
                continue
            if current is not None and current["side"] == side:
                current["segments"].extend(span)
                continue
            current = {"side": side, "segments": list(span), "line": line}
            runs.append(current)
        # A closed line's first and last run are neighbours across its start.
        if line.is_loop and len(runs) > 1 and runs[0]["side"] == runs[-1]["side"]:
            runs[0]["segments"] = runs[-1]["segments"] + runs[0]["segments"]
            runs.pop()
        if line.is_loop and len(runs) > 1:
            raise GeometryRefused(f"the closed internal line {line.name or '(unnamed)'} is split by "
                    f"this cut",
                    "an arc of a hole would end on the new boundary, which makes it "
                    "part of the outline; move the cut, or remove the line first")
        if not runs:
            dropped += 1
            continue
        for run in runs:  # loop: one line written per half this line reaches
            loop = bool(line.is_loop and len(runs) == 1)
            halves[run["side"]]["lines"].append(
                {"segments": run["segments"], "is_loop": loop,
                 "is_hole": bool(line.is_hole) if loop else False, "source": line})
        if len(runs) == 1:
            moved += 1
        else:
            split += 1
    return moved, split, dropped


# --------------------------------------------------------------- the write


def _pair(point) -> tuple:
    return (float(point[0]), float(point[1]))


def _write_segment(edge, segment) -> None:
    """Write one piece: a whole edge as it is drawn, a piece as it fits."""
    source = segment["edge"]
    whole = (segment["start"] <= 1e-9
             and segment["end"] >= segment["length"] - 1e-9)
    if whole:
        _copy_curve(edge, source, segment["reverse"])
    else:
        _write_piece(edge, segment["points"])


def _copy_curve(target, source, reverse=False) -> None:
    """Write one edge the way another edge is drawn, in either direction.

    A straight edge and a Bezier carry over exactly, and so does a spline: read
    the other way round, its points reverse and its two handles swap. That is
    what keeps a piece that reproduces a circle exactly a circle, which the
    fitted pieces of a curve could not promise.
    """
    points = [(float(point.co[0]), float(point.co[1])) for point in source.spline_points]
    handle1 = source.handle1.co[:] if len(source.handles) > 0 else (0.0, 0.0)
    handle2 = source.handle2.co[:] if len(source.handles) > 1 else (0.0, 0.0)
    type1, type2 = source.handle1_type, source.handle2_type
    if reverse:
        points.reverse()
        handle1, handle2 = handle2, handle1
        type1, type2 = type2, type1
    target.set_curve(source.kind, handle1, handle2, points, type1, type2)


def _write_run(sketch, segments, edges, is_loop) -> list:
    """Write one run of pieces into a chain of edges and return them.

    A closed run ends on the point its first piece started from, so the two
    halves of a cut share one point at each end of the cut rather than two that
    happen to be close; an open run - an internal line the cut shortened - ends
    on a point of its own.
    """
    start = sketch.add_vertex(_pair(segments[0]["points"][0]))
    index, written = start, []
    for position, segment in enumerate(segments):  # loop: one edge per piece
        closing = position + 1 == len(segments)
        if closing and is_loop:
            target_index = start
        else:
            target_index = sketch.add_vertex(_pair(segment["points"][-1]))
        edge = sketch.own(edges.add())
        edge.vertex_index[0] = index
        edge.vertex_index[1] = target_index
        _write_segment(edge, segment)
        written.append(edge)
        index = target_index
    return written


def _record(tables, segments, edges, half) -> None:
    """Remember which written edge each piece of a source edge became.

    The span is kept as fractions of the source edge, which is what a seam side
    stores as its position, so a side finds the piece that replaced its edge by
    reading the same number.
    """
    for segment, edge in zip(segments, edges):  # loop: one written edge per piece
        length = segment["length"]
        if length <= 0.0:
            continue
        tables.append({"source": segment["edge"],
                       "source_uuid": int(segment["edge"].global_uuid),
                       "start": segment["start"] / length,
                       "end": segment["end"] / length,
                       "target": edge, "half": half})


def _build_half(project, half, tables, key) -> dict:
    """Build one half's Sketch from its plan, and remember its pieces."""
    sketch = project.add_sketch()
    outline = _write_run(sketch, half["segments"], sketch.edges, True)
    sketch.refresh_collection_uuid(sketch.edges)
    _record(tables, half["segments"], outline, key)
    lines = []
    for run in half["lines"]:  # loop: one further line per pass
        line = sketch.own(sketch.internal_lines.add())
        line.is_loop = bool(run["is_loop"])
        line.is_hole = bool(run["is_hole"])
        line.name = run["source"].name
        edges = _write_run(sketch, run["segments"], line.edges, run["is_loop"])
        sketch.refresh_collection_uuid(line.edges)
        _record(tables, run["segments"], edges, key)
        lines.append(line)
    sketch.initialize()
    sketch.update()
    cut_edges = outline[len(outline) - len(half["cut"]):]
    return {"sketch": sketch, "edges": outline, "lines": lines,
            "cut_uuids": [int(edge.global_uuid) for edge in cut_edges]}


def _inherit(new_pattern, source, suffix) -> None:
    """Give a half everything of its source that is not geometry."""
    from ..model.qianyi_project import get_unique_name

    project = new_pattern.id_data
    new_pattern.name = get_unique_name(project.patterns, f"{source.name}_{suffix}")
    new_pattern.anchor = source.anchor[:]
    new_pattern.rotation = source.rotation
    new_pattern.grain_dir = source.grain_dir
    new_pattern.collision_layer = source.collision_layer
    new_pattern.fabric_uuid = source.fabric_uuid
    new_pattern.granularity = source.granularity
    new_pattern.is_mirror = bool(source.is_mirror)


def _find_piece(tables, uuid_value, pos):
    """The piece of a cut source edge a stored position lands on."""
    candidates = [piece for piece in tables if piece["source_uuid"] == int(uuid_value)]
    if not candidates:
        return None
    position = float(pos)
    for index, piece in enumerate(candidates):  # loop: one piece per test
        if piece["start"] - 1e-9 <= position < piece["end"] - 1e-9:
            return piece
        if index + 1 == len(candidates) and position <= piece["end"] + 1e-9:
            return piece
    return candidates[-1]


def _repoint(piece, pos) -> float:
    """Where a stored position sits on the edge that replaced its edge."""
    points = np.asarray(piece["source"].render_points, dtype=np.float64)
    lengths = cumulative_length(points)
    if lengths[-1] <= 0.0:
        return 0.0
    point = point_at_length(points, float(pos) * float(lengths[-1]))
    target = np.asarray(piece["target"].render_points, dtype=np.float64)
    return _fraction_at(target, point)


def _fraction_at(points, point) -> float:
    """Where a point projects onto a polyline, as a fraction of its length.

    The projection is onto the segments rather than onto their ends: a straight
    edge carries two samples however long it is, so the nearest sample would put
    every position on one of its ends.
    """
    lengths = cumulative_length(points)
    if len(points) < 2 or lengths[-1] <= 0.0:
        return 0.0
    best, best_distance = 0.0, None
    for index in range(len(points) - 1):  # loop: one segment per projection
        start, end = points[index], points[index + 1]
        segment = end - start
        span = float(np.dot(segment, segment))
        weight = 0.0 if span <= 0.0 else float(
            min(max(float(np.dot(point - start, segment)) / span, 0.0), 1.0))
        distance = float(np.linalg.norm(point - (start + weight * segment)))
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best = float(lengths[index] + weight * (lengths[index + 1] - lengths[index]))
    return best / float(lengths[-1])


def _move_sewings(project, made, tables) -> tuple:
    """Move every seam that named a replaced pattern onto the half that holds it.

    Returns the names of the seams that went, and the patterns that were moved
    onto - the ones the linking run has to be told about. A seam whose two ends
    landed in different halves is dropped: one side spans one chain, so a side
    that would need two patterns cannot be written, and the report says which
    seam it was rather than leaving it to fail later.
    """
    gone, drop_at, touched = [], [], []
    for index, sewing in enumerate(project.sewings):  # loop: one seam per pass
        placements, doomed = [], False
        for side in sewing.sides:
            pattern = side.pattern
            if pattern is None or pattern.global_uuid not in made:
                placements.append(None)
                continue
            runs, keys, keep = [], set(), True
            # loop: one drawn run of that side per step
            for span in side.spans:
                placed = [_find_piece(tables, span.line1_uuid, span.pos1),
                          _find_piece(tables, span.line2_uuid, span.pos2)]
                landed = {piece["half"] for piece in placed if piece is not None}
                if len(landed) != 1 or any(piece is None for piece in placed):
                    keep = False
                    break
                keys |= landed
                runs.append((placed, _repoint(placed[0], span.pos1),
                             _repoint(placed[1], span.pos2)))
            if not keep or len(keys) != 1 or not runs:
                # A run that lands in two halves, or runs that land in different
                # ones: a side is on one pattern, so the seam cannot be written
                # that way and goes.
                doomed = True
                placements.append(None)
                continue
            # Everything that can go wrong - a piece that is not there, a place
            # that cannot be read - is done before the first write, so the loop
            # that writes cannot leave a seam half moved.
            placements.append((runs, made[int(side.pattern_uuid)][keys.pop()]))
        if doomed:
            sides = [side.pattern.name for side in sewing.sides
                     if side.pattern is not None]
            label = sewing.name or f"seam {index}"
            gone.append(f"{label} ({' - '.join(sides)})")
            drop_at.append(index)
            continue
        for side, placement in zip(sewing.sides, placements):
            if placement is None:
                continue
            runs, target_uuid = placement
            for span, (placed, pos1, pos2) in zip(side.spans, runs):
                # loop: one drawn run of that side per step
                span.line1_uuid = int(placed[0]["target"].global_uuid)
                span.pos1 = pos1
                span.line2_uuid = int(placed[1]["target"].global_uuid)
                span.pos2 = pos2
            side.pattern_uuid = target_uuid
            touched.append(target_uuid)
    for index in sorted(drop_at, reverse=True):
        project.sewings[index].forget_identity()
        project.sewings.remove(index)
    if drop_at:
        project.refresh_collection_uuid(project.sewings)
        project.selected_sewings.clear()
    return gone, touched


def _sew_along(project, made, built, plan) -> list:
    """Sew the two halves of a cut together along the cut, one seam per member.

    The cut boundary of each half is the run of edges the cut wrote, and the two
    runs are the same geometry read one way in each half. Each seam starts both
    of its sides at the same end of the cut - the end the first crossing left on
    the outline - so the cut closes without twisting.
    """
    count = len(plan["cut"])
    if count == 0:
        return []
    names = []
    for pair in made.values():  # loop: one seam per member of the chain
        # Read back by identity: the source patterns went, and removing them
        # retired the wrappers this command was holding.
        first_pattern = global_data.get_obj_by_uuid(pair["a"], check_uuid=False)
        second_pattern = global_data.get_obj_by_uuid(pair["b"], check_uuid=False)
        first_half = [global_data.get_obj_by_uuid(uuid_value, check_uuid=False)
                      for uuid_value in built["a"]["cut_uuids"]]
        second_half = [global_data.get_obj_by_uuid(uuid_value, check_uuid=False)
                       for uuid_value in built["b"]["cut_uuids"]]
        if None in first_half or None in second_half:
            return names
        if len(first_half) != count or len(second_half) != count:
            return names
        # A pattern that no seam reaches has not built its copy of the stage yet,
        # and a side is stored as a place on that copy; the two halves are about
        # to be reached by this seam, so their copies are built first.
        first_pattern.ensure_sections()
        second_pattern.ensure_sections()
        # The first half reads the cut backwards, so its own run ends where the
        # second half's begins: both sides are walked from that same end.
        sewing = project.add_sewing(first_half[-1], 1.0, first_half[0], 0.0, True,
                                    second_half[0], 0.0, second_half[-1], 1.0, False,
                                    pattern1=first_pattern, pattern2=second_pattern)
        if sewing is None:
            console.warning("cut along line: the seam along the cut was refused:",
                            project.last_sewing_error)
            return names
        # A seam is named by the two patterns it joins: the editor's own seams
        # have no name of their own, and the report has to name this one.
        names.append(f"{first_pattern.name} - {second_pattern.name}")
    return names


def _take_back(project, uuids) -> None:
    """Remove the halves a failed cut had written; the sources are still there."""
    entries = [global_data.get_obj_by_uuid(uuid_value, check_uuid=False)
               for uuid_value in uuids]
    entries = [entry for entry in entries if entry is not None]
    if entries:
        project.remove_patterns(entries)


def cut_pattern(pattern, line, *, sew_along_cut=False, check_crossing=True) -> dict:
    """Cut `pattern` along `line` and return what happened.

    Both halves are built from one plan, so a refusal leaves the project as it
    was: nothing is written until the plan has been made. Every member of the
    pattern's chain is replaced by its own pair of halves, so the two halves come
    out as two chains of the length the source chain had.
    """
    project = pattern.project
    plan = plan_cut(pattern, line, check_crossing=check_crossing)
    # The name is read before the source patterns go: a removed pattern's wrapper
    # answers garbage, and everything below - the report, the console line and the
    # names of the halves - is written after they are gone.
    source_name = pattern.name
    members = pattern.sketch_members()
    tables, built = [], {}
    for key in ("a", "b"):
        built[key] = _build_half(project, plan["halves"][key], tables, key)
    made, uuids = {}, []
    try:
        for member in members:  # loop: one pair of patterns per member of the chain
            pair = {}
            for key in ("a", "b"):
                new_pattern = project.add_pattern(sketch=built[key]["sketch"])
                _inherit(new_pattern, member, key)
                new_pattern.initialize()
                new_pattern.calc_bbox()
                new_pattern.mark_geometry_changed()
                new_pattern.generate_mesh()
                pair[key] = new_pattern.global_uuid
                uuids.append(new_pattern.global_uuid)
            made[member.global_uuid] = pair
        gone, touched = _move_sewings(project, made, tables)
    except Exception:
        # Everything that can fail runs before the source patterns go, so the
        # halves written so far are taken back and the run leaves the project as
        # it found it - a chain half cut is worse than a cut that did not happen.
        _take_back(project, uuids)
        raise
    project.remove_patterns(members)
    # What was selected to run this is gone with the sources: leaving the
    # selection naming it would make the next click on any tool read a selection
    # of removed edges first.
    project.clear_selected_objects_by_mode("EDGE")
    project.clear_edge_finder()
    patterns = [global_data.get_obj_by_uuid(uuid_value, check_uuid=False)
                for uuid_value in uuids]
    patterns = [entry for entry in patterns if entry is not None]
    seam = None
    if sew_along_cut:
        names = _sew_along(project, made, built, plan)
        seam = names[0] if names else None
    if touched or gone or seam is not None:
        project.sewings_changed(patterns)
    for entry in patterns:  # loop: one relink mark per half
        entry.need_sewing_update = True
    console.info(f"[cut] {source_name}: halves of {plan['areas']['a']:.1f} and "
                 f"{plan['areas']['b']:.1f} mm^2 out of {len(members)} member(s), "
                 f"{plan['moved']} internal line(s) placed, {plan['split']} split, "
                 f"{plan['dropped']} dropped")
    return {"action": "cut_along_line", "pattern": source_name,
            "halves": [entry.name for entry in patterns], "areas": list(plan["areas"].values()),
            "members": len(members), "dropped_sewings": gone, "seam": seam,
            "lines_moved": plan["moved"], "lines_split": plan["split"],
            "lines_dropped": plan["dropped"], "patterns": patterns}

register, unregister = register_classes_factory((NODE_OT_cut_along_line,))
