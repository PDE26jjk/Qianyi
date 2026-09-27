"""Put a point of the line where it crosses something else.

The lines of a pattern are drawn on top of each other: where two of them cross,
each keeps its own curve and nothing joins them, and the same is true where a
line crosses the outline. This command gives every one of those crossings a point
of its own: the line is split there, so the point exists, can be picked, and is
where a seam can be aimed.

The points are the line's own, not the other line's: two lines that cross are two
lines, and a point of one that happens to sit on the other is what a crossing is.
A crossing that lands within the merge threshold of a point the line already has
does not add a second one: that point is moved onto the crossing instead, which is
what keeps a line's own points from piling up on one place as it is drawn over
itself.
"""

import numpy as np
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model import pattern_geometry
from ..model.generator import refuse_generated_edit
from ..model.internal_line import InternalLine
from ..model.model_data import refresh_all_uuids
from ..model.pattern_geometry import GeometryRefused, MERGE_THRESHOLD_MM
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.node_tree import get_active_node_tree
from ._2d_cut_along_line import _Chain, _crossings
from ._2d_operator_base import Operator2DBase, select_vertices


class NODE_OT_line_intersections(Operator2DBase):
    """Put a point of the selected internal lines where they cross."""

    bl_idname = Operators.LineIntersections2D
    bl_label = "line intersections"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context: Context, event: Event):
        ensure_edit_mode(context, "EDGE", "EDGE_VERTEX")
        return self.execute(context)

    def execute(self, context: Context):
        project = get_active_node_tree(context)
        if project is None:
            return {'CANCELLED'}
        try:
            pattern, lines = selected_lines(project)
            if refuse_generated_edit(self, project, pattern):
                return {'CANCELLED'}
            report = split_at_intersections(pattern, lines)
        except pattern_geometry.GeometryRefused as refused:
            return self.refuse(refused)
        select_vertices(project, report["points"])
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
    """One line for the info area: what the crossings turned into."""
    message = (f"put {len(report['points'])} point(s) of the line where it crosses "
               f"something else on {report['pattern']}")
    if report["snapped"]:
        message += f", {report['snapped']} of them an existing point moved onto"
    if report["warnings"]:
        message += f", {len(report['warnings'])} piece(s) could not be fitted"
    return message


def selected_lines(project) -> tuple:
    """The pattern and the internal lines the selection names.

    The selection is stored as uuids and the uuid map is not something Blender's
    undo restores, so a selection that does not resolve is retried once after the
    map is rebuilt - which is what a re-run from the redo panel needs.
    """
    uuids = [entry.uuid for entry in project.selected_edges]
    if not uuids:
        raise GeometryRefused("no edge is selected",
                              "select the lines to put points at their crossings")
    edges = pattern_geometry._edges_of_uuids(uuids)
    if len(edges) < len(uuids):
        refresh_all_uuids()
        edges = pattern_geometry._edges_of_uuids(uuids)
    lines, pattern = [], None
    for edge in edges:  # loop: one selected edge per check
        parent = edge.get_parent()
        if not isinstance(parent, InternalLine):
            raise GeometryRefused(
                "an outline edge is selected",
                "a crossing is something a line has: select the lines")
        if parent not in lines:
            lines.append(parent)
        owner = parent.sketch.owner if parent.sketch is not None else None
        if pattern is None:
            pattern = owner
        elif owner != pattern:
            raise GeometryRefused("the selected lines are on more than one pattern",
                                  "put points at the crossings of one pattern at a time")
    if not lines or pattern is None:
        raise GeometryRefused("the selection names no internal line",
                              "select the lines to put points at their crossings")
    return pattern, lines


# ------------------------------------------------------- the command's own computation

