"""Make internal lines offset from the selected chain.

The source is whatever chain the selection names - a run of outline edges, or an
internal line - and the command writes lines inside the pattern offset from it
along its own normal. How far apart they are is a mode, the way an edge is
divided: either the source's own length divided into equal parts, with a line at
every division point inside it, or a distance, with a line at it, twice it, and so
on for as many as were asked for. A pleated edge is the first kind: select the
edge, ask for the fold lines, and the pattern keeps its shape.

The source is read, never changed: a run of the outline stays the outline it was
and an internal line stays where it is, so what comes out is exactly the lines
asked for. The offset of a curve is another curve, so every piece of the source is
sampled along its own arc length and moved along the normal there, and consecutive
pieces are joined by the straight chord between their offsets. Where the source
turns tighter than the distance, those pieces come back across each other and the
loop they enclose is removed before the line is used: the in/out classification of
a line's pieces and the seam sampling both assume a simple curve. A line that
lands outside the outline altogether is not written, because the mesh would
classify every piece of it as outside, and the report names it.
"""

import numpy as np
from bpy.props import EnumProperty, FloatProperty, IntProperty
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model import pattern_geometry
from ..model.generator import refuse_generated_edit
from ..model.model_data import refresh_all_uuids
from ..model.pattern_geometry import GeometryRefused, MERGE_THRESHOLD_MM
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.node_tree import get_active_node_tree
from ._2d_divide_edge import edge_target
from ._2d_operator_base import Operator2DBase, select_edges


mode_property = EnumProperty(
    name="Mode",
    description="How the distances between the lines are decided",
    items=[
        ("PARTS", "Equal parts",
         "Divide the source's own length into this many parts and write a line "
         "at every division point inside it",),
        ("DISTANCE", "Distance",
         "Write a line at the distance, one at twice it, and so on, for this "
         "many lines",),
    ],
    default="PARTS",
)


class NODE_OT_offset_copies(Operator2DBase):
    """Write internal lines offset from the selected outline run or internal line."""

    bl_idname = Operators.OffsetCopies2D
    bl_label = "offset copies"
    bl_options = {'REGISTER', 'UNDO'}

    mode: mode_property
    parts: IntProperty(
        name="Parts",
        description="How many parts of equal length the source is divided into",
        default=4,
        min=2,
    )
    distance: FloatProperty(
        name="Distance (mm)",
        description="How far apart the lines are, measured along the source's own "
                    "normal, to its left as it is walked; a negative distance "
                    "takes them to the other side",
        default=15.0,
    )
    count: IntProperty(
        name="Lines",
        description="How many lines to write at that distance from each other",
        default=5,
        min=1,
    )

    def draw(self, context: Context):
        """The adjust-last-operation panel: the numbers this mode uses."""
        layout = self.layout
        layout.prop(self, "mode")
        if self.mode == "PARTS":
            layout.prop(self, "parts")
        else:
            layout.prop(self, "distance")
            layout.prop(self, "count")

    def invoke(self, context: Context, event: Event):
        ensure_edit_mode(context, "EDGE", "EDGE_VERTEX")
        return self.execute(context)

    def execute(self, context: Context):
        project = get_active_node_tree(context)
        if project is None:
            return {'CANCELLED'}
        try:
            source = selected_source(project)
            if refuse_generated_edit(self, project, source["pattern"]):
                return {'CANCELLED'}
            report = offset_copies(source["pattern"], source,
                                   **arguments(self.mode, self.parts, self.distance,
                                               self.count))
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


def arguments(mode, parts, distance, count) -> dict:
    """The model command's arguments for the mode this run is in.

    Kept out of the operator so it can be exercised without a Blender operator
    instance, which cannot be created from Python.
    """
    if mode == "PARTS":
        return {"parts": int(parts)}
    return {"distance": float(distance), "count": int(count)}


def describe(report) -> str:
    """One line for the info area: what the run produced."""
    first, last = report["offsets"][0], report["offsets"][-1]
    where = (f"at {first:g} mm" if first == last else f"at {first:g} to {last:g} mm")
    message = (f"added {len(report['lines'])} internal line(s) off {report['source']} "
               f"{where}")
    if report["shortened"]:
        message += f", {len(report['shortened'])} shortened by its own crossings"
    if report["dropped"]:
        message += (f", {len(report['dropped'])} not made: "
                    + "; ".join(report["dropped"]))
    return message


# --------------------------------------------------------------- what it works on

