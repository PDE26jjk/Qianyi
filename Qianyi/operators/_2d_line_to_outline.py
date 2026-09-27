"""Put both ends of the selected internal line on the outline.

`EXTEND` is for an end that stops short inside the pattern: it is moved out to the
nearest point of the outline, so a dart or a fold line that was drawn inside now
spans the pattern. `TRIM` cuts the line back where it leaves the pattern. An end
that lies outside is cut back in either mode - there is nothing to extend there -
so the two modes differ only at the ends that are inside.

The line is a chain, and the two ends ask for a span of it: what lies before the
span's start and after its end is outside the pattern and goes. The pieces that
stay keep their own identity, so a seam that named one of them still names it; a
seam on a piece an end was cut into is re-aimed at the point of the new piece
closest to where it was; and a seam on a piece that went is dropped and named.
The points of the pattern are the line's own: the span's two ends are written
onto the line's own end points, and the points of the pieces that went leave the
pool with them.
"""

import numpy as np
from bpy.props import EnumProperty
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model import pattern_geometry
from ..model.generator import refuse_generated_edit
from ..model.internal_line import InternalLine
from ..model.model_data import refresh_all_uuids
from ..model.pattern_geometry import GeometryRefused
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.curve_fit import slice_by_arc_length
from ..utilities.node_tree import get_active_node_tree
from ._2d_elements_delete import _shift_index, _vertex_is_orphan
from ._2d_operator_base import Operator2DBase, select_edges


mode_property = EnumProperty(
    name="Mode",
    description="What happens at an end of the line",
    items=[
        ("EXTEND", "Extend", "Move an end that stops short out to the outline"),
        ("TRIM", "Trim", "Cut the line back to the outline"),
    ],
    default="EXTEND",
)
# The shortest span worth writing: below it the line has been cut away to nothing.
SPAN_EPSILON_MM = 1e-6


class NODE_OT_line_to_outline(Operator2DBase):
    """Trim or extend the selected internal line to the outline."""

    bl_idname = Operators.LineToOutline2D
    bl_label = "line to outline"
    bl_options = {'REGISTER', 'UNDO'}

    mode: mode_property

    def draw(self, context: Context):
        """The adjust-last-operation panel."""
        self.layout.prop(self, "mode")

    def invoke(self, context: Context, event: Event):
        ensure_edit_mode(context, "EDGE", "EDGE_VERTEX")
        return self.execute(context)

    def execute(self, context: Context):
        project = get_active_node_tree(context)
        if project is None:
            return {'CANCELLED'}
        try:
            line, pattern = selected_line(project)
            if refuse_generated_edit(self, project, pattern):
                return {'CANCELLED'}
            report = fit_line(pattern, line, mode=self.mode)
        except pattern_geometry.GeometryRefused as refused:
            return self.refuse(refused)
        select_edges(project, report["edges"])
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
    """One line for the info area: what happened at the line's two ends."""
    message = (f"put both ends of the internal line on the outline of "
               f"{report['pattern']} ({report['mode'].lower()})")
    moved = [f"{value:.1f} mm" for value in report["moved"] if value > 0.001]
    if moved:
        message += ", moving them " + " and ".join(moved)
    if report["dropped_pieces"]:
        message += f", {report['dropped_pieces']} piece(s) of it went"
    if report["dropped_sewings"]:
        message += f", dropped {report['dropped_sewings']} seam(s)"
    if report["sewings_moved"]:
        message += f", {report['sewings_moved']} seam end(s) followed"
    return message