def plan_intersections(pattern, lines) -> list:
    """Every crossing of these lines with anything else, and where it sits.

    The partners are the outline and every line of the pattern, the selected ones
    included: a crossing between two selected lines is found once from each side,
    and each side puts a point of its own there. The crossings are asked of the
    engine - the same call the section stage cuts the lines with - so a point the
    mesh would see is a point here too.
    """
    sketch = pattern.require_sketch()
    chains = [(line, _Chain(sketch, line.edges, line.is_loop)) for line in lines]
    others = [("the outline", _Chain(sketch, pattern.edges, True))]
    others += [(f"internal line {index}",
                _Chain(sketch, line.edges, line.is_loop))
               for index, line in enumerate(pattern.internal_lines)]
    found = []
    for line, chain in chains:  # loop: one selected line per plan
        crossings = []
        for label, partner in others:
            if partner is chain or partner.edges == chain.edges:
                continue
            for arc, _other in _crossings(chain, partner):
                crossings.append((arc, label))
        crossings.sort(key=lambda entry: entry[0])
        # Two partners that cross the line in the same place are one crossing of
        # the line: the places are close enough to be the same point.
        places = []
        for arc, label in crossings:
            if places and abs(arc - places[-1][0]) < MERGE_THRESHOLD_MM:
                continue
            places.append((arc, label))
        if places:
            found.append((line, chain, places))
    return found


def split_at_intersections(pattern, lines) -> dict:
    """Split every one of these lines where it crosses something else.

    Everything is planned before anything is written, so a run that finds no
    crossing leaves the pattern exactly as it was. A crossing within the merge
    threshold of a point the line already has moves that point onto the crossing
    instead of adding another.
    """
    plan = plan_intersections(pattern, lines)
    if not plan:
        raise GeometryRefused(
            "these lines cross nothing",
            "a point is only written where one line meets another or the outline")
    sketch = pattern.require_sketch()
    points, snapped, warnings = [], 0, []
    for line, chain, places in plan:  # loop: one line per plan
        own = {}
        for index in range(len(line.edges)):  # loop: the line's own two ends
            edge = line.edges[index]
            for slot in (0, 1):
                own[int(edge.vertex_index[slot])] = None
        cuts = {}
        moves, taken = [], set()
        for arc, _label in places:  # loop: one crossing per cut
            edge_index, local = chain.place(arc)
            spot = pattern_geometry._point_on(chain.points[edge_index], local)
            nearest, closest = None, MERGE_THRESHOLD_MM
            for vertex_index in own:
                if vertex_index in taken:
                    continue
                vertex = pattern.vertices[vertex_index]
                distance = float(np.hypot(float(vertex.co[0]) - spot[0],
                                          float(vertex.co[1]) - spot[1]))
                if distance < closest:
                    nearest, closest = vertex_index, distance
            if nearest is not None:
                taken.add(nearest)
                moves.append((nearest, spot))
                snapped += 1
                continue
            cuts.setdefault(edge_index, []).append(local)
        touched = sorted(cuts)
        tables = {index: pattern_geometry._table(pattern, index, line.edges)
                  for index in touched}
        seam_ends = pattern_geometry._sewing_ends_on(
            pattern, [(line.edges[index].global_uuid, tables[index]["points"])
                      for index in touched])
        for vertex_index, spot in moves:  # loop: one moved point per crossing
            sketch.set_vertex_position(vertex_index, (float(spot[0]), float(spot[1])))
            points.append(pattern.vertices[vertex_index])
        written = {}
        for index in sorted(touched, reverse=True):  # loop: one cut edge per edge
            original = line.edges[index].global_uuid
            cuts[index] = sorted(set(cuts[index]))
            warnings.extend(pattern_geometry._split_edge(
                pattern, index, cuts[index], tables[index], line.edges))
            lengths = pattern_geometry._piece_lengths(tables[index]["length"], cuts[index])
            written[original] = pattern_geometry._piece_table_on(line.edges, index, lengths)
            for position in range(len(lengths)):  # loop: one written piece per piece
                if position:
                    points.append(pattern.vertices[
                        int(line.edges[index + position].vertex_index[0])])
                line.edges[index + position].need_update_points = True
                line.edges[index + position].update()
        pattern.refresh_collection_uuid(line.edges)
        pattern_geometry._remap_sewing_ends_on(pattern, seam_ends, written)
        pattern_geometry._mark_sewings(pattern, seam_ends)
    pattern.refresh_collection_uuid(pattern.vertices)
    pattern.mark_geometry_changed()
    pattern_geometry._resample(pattern)
    sketch.rebuild_meshes()
    pattern.project.clear_edge_finder()
    return {"pattern": pattern.name, "points": points, "snapped": snapped,
            "warnings": warnings}


register, unregister = register_classes_factory((NODE_OT_line_intersections,))