def selected_source(project) -> dict:
    """The chain the selection names: one internal line, or a run of outline edges.

    The selection is stored as uuids and the uuid map is not something Blender's
    undo restores, so a selection that does not resolve is retried once after the
    map is rebuilt - which is what a re-run from the redo panel needs.
    """
    uuids = [entry.uuid for entry in project.selected_edges]
    if not uuids:
        raise pattern_geometry.GeometryRefused(
            "no edge is selected", "select the line to write the copies off")
    edges = pattern_geometry._edges_of_uuids(uuids)
    if len(edges) < len(uuids):
        refresh_all_uuids()
        edges = pattern_geometry._edges_of_uuids(uuids)
    pattern, line, indices = None, None, []
    for edge in edges:  # loop: one selected edge per check
        owner, line_index, index = edge_target(edge)
        if pattern is None:
            pattern = owner
        elif owner != pattern:
            raise pattern_geometry.GeometryRefused(
                "the selected edges are on more than one pattern",
                "write the copies of one pattern at a time")
        if line_index is None:
            indices.append(index)
            continue
        found = pattern.internal_lines[line_index]
        if line is not None and line != found:
            raise pattern_geometry.GeometryRefused(
                "edges of several internal lines are selected",
                "write the copies of one line at a time")
        line = found
    if pattern is None:
        raise pattern_geometry.GeometryRefused(
            "the selection names edges the model no longer has",
            "select the line to write the copies off again")
    if line is not None:
        if indices:
            raise pattern_geometry.GeometryRefused(
                "an outline edge and an internal line's edge are both selected",
                "write the copies of one line at a time")
        if line.is_loop:
            raise pattern_geometry.GeometryRefused(
                "that internal line is closed",
                "a closed line has no ends to measure the parts of")
        chain = [line.edges[index] for index in range(len(line.edges))]
        return {"pattern": pattern, "line": line, "edges": chain,
                "source": "the internal line"}
    run = pattern_geometry.run_indices(len(pattern.edges), indices)
    return {"pattern": pattern, "line": None,
            "edges": [pattern.edges[index] for index in run],
            "source": f"{len(run)} outline edge(s)"}


# ------------------------------------------------------- the command's own computation

def line_offsets(pattern, edges, parts, distance, count) -> list:
    """Where the new lines sit, measured along the source's own normal.

    Either the source's own length is divided into equal parts and a line is
    written at every division point inside it - the way an edge is divided, and
    how a pleated edge is laid out - or the lines are written at the distance,
    twice it, and so on, for as many as were asked for, a negative distance
    taking them to the other side. Nothing is clamped to the room the pattern
    has: a line that lands outside it is named in the report instead, and the
    caller decides whether to ask for fewer.
    """
    if (parts is None) == (distance is None):
        raise GeometryRefused("give either a part count or a distance",
                              "one of them decides where the lines go")
    if parts is not None:
        parts = int(parts)
        if parts < 2:
            raise GeometryRefused(
                f"dividing the source into {parts} part would not space anything",
                "ask for two or more parts")
        spacing = sum(float(edge.length) for edge in edges) / parts
        if spacing < MERGE_THRESHOLD_MM:
            raise GeometryRefused(
                f"{parts} parts of the source would be {spacing:.3f} mm apart",
                f"two lines closer than {MERGE_THRESHOLD_MM:g} mm cannot be told apart")
        return [spacing * step for step in range(1, parts)]
    distance, count = float(distance), int(count)
    if distance == 0.0:
        raise GeometryRefused(f"a distance of {distance:g} mm spaces nothing",
                              "give a distance in one direction or the other")
    if count < 1:
        raise GeometryRefused(f"{count} lines would not make a line",
                              "ask for one line or more")
    return [distance * step for step in range(1, count + 1)]


def plan_lines(pattern, edges, offsets, outline) -> tuple:
    """The lines this run would write, the ones it cannot, and what it shortened.

    Every line is planned before the first is written: the source is offset once
    per distance asked for, each offset is de-looped, and one that ends up outside
    the outline altogether is not written but named, because the mesh would
    classify every piece of it as outside and it would cut nothing.
    """
    source = pattern_geometry.sampled_pieces(edges)
    planned, dropped, shortened = [], [], []
    for offset in offsets:  # loop: one line per requested distance
        moved = [pattern_geometry.offset_piece(piece, offset) for piece in source]
        points, owner = pattern_geometry.dedupe_points(
            np.vstack(moved),
            np.concatenate([np.full(len(piece), index, dtype=np.int64)
                            for index, piece in enumerate(moved)]))
        points, owner, loops = pattern_geometry.without_loops(points, owner)
        if not pattern_geometry.inside_mask(outline, points).any():
            dropped.append(f"the line at {offset:g} mm lies outside the pattern")
            continue
        written = pattern_geometry.split_by_owner(points, owner)
        if not written:
            dropped.append(f"the line at {offset:g} mm has no length left")
            continue
        if loops:
            shortened.append(offset)
        planned.append(written)
    return planned, dropped, shortened


def offset_copies(pattern, source, *, parts=None, distance=None, count=1) -> dict:
    """Write the lines, and answer what was made and what could not be.

    Everything is decided before anything is written, so a run whose lines cannot
    be made leaves the pattern exactly as it was. All the writes are one undo step.
    """
    offsets = line_offsets(pattern, source["edges"], parts, distance, count)
    outline = np.asarray(pattern.get_boundary_points(), dtype=np.float64)
    planned, dropped, shortened = plan_lines(pattern, source["edges"], offsets, outline)
    if not planned:
        raise GeometryRefused(
            f"none of the {len(offsets)} line(s) asked for lands inside "
            f"{pattern.name!r}", "; ".join(dropped))
    lines = [pattern_geometry.write_curve_line(pattern, pieces) for pieces in planned]
    pattern.mark_geometry_changed()
    pattern_geometry._resample(pattern)
    pattern.require_sketch().rebuild_meshes()
    pattern.project.clear_edge_finder()
    return {"pattern": pattern.name, "source": source["source"], "offsets": offsets,
            "lines": lines,
            "edges": [uuid_value for written in lines for uuid_value in written],
            "shortened": shortened, "dropped": dropped}


register, unregister = register_classes_factory((NODE_OT_offset_copies,))