def selected_line(project) -> tuple:
    """The internal line the selection names, and the pattern it lives in.

    The selection is stored as uuids and the uuid map is not something Blender's
    undo restores, so a selection that does not resolve is retried once after the
    map is rebuilt - which is what a re-run from the redo panel needs.
    """
    uuids = [entry.uuid for entry in project.selected_edges]
    if not uuids:
        raise GeometryRefused("no edge is selected",
                              "select the internal line to fit to the outline")
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
        raise GeometryRefused(
            "the selection names no internal line",
            "this fits a line to the outline; an outline edge is already on it")
    if len(lines) > 1:
        raise GeometryRefused("edges of several internal lines are selected",
                              "fit one line to the outline at a time")
    line = lines[0]
    if line.is_loop:
        raise GeometryRefused("that internal line is closed",
                              "a closed line has no ends to put on the outline")
    if line.sketch is None or line.sketch.owner is None:
        raise GeometryRefused("that internal line belongs to no pattern",
                              "it was left behind by an edit")
    return line, line.sketch.owner


# ------------------------------------------------------- the command's own computation

def piece_points(edge) -> np.ndarray:
    """One piece's own drawn points, rebuilt when the last edit left them stale."""
    sketch = edge.sketch
    if sketch is not None and edge.render_points is None:
        sketch.update()
    points = np.asarray(edge.render_points, dtype=np.float64)
    if points.ndim != 2 or len(points) < 2:
        raise GeometryRefused("a piece of that line has no shape to fit",
                              "rebuild the pattern's geometry first")
    return points


def walked_pieces(line) -> list:
    """The line's pieces, each read the way the line is walked."""
    return [piece_points(line.edges[index]) for index in range(len(line.edges))]


def piece_length(piece) -> float:
    return float(np.sum(np.linalg.norm(np.diff(piece, axis=0), axis=1)))


def joined(pieces) -> tuple:
    """The chain's points as one polyline, and the arc length at each of them."""
    points = np.vstack([pieces[0], *[piece[1:] for piece in pieces[1:]]])
    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return points, np.concatenate(([0.0], np.cumsum(steps)))


def piece_of(pieces, arc) -> tuple:
    """``(piece index, arc within it)`` for one arc length along the chain."""
    walked = 0.0
    for index, piece in enumerate(pieces):  # loop: one piece per check
        length = piece_length(piece)
        if arc <= walked + length + 1e-9:
            return index, min(max(arc - walked, 0.0), length)
        walked += length
    last = len(pieces) - 1
    return last, piece_length(pieces[last])


def _segment_crossings(starts, steps, polygon):
    """Where one step of the line crosses one step of the outline, if it does."""
    other_start, other_step = polygon, np.roll(polygon, -1, axis=0) - polygon
    delta = other_start[None, :, :] - starts[:, None, :]
    denominator = (steps[:, None, 0] * other_step[None, :, 1]
                   - steps[:, None, 1] * other_step[None, :, 0])
    parallel = np.abs(denominator) <= 1e-12
    safe = np.where(parallel, 1.0, denominator)
    weight = (delta[..., 0] * other_step[None, :, 1]
              - delta[..., 1] * other_step[None, :, 0]) / safe
    other = (delta[..., 0] * steps[:, None, 1]
             - delta[..., 1] * steps[:, None, 0]) / safe
    hit = ~parallel & (weight >= -1e-9) & (weight <= 1.0 + 1e-9) \
        & (other >= -1e-9) & (other <= 1.0 + 1e-9)
    return weight, hit


def nearest_on(polygon, point) -> np.ndarray:
    """The point of the outline closest to `point`."""
    starts, steps = polygon[:-1], polygon[1:] - polygon[:-1]
    squares = (steps * steps).sum(axis=1)
    weight = np.clip(((point - starts) * steps).sum(axis=1)
                     / np.where(squares > 0.0, squares, 1.0), 0.0, 1.0)
    spots = starts + steps * weight[:, None]
    return spots[int(np.argmin(((spots - point) ** 2).sum(axis=1)))].copy()


def where_it_enters(points, arcs, polygon) -> tuple:
    """Where a walk that starts outside the outline first crosses into it.

    The step that goes from outside to inside is solved exactly, so the end of the
    span lands on the outline rather than on the sample nearest to it.
    """
    inside = pattern_geometry.inside_mask(polygon, points)
    if not inside.any():
        raise GeometryRefused("the line lies outside the pattern",
                              "nothing of it is inside the outline")
    spot = int(np.argmax(inside))
    if spot == 0:
        return 0.0, np.asarray(points[0], dtype=np.float64)
    starts, steps = points[spot - 1:spot], points[spot:spot + 1] - points[spot - 1:spot]
    weight, hit = _segment_crossings(starts, steps, polygon)
    if not hit.any():
        return float(arcs[spot]), np.asarray(points[spot], dtype=np.float64)
    row, column = np.argwhere(hit)[0]
    along = float(weight[int(row), int(column)])
    return (float(arcs[spot - 1]) + along * float(np.linalg.norm(steps[0])),
            starts[0] + along * steps[0])


def endpoint_of(points, arcs, polygon, mode) -> dict:
    """Where one end of the chain should be: an arc along it, or a point to reach.

    The chain is read from the end in question, so an end that lies outside is cut
    back to where the walk enters the outline, and one that lies inside is left
    alone unless the mode extends it, which puts its end on the nearest point of
    the outline.
    """
    if pattern_geometry.inside_mask(polygon, points[:1])[0]:
        if mode != "EXTEND":
            return {"arc": 0.0, "point": None, "moved": 0.0}
        target = nearest_on(polygon, points[0])
        return {"arc": 0.0, "point": target,
                "moved": float(np.hypot(*(target - points[0])))}
    arc, target = where_it_enters(points, arcs, polygon)
    return {"arc": arc, "point": None,
            "moved": float(np.hypot(*(target - points[0])))}


def plan_fit(line, polygon, mode) -> dict:
    """The span of the line that stays, and where its two ends go.

    A line that lies outside the pattern altogether, and one whose span has no
    length left, are both refused here, before anything is written.
    """
    pieces = walked_pieces(line)
    if not pieces:
        raise GeometryRefused("that internal line has no pieces")
    points, arcs = joined(pieces)
    tail = [piece[::-1] for piece in pieces[::-1]]
    tail_points, tail_arcs = joined(tail)
    total = float(arcs[-1])
    start = endpoint_of(points, arcs, polygon, mode)
    back = endpoint_of(tail_points, tail_arcs, polygon, mode)
    if not start["moved"] and not back["moved"]:
        raise GeometryRefused(
            "both ends of that line are already inside the pattern",
            "there is nothing to trim; extend takes them out to the outline")
    span_from = 0.0 if start["point"] is not None else start["arc"]
    span_to = total if back["point"] is not None else total - back["arc"]
    if span_to - span_from <= SPAN_EPSILON_MM:
        raise GeometryRefused("the line lies outside the pattern",
                              "nothing of it would be left inside the outline")
    return {"pieces": pieces, "start": start, "back": back,
            "span": (span_from, span_to)}


def drop_pieces(pattern, line, indices) -> int:
    """Take these pieces out of the line, with the points nothing uses any more.

    A seam on one of them has nothing left to name, so it is dropped and counted;
    a seam on a piece that stays is untouched, because the pieces that stay are
    the very edges they were.
    """
    gone = [line.edges[index] for index in indices]
    seam_ends = pattern_geometry._sewing_ends_on(
        pattern, [(edge.global_uuid, piece_points(edge)) for edge in gone])
    for end in seam_ends:  # loop: one seam end per dropped piece
        pattern.project.sewings[end["sewing"]].impacted = True
    pool = {int(edge.vertex_index[slot]) for edge in gone for slot in (0, 1)}
    for index in sorted(indices, reverse=True):  # loop: one dropped piece per index
        line.edges.remove(index)
    pattern.refresh_collection_uuid(line.edges)
    for index in sorted(pool, reverse=True):  # loop: one point of a dropped piece
        if not _vertex_is_orphan(pattern, index):
            continue
        pattern.vertices.remove(index)
        for edge in pattern.edges:
            _shift_index(edge, index)
        for other in pattern.internal_lines:
            for edge in other.edges:
                _shift_index(edge, index)
    pattern.refresh_collection_uuid(pattern.vertices)
    for other in pattern.internal_lines:
        pattern.refresh_collection_uuid(other.edges)
    return len({end["sewing"] for end in seam_ends})


def fit_line(pattern, line, *, mode="EXTEND") -> dict:
    """Put both of one internal line's ends on the outline.

    The span is read and decided first, so a line that cannot be fitted is refused
    with the line exactly as it was. Only the two pieces an end was cut into are
    rewritten; the pieces between them are the pieces they were, and so are the
    points they run through.
    """
    polygon = np.asarray(pattern.get_boundary_points(), dtype=np.float64)
    if polygon.ndim != 2 or len(polygon) < 3:
        raise GeometryRefused(f"{pattern.name!r} has no outline to fit to")
    plan = plan_fit(line, polygon, mode)
    pieces, first, back = plan["pieces"], plan["start"], plan["back"]
    span_from, span_to = plan["span"]
    first_piece, from_here = piece_of(pieces, span_from)
    last_piece, to_here = piece_of(pieces, span_to)
    gone = [index for index in range(len(pieces))
            if index < first_piece or index > last_piece]
    touched = {first_piece, last_piece}
    seam_ends = pattern_geometry._sewing_ends_on(
        pattern, [(line.edges[index].global_uuid, pieces[index]) for index in touched])

    if first_piece == last_piece:
        kept = slice_by_arc_length(pieces[first_piece], from_here, to_here)
    else:
        kept = slice_by_arc_length(pieces[first_piece], from_here,
                                   piece_length(pieces[first_piece]))
        last_part = slice_by_arc_length(pieces[last_piece], 0.0, to_here)
    if first["point"] is not None:
        kept = np.vstack((first["point"], kept))
    if back["point"] is not None:
        if first_piece == last_piece:
            kept = np.vstack((kept, back["point"]))
        else:
            last_part = np.vstack((last_part, back["point"]))
    if len(kept) < 2 or (first_piece != last_piece and len(last_part) < 2):
        raise GeometryRefused("that line has nothing left to write")

    dropped = drop_pieces(pattern, line, gone) if gone else 0
    if first_piece == last_piece:
        edge = line.edges[0]
        pattern.sketch.set_vertex_position(int(edge.vertex_index[0]),
                                           (float(kept[0][0]), float(kept[0][1])))
        pattern.sketch.set_vertex_position(int(edge.vertex_index[1]),
                                           (float(kept[-1][0]), float(kept[-1][1])))
        pattern_geometry._write_piece(edge, kept)
        edge.update()
    else:
        head, tail_edge = line.edges[0], line.edges[len(line.edges) - 1]
        pattern.sketch.set_vertex_position(int(head.vertex_index[0]),
                                           (float(kept[0][0]), float(kept[0][1])))
        pattern_geometry._write_piece(head, kept)
        head.update()
        pattern.sketch.set_vertex_position(int(tail_edge.vertex_index[1]),
                                           (float(last_part[-1][0]),
                                            float(last_part[-1][1])))
        pattern_geometry._write_piece(tail_edge, last_part)
        tail_edge.update()
    moved = pattern_geometry._remap_sewing_ends_on(
        pattern, seam_ends,
        {edge.global_uuid: [(edge.global_uuid, 0.0, piece_length(
            np.asarray(edge.render_points, dtype=np.float64)))]
         for edge in {line.edges[0], line.edges[len(line.edges) - 1]}},
        trimmed=True)
    pattern.project.remove_impacted_sewings()
    pattern.mark_geometry_changed()
    pattern.require_sketch().rebuild_meshes()
    pattern.project.clear_edge_finder()
    return {"pattern": pattern.name, "mode": mode,
            "moved": (first["moved"], back["moved"]), "dropped_pieces": len(gone),
            "dropped_sewings": dropped, "sewings_moved": moved,
            "edges": [line.edges[index].global_uuid for index in range(len(line.edges))]}


register, unregister = register_classes_factory((NODE_OT_line_to_outline,))
