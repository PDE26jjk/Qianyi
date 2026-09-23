"""Round, chamfer or hollow the selected corners, by dragging the radius."""

import math

import numpy as np
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators
from ..model import pattern_geometry as geometry
from ..model.generator import refuse_generated_edit
from ..model.geometry import Vertex2D
from ..model.model_data import refresh_all_uuids
from ..model.pattern import boundary_self_intersection
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.curve_fit import polyline_length, slice_by_arc_length
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree
from ._2d_operator_base import (Operator2DBase, select_edges, select_vertices,
                                show_redo_panel)

mode_property = EnumProperty(
    name="Corner",
    description="What replaces the corner",
    items=[
        ("ROUND", "Round", "Replace the corner with an arc tangent to both "
                           "edges",),
        ("CHAMFER", "Chamfer", "Replace the corner with a straight edge "
                               "between the same two points",),
        ("CONCAVE", "Hollow",
         "Put the arc on the other side of the chord, cutting a hollow into "
         "the panel",),
    ],
    default="ROUND",
)


class NODE_OT_corner(Operator2DBase):
    """Round, chamfer or hollow the selected corners.

    The command acts on the current selection - the vertices of one outline -
    and its numbers are the operator's own properties, so Blender's
    adjust-last-operation panel re-runs it from the state that existed before
    it: a new radius or another mode replaces the previous treatment instead of
    adding a second one. The first apply and the re-run are the same
    `execute`, and the undo step restores the selection the run was made from.

    Picked from the pattern editor's context menu the operator starts a drag:
    the radius follows the pointer from the corner, the arc is drawn as it
    would land, and the left button applies it. The same operator run again
    from the redo panel needs no pointer.
    """

    bl_idname = Operators.Corner2D
    bl_label = "corner"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    # Transient gesture state, with defaults so a step can never be the first
    # thing to look at a flag that was not set yet.
    blocked = None
    noop = False

    mode: mode_property
    from_tool: BoolProperty(
        name="From the toolbar",
        description="Set by the corner tool, which takes the treatment from its "
                    "own setting instead of from the menu entry that ran it",
        default=False,
        options={"SKIP_SAVE"},
    )
    pattern_name: StringProperty(
        name="Panel",
        description="The panel the tool took its target on; the redo panel "
                    "re-runs the command on it",
    )
    target_vertices: StringProperty(
        name="Corners",
        description="The vertices the tool took, as indices; the redo panel "
                    "re-runs the command on them",
    )
    radius: FloatProperty(
        name="Radius (mm)",
        description="Radius of the corner treatment, in millimetres",
        default=10.0,
        min=0.001,
    )

    @classmethod
    def poll(cls, context: Context):
        # The mode is not part of the poll: `invoke` puts the editor into the
        # mode this command works in, so a caller never has to check the header.
        return get_active_node_tree(context) is not None

    def draw(self, context: Context):
        """The adjust-last-operation panel: the numbers this command used."""
        layout = self.layout
        layout.prop(self, "mode")
        layout.prop(self, "radius")

    def invoke(self, context: Context, event: Event):
        ensure_edit_mode(context, "EDGE", "EDGE_VERTEX")
        project = get_active_node_tree(context)
        if project is None:
            return {'CANCELLED'}
        # Picked as a tool, the mode comes from the tool's own setting; run from
        # the menu or again from the redo panel, it is the property below.
        if self.from_tool:
            tool_mode = getattr(getattr(context.scene, "qmyi", None),
                                "corner_mode", None)
            if tool_mode:
                self.mode = tool_mode
        if not self.take_hover(context, project):
            return {'CANCELLED'}
        try:
            pattern, indices = self.resolve_target(project)
        except geometry.GeometryRefused as refused:
            return self.refuse(refused)
        if refuse_generated_edit(self, project, pattern):
            return {'CANCELLED'}
        try:
            # What radii this corner accepts, asked before the drag so the
            # pointer has a range to move in. The radius the last run left
            # behind is brought into that range rather than refused: a radius
            # that fitted one corner is usually wrong for the next one.
            limits = corner_limits(pattern, indices, mode=self.mode)
        except geometry.GeometryRefused as refused:
            return self.refuse(refused)
        self.pattern = pattern
        self.indices = indices
        self.smallest_radius = limits["smallest"]
        self.largest_radius = limits["largest"]
        # Dragging past the largest radius snaps a single corner to the merge:
        # each side merges as the tangent reaches its own far vertex, and the
        # drag ends when the farther of the two has been reached.
        self.merge_radius = None
        if len(indices) == 1:
            entry = limits["entries"][0]
            self.merge_radius = (max(entry["prev_length"], entry["next_length"])
                                 / entry["factor"])
        self.radius = min(max(float(self.radius), self.smallest_radius),
                          self.largest_radius)
        self.start_radius = self.radius
        self.corner = np.asarray(limits["entries"][0]["point"], dtype=np.float64)
        # The distance the pointer is at when the gesture starts: the radius
        # then grows and shrinks by how far the pointer moves from here.
        self.start_distance = self.pointer_distance(context, event)
        self.blocked = None
        # While the gesture runs it owns the preview; the tool's own cursor
        # preview leaves it alone.
        global_data.temp_draw_manager.preview_locked = True
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)
        self.refresh_preview(context)
        return {'RUNNING_MODAL'}

    def resolve_target(self, project):
        """The corners this run treats: the one the tool took, or the selection.

        A tool click has no selection step of its own - the operator is the
        first thing that runs - so the vertex it took is carried in the
        operator's own properties, and that is also what the redo panel re-runs
        from: Blender rolls the operator's undo step back, and that step
        includes the selection the operator itself made.
        """
        wanted = [int(part) for part in self.target_vertices.split(",")
                  if part.strip()] if self.target_vertices else []
        if wanted:
            for pattern in project.patterns:  # loop: one panel per name check
                if pattern.name != self.pattern_name:
                    continue
                if all(0 <= index < len(pattern.vertices) for index in wanted):
                    return pattern, sorted(set(wanted))
                break
        return selected_corner_run(project)

    def take_hover(self, context: Context, project) -> bool:
        """Take the corner under the pointer, if the pointer is on one.

        A tool is picked to be used, so a click takes the vertex it is pointing
        at; a click that lands on a vertex which is already part of the
        selection keeps that selection, so several corners can be treated in
        one run the way the command's own rule describes.
        """
        hover = context.scene.qmyi.hover_object
        if not isinstance(hover, Vertex2D) or hover.pattern is None:
            self.report({'INFO'}, "click a corner of the outline")
            return False
        if not geometry.is_outline_vertex(hover):
            self.report({'INFO'},
                        "that point is in the middle of an edge, not a corner")
            return False
        self.pattern_name = hover.pattern.name
        if hover.is_selected and len(project.selected_vertices) > 1:
            # The click landed inside a selection, so the run is that selection
            # and the vertex list decides it, not the one vertex under the
            # pointer.
            indices = [vertex.get_index()
                       for vertex in project.get_selected_objects_by_mode("EDGE", strict=False)
                       if isinstance(vertex, Vertex2D)
                       and geometry.is_outline_vertex(vertex)
                       and vertex.pattern == hover.pattern]
            self.target_vertices = ",".join(str(index) for index in sorted(indices))
            return True
        select_vertices(project, [hover])
        self.target_vertices = str(hover.get_index())
        return True

    def modal(self, context: Context, event: Event):
        if event.type == 'MOUSEMOVE':
            self.drag(context, event)
            return {'RUNNING_MODAL'}
        # The gesture is press, drag, release: the radius is what the drag set,
        # and the release applies it. A click that never moved applies the
        # radius the drag started from.
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'RELEASE':
            result = self.finish(context)
            if result == {'FINISHED'}:
                # The drag is over, so the panel is what changes the radius
                # from here on.
                show_redo_panel(context)
            return result
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.cleanup(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def drag(self, context: Context, event: Event) -> None:
        """Follow the pointer, as an offset from the radius the drag started at.

        The radius grows and shrinks by how much the pointer moved, so the drag
        starts at a radius that fits the corner instead of jumping to whatever
        distance the pointer happens to be at. Dragging below what the corner
        can take is not an error and not a clamp: the radius reaches zero, and a
        radius of zero means the corner is left alone.
        """
        radius = self.start_radius + (self.pointer_distance(context, event)
                                      - self.start_distance)
        radius = max(radius, 0.0)
        # A single corner can be pulled past the largest radius that fits, and
        # the drag ends at the merged corner's own radius; several corners stop
        # at what their shared edges allow.
        if self.merge_radius is not None:
            radius = min(radius, self.merge_radius)
        else:
            radius = min(radius, self.largest_radius)
        if abs(radius - self.radius) < 1e-4:
            return
        self.radius = radius
        self.refresh_preview(context)

    def pointer_distance(self, context: Context, event: Event) -> float:
        """How far the pointer is from the corner, in the panel's own space."""
        position = region2view_coord(context,
                                     (event.mouse_region_x, event.mouse_region_y))
        point = np.asarray(self.pattern.view_to_pattern_pos(position), dtype=np.float64)
        return float(np.hypot(*(point - self.corner)))

    def refresh_preview(self, context: Context) -> None:
        """Draw the arc this radius would write, or say why it cannot."""
        manager = global_data.temp_draw_manager
        if self.radius > self.largest_radius + 1e-9 and self.merge_radius is not None:
            # Past the largest radius that fits, the corner is drawn merged:
            # both edges consumed, the vertex gone, the arc end to end.
            self.noop = False
            try:
                plan = plan_corner_merge(self.pattern, self.indices[0],
                                         radius=self.radius, mode=self.mode)
            except geometry.GeometryRefused as refused:
                self.blocked = refused
                return
            self.blocked = None
            self.draw_preview(context, plan)
            return
        if self.radius < self.smallest_radius:
            # Too small to write: nothing would change, so nothing is drawn and
            # nothing will be applied.
            self.blocked = None
            self.noop = True
            if manager is not None:
                manager.clear_tool_preview()
            self.set_status(context, None)
            if context.area is not None:
                context.area.tag_redraw()
            return
        self.noop = False
        try:
            plan = plan_corner(self.pattern, self.indices,
                                        radius=self.radius, mode=self.mode)
        except geometry.GeometryRefused as refused:
            # The radius is inside the range, so this is a corner the command
            # still cannot treat; the last arc stays up and the run is refused
            # rather than applied if it is confirmed as it stands.
            self.blocked = refused
            return
        self.blocked = None
        self.draw_preview(context, plan)

    def draw_preview(self, context: Context, plan) -> None:
        """Draw every arc that would be written, and its tangent lengths."""
        manager = global_data.temp_draw_manager
        if manager is None:
            return
        manager.clear_tool_preview()
        for entry in plan["entries"]:  # loop: one previewed corner per entry
            points = [self.pattern.pattern_to_view_pos(point)
                      for point in entry["arc"]["points"]]
            for index in range(len(points) - 1):  # loop: one segment per pair
                manager.add_tool_line(points[index], points[index + 1])
            corner = self.pattern.pattern_to_view_pos(entry["point"])
            for tangent in (entry["tangent1"], entry["tangent2"]):
                manager.add_tool_line(corner,
                                      self.pattern.pattern_to_view_pos(tangent))
        # The corner the run acts on stays visible while the radius is dragged.
        manager.set_tool_points(
            [(self.pattern, entry["point"], "target") for entry in plan["entries"]])
        self.set_status(context, plan)
        if context.area is not None:
            context.area.tag_redraw()

    def set_status(self, context: Context, plan) -> None:
        workspace = getattr(context, "workspace", None)
        if workspace is None:
            return
        if plan is None:
            workspace.status_text_set(
                f"{self.mode.lower()} corner: radius {self.radius:.3f} mm is "
                f"below the smallest that fits ({self.smallest_radius:.3f} mm) "
                "- nothing will be applied")
            return
        if plan.get("merged"):
            workspace.status_text_set(
                f"{self.mode.lower()} corner: merged - the arc takes the whole "
                f"of both edges and the vertex goes ({plan['radius']:.3f} mm "
                f"radius) - left click to apply, Esc to cancel")
            return
        workspace.status_text_set(
            f"{self.mode.lower()} corner: radius {self.radius:.3f} mm "
            f"(fits {plan['smallest_radius']:.3f} to {plan['largest_radius']:.3f}) "
            "- move to size, left click to apply, Esc to cancel")

    def finish(self, context: Context):
        if self.noop:
            self.report({'INFO'}, "the radius is below what this corner can "
                                  "take: nothing was changed")
            self.cleanup(context)
            return {'CANCELLED'}
        if self.blocked is not None:
            result = self.refuse(self.blocked)
            self.cleanup(context)
            return result
        result = self.execute(context)
        self.cleanup(context)
        return result

    def cleanup(self, context: Context) -> None:
        manager = global_data.temp_draw_manager
        if manager is not None:
            manager.clear_tool_preview()
            manager.preview_locked = False
        workspace = getattr(context, "workspace", None)
        if workspace is not None:
            workspace.status_text_set(None)
        context.window.cursor_modal_restore()
        if context.area is not None:
            context.area.tag_redraw()

    def execute(self, context: Context):
        project = get_active_node_tree(context)
        if project is None:
            return {'CANCELLED'}
        try:
            pattern, indices = self.resolve_target(project)
        except geometry.GeometryRefused as refused:
            return self.refuse(refused)
        if refuse_generated_edit(self, project, pattern):
            return {'CANCELLED'}
        try:
            # A radius outside the range is clamped rather than refused: the
            # redo panel's slider has no way to know the range, so dragging it
            # to either end asks for a value the corner cannot take. Above the
            # largest, a single corner is answered with the merge - the arc
            # takes the whole of both edges and the vertex goes - and below the
            # smallest the answer is that there is nothing to treat, so the
            # command does nothing rather than reporting.
            limits = corner_limits(pattern, indices, mode=self.mode)
            if float(self.radius) < limits["smallest"]:
                # Reported as finished with nothing done, not as cancelled: on
                # a re-run Blender rolls the operator's own step back first and
                # keeps the last result when the re-run cancels, so a radius of
                # zero has to succeed at leaving the panel alone.
                self.report({'INFO'}, "the radius is below what this corner can "
                                      "take: nothing was changed")
                return {'FINISHED'}
            if float(self.radius) > limits["largest"] + 1e-9 and len(indices) == 1:
                report = corner_vertices(pattern, indices, radius=self.radius,
                                         mode=self.mode, merge=True)
            else:
                self.radius = min(float(self.radius), limits["largest"])
                report = corner_vertices(pattern, indices,
                                         radius=self.radius, mode=self.mode)
        except geometry.GeometryRefused as refused:
            return self.refuse(refused)
        # The outline changed, so the finder the tools snap against is stale.
        project.clear_edge_finder()
        select_edges(project, report["corner_uuids"])
        self.report({'INFO'}, describe(report))
        return {'FINISHED'}

    def refuse(self, refused):
        """Report a refusal and its hints, the way every command here does."""
        self.report({'ERROR'}, refused.reason)
        for hint in refused.hints:  # loop: one report line per hint
            self.report({'INFO'}, hint)
        return {'CANCELLED'}


def describe(report) -> str:
    """One line for the info area: what the corner command produced."""
    done = {"ROUND": "rounded", "CHAMFER": "chamfered", "CONCAVE": "hollowed"}
    message = (f"{done[report['mode']]} {len(report['corners'])} corner(s) of "
               f"{report['panel']} at {report['radius']:.3f} mm")
    if report["copies"]:
        message += f", with {report['copies']} linked copies"
    if report["sewings_moved"]:
        message += f", {report['sewings_moved']} seam end(s) moved with the edges"
    if report["warnings"]:
        message += (f", {len(report['warnings'])} piece(s) could not be fitted "
                    f"to tolerance")
    return message


# --- the command's own computation

CORNER_MODES = ("ROUND", "CHAMFER", "CONCAVE")

STRAIGHT_CORNER_EPS = 1e-6

CORNER_EDGE_MARGIN_MM = 5.0

def selected_corner_run(project):
    """The selected outline vertices, as (panel, indices)."""
    uuids = [entry.uuid for entry in project.selected_vertices]
    if not uuids:
        raise geometry.GeometryRefused("no vertex is selected",
                              "select the corner of the outline to treat")
    vertices = []
    for uuid_value in uuids:
        try:
            obj = global_data.get_obj_by_uuid(uuid_value, check_uuid=True)
        except Exception:
            obj = None
        if geometry.is_outline_vertex(obj):
            vertices.append(obj)
    if len(vertices) < len(uuids):
        refresh_all_uuids()
        vertices = [global_data.get_obj_by_uuid(uuid_value, check_uuid=False)
                    for uuid_value in uuids]
        vertices = [vertex for vertex in vertices if geometry.is_outline_vertex(vertex)]
    if not vertices:
        raise geometry.GeometryRefused("no corner of an outline is selected",
                              "a point in the middle of an edge is not a corner")
    pattern = vertices[0].pattern
    for vertex in vertices:
        if vertex.pattern != pattern:
            raise geometry.GeometryRefused("the selected vertices are on more than one panel",
                                  "treat the corners of one panel at a time")
    return pattern, sorted({vertex.get_index() for vertex in vertices})

def _tangent_at(points, backwards) -> np.ndarray:
    """The unit direction the outline travels in at the corner end of an edge.

    The samples next to the corner are walked inwards until two of them differ,
    so the tangent is not quantised by a low-sampled straight edge.
    """
    corner = np.asarray(points[-1] if backwards else points[0], dtype=np.float64)
    order = range(len(points) - 2, -1, -1) if backwards else range(1, len(points))
    for index in order:
        other = np.asarray(points[index], dtype=np.float64)
        delta = corner - other if backwards else other - corner
        if float(np.hypot(*delta)) > 1e-9:
            return geometry._unit(delta)
    return geometry._unit(np.asarray(points[-1], dtype=np.float64)
                 - np.asarray(points[0], dtype=np.float64))

def _mirror_across(start, end, point) -> np.ndarray:
    """`point` reflected across the line through `start` and `end`."""
    direction = geometry._unit(np.asarray(end, dtype=np.float64) - np.asarray(start, dtype=np.float64))
    offset = np.asarray(point, dtype=np.float64) - np.asarray(start, dtype=np.float64)
    along = float(np.dot(offset, direction)) * direction
    return np.asarray(start, dtype=np.float64) + along - (offset - along)

def _corner_edge_points(pattern, index, edges=None) -> np.ndarray:
    """The sampled polyline of one edge at a corner, refreshed if it has none."""
    edges = pattern.edges if edges is None else edges
    points = edges[index].render_points
    if points is None or len(points) < 2:
        pattern.forced_update()
        points = edges[index].render_points
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or len(points) < 2:
        raise geometry.GeometryRefused(f"an edge at vertex {index} of {pattern.name!r} has no shape",
                              "rebuild the panel's geometry first")
    return points

def _corner_adjacency(pattern, index):
    """The two edges that meet at one vertex, and the chain they live in.

    A corner is one edge arriving and one leaving, both from the same chain -
    the outline, or one internal line. Where the outline meets a line there is
    no single chain to treat, and that is refused by name.
    """
    arriving, leaving = [], []
    for edge in pattern.edges:
        if edge.vertex_index[1] == index:
            arriving.append((edge, None))
        if edge.vertex_index[0] == index:
            leaving.append((edge, None))
    for line_index, line in enumerate(pattern.internal_lines):
        for edge in line.edges:
            if edge.vertex_index[1] == index:
                arriving.append((edge, line_index))
            if edge.vertex_index[0] == index:
                leaving.append((edge, line_index))
    if len(arriving) == 1 and len(leaving) == 1:
        (prev_edge, prev_home), (next_edge, next_home) = arriving[0], leaving[0]
        if prev_home is next_home:
            return prev_edge, next_edge, prev_home
        raise geometry.GeometryRefused(
            f"vertex {index} of {pattern.name!r} is where the outline meets an "
            f"internal line",
            "treating such a corner is not offered")
    raise geometry.GeometryRefused(
        f"vertex {index} of {pattern.name!r} is not a corner",
        f"a corner has one edge arriving and one leaving it; this vertex has "
        f"{len(arriving)} arriving and {len(leaving)} leaving")

def _corner_table(pattern, index, winding) -> dict:
    """What the two edges at one vertex say about treating that corner.

    The two edges come from one chain - the outline, or one internal line -
    which the entry records as its `line_index` (`None` for the outline).
    """
    vertex = pattern.vertices[index]
    prev_edge, next_edge, line_index = _corner_adjacency(pattern, index)
    edges = pattern.edges if line_index is None \
        else pattern.internal_lines[line_index].edges
    prev_points = _corner_edge_points(pattern, prev_edge.get_index(), edges)
    next_points = _corner_edge_points(pattern, next_edge.get_index(), edges)
    tangent_in = _tangent_at(prev_points, backwards=True)
    tangent_out = _tangent_at(next_points, backwards=False)
    turn = math.atan2(geometry._cross(tangent_in, tangent_out), float(np.dot(tangent_in, tangent_out)))
    # A counter-clockwise outline turns left at a convex corner and right at a
    # reflex one, which is what makes the interior angle larger than a half turn.
    angle = math.pi - winding * turn
    if abs(angle - math.pi) < STRAIGHT_CORNER_EPS:
        raise geometry.GeometryRefused(
            f"the outline is straight at vertex {index} of {pattern.name!r}",
            "the two edges are collinear there, so there is no corner to treat")
    return {
        "index": index,
        "line_index": line_index,
        "point": np.array((float(vertex.co[0]), float(vertex.co[1])), dtype=np.float64),
        "angle": angle,
        # How much tangent length one millimetre of radius costs: the same at a
        # reflex corner, where the arc is tangent to the same two edges.
        "factor": 1.0 / abs(math.tan(angle / 2.0)),
        "convex": angle < math.pi,
        "prev_index": prev_edge.get_index(),
        "next_index": next_edge.get_index(),
        "prev_uuid": prev_edge.global_uuid,
        "next_uuid": next_edge.global_uuid,
        "prev_length": polyline_length(prev_points),
        "next_length": polyline_length(next_points),
        "prev_points": prev_points,
        "next_points": next_points,
        "tangent_in": tangent_in,
        "tangent_out": tangent_out,
    }

def _corner_tangents(entry) -> tuple:
    """The two points the corner edge joins, one tangent length from the corner."""
    tangent = entry["tangent"]
    return (geometry._point_on(entry["prev_points"], entry["prev_length"] - tangent),
            geometry._point_on(entry["next_points"], tangent))

def _corner_arc(entry, radius, mode) -> dict:
    """The arc that replaces one corner: centre, Bezier handles, sampled points.

    `ROUND` is the arc tangent to both edges, which removes the corner;
    `CONCAVE` is the same arc mirrored across the chord between the tangent
    points, which cuts a hollow into the panel instead.
    """
    angle = entry["angle"]
    bisector = geometry._unit(geometry._unit(-entry["tangent_in"]) + geometry._unit(entry["tangent_out"]))
    centre = entry["point"] + bisector * (radius / math.sin(angle / 2.0))
    if mode == "CONCAVE":
        centre = _mirror_across(entry["tangent1"], entry["tangent2"], centre)
    return geometry._arc_between(entry["tangent1"], entry["tangent2"], centre, radius)

def _corner_geometry(entries, radius, mode) -> None:
    """Fill in the points and the arc every corner gets at this radius.

    Both tangent points stay points of the edges they were measured on: the
    radius the command accepts keeps `CORNER_EDGE_MARGIN_MM` of edge between
    each of them and the vertex at the far end. Past that radius a single
    corner merges instead - the tangent point joins the far vertex and the
    edge is consumed.
    """
    for entry in entries:
        entry["tangent"] = radius * entry["factor"]
        entry["tangent1"], entry["tangent2"] = _corner_tangents(entry)
        entry["arc"] = _corner_arc(entry, radius, mode)

def _corner_trims(entries) -> dict:
    """How much each touched edge loses at each end, by uuid."""
    trims = {}
    for entry in entries:
        for role, points, length in (("prev", entry["prev_points"], entry["prev_length"]),
                                     ("next", entry["next_points"], entry["next_length"])):
            trim = trims.setdefault(entry[f"{role}_uuid"],
                                    {"start": 0.0, "end": 0.0, "points": points,
                                     "length": length})
            if role == "prev":
                trim["end"] = max(trim["end"], entry["tangent"])
            else:
                trim["start"] = max(trim["start"], entry["tangent"])
    return trims

def _corner_piece(trim) -> np.ndarray:
    """What one edge becomes: the part of it the corner leaves behind."""
    return slice_by_arc_length(trim["points"], trim["start"], trim["length"] - trim["end"])

def corner_outline(pattern, entries, trims) -> np.ndarray:
    """The outline the corner treatment would write, as one closed polyline."""
    chunks = []
    for edge in pattern.edges:
        uuid_value = edge.global_uuid
        trim = trims.get(uuid_value)
        points = (np.asarray(edge.render_points, dtype=np.float64) if trim is None
                  else _corner_piece(trim))
        chunks.append(points[:-1])
        for corner in entries:
            if corner["prev_uuid"] == uuid_value:
                chunks.append(corner["arc"]["points"][:-1])
    candidate = np.concatenate(chunks, dtype=np.float64)
    # A repeated point is a zero-length segment, which the crossing test does
    # not define: the outline the panel samples never repeats a point.
    keep = np.ones(len(candidate), dtype=bool)
    keep[1:] = np.linalg.norm(np.diff(candidate, axis=0), axis=1) > 1e-9
    return candidate[keep]

def _check_corner_outline(pattern, entries, trims) -> None:
    """Refuse a corner treatment whose outline would cross itself."""
    candidate = corner_outline(pattern, entries, trims)
    if len(candidate) < 3:
        return
    intersected, crossing = boundary_self_intersection(candidate.astype(np.float32))
    if intersected:
        where = (f"the crossing is at ({crossing[0]:.1f}, {crossing[1]:.1f}) mm"
                 if crossing else "the outline is too small to enclose an area")
        raise geometry.GeometryRefused(
            "the corner would make the outline cross itself", where,
            "a smaller radius, or treating fewer corners at once, keeps the outline simple")

def _corner_crosses(pattern, entries, mode, radius) -> bool:
    """Whether the corner treatment at this radius would cross the outline."""
    trial = [dict(entry) for entry in entries]
    _corner_geometry(trial, radius, mode)
    try:
        _check_corner_outline(pattern, trial, _corner_trims(trial))
        return False
    except geometry.GeometryRefused:
        return True

def _corner_crossing_limit(pattern, entries, mode, ceiling) -> float:
    """The largest radius at or below `ceiling` whose outline stays simple.

    Bisection, because whether a candidate outline crosses itself is answered by
    sampling it and testing it, and the answer is monotone in the radius.
    """
    if ceiling <= 0.0 or not _corner_crosses(pattern, entries, mode, ceiling):
        return ceiling
    low, high = 0.0, ceiling
    for _ in range(18):
        middle = (low + high) / 2.0
        if _corner_crosses(pattern, entries, mode, middle):
            high = middle
        else:
            low = middle
    return low

def corner_limits(pattern, vertex_indices, *, mode="ROUND") -> dict:
    """The radii a corner run accepts, without writing anything.

    Every treated corner takes `radius * factor` from each of its two edges, so
    an edge with a treated corner at both ends holds both tangent lengths - half
    of the edge when the two are equal. The largest radius is what the edges
    allow less `CORNER_EDGE_MARGIN_MM` at each end, cut back to the largest whose
    outline stays simple; the smallest leaves a piece above the merge threshold.
    """
    if mode not in CORNER_MODES:
        raise geometry.GeometryRefused(f"unknown corner mode {mode!r}",
                              f"use one of {', '.join(CORNER_MODES)}")
    count = len(pattern.vertices)
    if len(pattern.edges) < 3:
        raise geometry.GeometryRefused(f"{pattern.name!r} has {len(pattern.edges)} edge(s)",
                              "a corner needs an outline with at least three edges")
    order = sorted({int(index) for index in vertex_indices})
    if not order:
        raise geometry.GeometryRefused("no vertex is selected", "select the corner to treat")
    for index in order:
        if not 0 <= index < count:
            raise geometry.GeometryRefused(f"{pattern.name!r} has no vertex {index}",
                                  f"it has {count} vertices")
    geometry._ensure_shape(pattern, range(len(pattern.edges)))
    winding = 1.0 if pattern.calc_area() >= 0.0 else -1.0
    entries = [_corner_table(pattern, index, winding) for index in order]
    homes = {entry["line_index"] for entry in entries}
    if len(homes) > 1:
        raise geometry.GeometryRefused(
            f"{pattern.name!r} has corners of the outline and of an internal "
            f"line selected together",
            "treat the corners of the outline, or of one line, at a time")
    line_index = next(iter(homes))
    if line_index is not None:
        line = pattern.internal_lines[line_index]
        geometry._ensure_shape(pattern, range(len(line.edges)), line.edges)
    # The margin is the vector command's own: how much of an edge stays
    # between a tangent point and the vertex beyond it. The mesh's sampling
    # granularity has no say in it.
    margin = CORNER_EDGE_MARGIN_MM
    # loop: the two edges of one corner per entry - how much of each edge this
    # run's treated corners share, after the margin each end keeps.
    budgets = {}
    for entry in entries:
        for uuid_value, length in ((entry["prev_uuid"], entry["prev_length"]),
                                   (entry["next_uuid"], entry["next_length"])):
            usable = max(length - margin, 0.0)
            held, factors = budgets.get(uuid_value, (usable, 0.0))
            budgets[uuid_value] = (min(held, usable), factors + entry["factor"])
    limits = {}
    for entry in entries:
        limits[entry["index"]] = min(budgets[uuid][0] / budgets[uuid][1]
                                     for uuid in (entry["prev_uuid"], entry["next_uuid"]))
    smallest = max(geometry.MERGE_THRESHOLD_MM / entry["factor"] for entry in entries)
    ceiling = min(limits.values())
    if ceiling <= 0.0 or ceiling < smallest:
        worst = min(limits, key=lambda index: limits[index])
        shortest = min(entry["prev_length"] for entry in entries)
        raise geometry.GeometryRefused(
            f"the edges next to vertex {worst} of {pattern.name!r} are too short to treat",
            f"the shortest one is {shortest:.3f} mm, and a corner needs {margin:g} mm "
            "left on each side of it")
    return {"pattern": pattern, "entries": entries, "order": order, "limits": limits,
            "margin": margin, "smallest": smallest, "line_index": line_index,
            "largest": ceiling if line_index is not None
            else _corner_crossing_limit(pattern, entries, mode, ceiling)}

def plan_corner(pattern, vertex_indices, *, radius, mode="ROUND") -> dict:
    """Where the corner treatment would land, without writing anything.

    The measurement the command applies, so a preview and the command cannot
    disagree.
    """
    layout = corner_limits(pattern, vertex_indices, mode=mode)
    radius_value = float(radius)
    if radius_value <= 0.0:
        raise geometry.GeometryRefused(f"a radius of {radius_value:g} mm would not change the corner",
                              "give a radius greater than zero")
    smallest, largest = layout["smallest"], layout["largest"]
    if radius_value > largest + 1e-9:
        worst = min(layout["limits"], key=lambda index: layout["limits"][index])
        raise geometry.GeometryRefused(
            f"a radius of {radius_value:g} mm does not fit the corner at vertex {worst}",
            f"the largest radius that fits is {largest:.3f} mm",
            "the tangent length has to fit the two edges - two corners on one edge "
            "share it - and the result has to stay a simple outline")
    if radius_value < smallest - 1e-9:
        raise geometry.GeometryRefused(
            f"a radius of {radius_value:g} mm is too small to write",
            f"the smallest radius this corner can take is {smallest:.3f} mm",
            f"a shorter tangent would leave a piece below {geometry.MERGE_THRESHOLD_MM:g} mm")
    entries = layout["entries"]
    _corner_geometry(entries, radius_value, mode)
    trims = _corner_trims(entries)
    _check_corner_outline(pattern, entries, trims)
    return {"pattern": pattern, "entries": entries, "trims": trims, "mode": mode,
            "radius": radius_value, "largest_radius": largest, "smallest_radius": smallest}

def plan_corner_merge(pattern, vertex_index, *, radius, mode="ROUND") -> dict:
    """The corner pulled to the very end, one side at a time.

    The tangent length follows the radius like any corner's, and each side
    merges when the tangent reaches that side's own far vertex - that side's
    edge is consumed and the arc ends on the vertex beyond it - while the
    other side keeps its trim until the tangent reaches its end too. The
    merged outline is tested for a self-crossing like any other.
    """
    if mode not in CORNER_MODES:
        raise geometry.GeometryRefused(f"unknown corner mode {mode!r}",
                              f"use one of {', '.join(CORNER_MODES)}")
    geometry._ensure_shape(pattern, range(len(pattern.edges)))
    winding = 1.0 if pattern.calc_area() >= 0.0 else -1.0
    entry = _corner_table(pattern, int(vertex_index), winding)
    up = -entry["tangent_in"]  # the ray from the corner to the first far vertex
    out = entry["tangent_out"]  # ... and to the second
    cos_a = float(np.dot(up, out))
    sin_a = abs(geometry._cross(up, out))
    prev_length, next_length = entry["prev_length"], entry["next_length"]
    point = entry["point"]
    far_prev = point + up * prev_length
    far_next = point + out * next_length
    # Inward normals: one on each ray, pointing at the other ray.
    normal_next = geometry._unit(up - cos_a * out)
    normal_prev = geometry._unit(out - cos_a * up)

    tangent = min(max(float(radius), 0.0) * entry["factor"], max(prev_length, next_length))
    consume_prev = tangent >= prev_length - 1e-9
    consume_next = tangent >= next_length - 1e-9
    if not consume_prev and not consume_next:
        # Not a merge at all: the tangent has not reached either end. The
        # normal command is what treats this, at a radius that fits.
        raise geometry.GeometryRefused(
            f"a radius of {float(radius):g} mm does not reach either edge's end",
            f"a corner merges when its tangent reaches {min(prev_length, next_length):g} mm",
            f"the largest radius that fits without merging is "
            f"{min(prev_length, next_length) / entry['factor']:.3f} mm")
    if consume_prev and consume_next:
        # Both far vertices: the arc is tangent to the longer ray at its end
        # and passes through the shorter one's.
        if next_length >= prev_length:
            base, normal = far_next, normal_next
            through_length = prev_length
        else:
            base, normal = far_prev, normal_prev
            through_length = next_length
        radius_value = (max(prev_length, next_length) ** 2 + through_length ** 2
                        - 2 * max(prev_length, next_length) * through_length * cos_a) \
            / (2 * sin_a * through_length)
        centre = base + normal * radius_value
        start, end = far_prev, far_next
    elif consume_prev:
        # The first side is consumed: the arc starts on its far vertex and is
        # tangent to the second edge at its own tangent point.
        end = point + out * tangent
        radius_value = (tangent ** 2 + prev_length ** 2
                        - 2 * tangent * prev_length * cos_a) / (2 * sin_a * prev_length)
        centre = end + normal_next * radius_value
        start = far_prev
    else:
        # The second side is consumed: the mirror of the case above.
        start = point + up * tangent
        radius_value = (tangent ** 2 + next_length ** 2
                        - 2 * tangent * next_length * cos_a) / (2 * sin_a * next_length)
        centre = start + normal_prev * radius_value
        end = far_next
    if mode == "CHAMFER":
        arc = {"points": np.linspace(start, end, 32, dtype=np.float64),
               "handle1": None, "handle2": None}
    else:
        if mode == "CONCAVE":
            centre = _mirror_across(start, end, centre)
        arc = geometry._arc_between(start, end, centre, radius_value)
    entry["tangent"] = tangent
    entry["tangent1"] = start
    entry["tangent2"] = end
    entry["consume_prev"] = consume_prev
    entry["consume_next"] = consume_next
    entry["arc"] = arc
    candidate = _merged_outline(pattern, entry)
    if len(candidate) >= 3:
        intersected, crossing = boundary_self_intersection(candidate.astype(np.float32))
        if intersected:
            where = (f"the crossing is at ({crossing[0]:.1f}, {crossing[1]:.1f}) mm"
                     if crossing else "the outline is too small to enclose an area")
            raise geometry.GeometryRefused(
                "the merged corner would make the outline cross itself", where)
    return {"pattern": pattern, "entries": [entry], "mode": mode,
            "radius": radius_value, "smallest_radius": 0.0,
            "largest_radius": radius_value, "merged": True}


def _merged_outline(pattern, entry) -> np.ndarray:
    """The chain with the corner merged in, as one polyline.

    The chain is the corner's own - the outline for an outline corner, the
    line's edges for a line corner. A consumed side is skipped - the arc
    stands in for it - and a side the tangent has not reached keeps the part
    of itself the corner leaves.
    """
    edges = pattern.edges if entry["line_index"] is None         else pattern.internal_lines[entry["line_index"]].edges
    chunks = []
    for edge in edges:
        uuid_value = edge.global_uuid
        points = edge.render_points
        if uuid_value == entry["prev_uuid"]:
            if not entry["consume_prev"]:
                points = np.asarray(points, dtype=np.float64)
                chunks.append(slice_by_arc_length(
                    points, 0.0, entry["prev_length"] - entry["tangent"])[:-1])
            continue
        if uuid_value == entry["next_uuid"]:
            chunks.append(entry["arc"]["points"][:-1])
            if not entry["consume_next"]:
                points = np.asarray(points, dtype=np.float64)
                chunks.append(slice_by_arc_length(
                    points, entry["tangent"], entry["next_length"])[:-1])
            continue
        if points is None:
            return np.zeros((0, 2), dtype=np.float64)
        chunks.append(np.asarray(points, dtype=np.float64)[:-1])
    candidate = np.concatenate(chunks, dtype=np.float64)
    keep = np.ones(len(candidate), dtype=bool)
    keep[1:] = np.linalg.norm(np.diff(candidate, axis=0), axis=1) > 1e-9
    return candidate[keep]


def _corner_member_merge(pattern, plan) -> dict:
    """Write one member's merged corner, and return what happened.

    The corner's own chain is what changes - the outline for an outline
    corner, the matching line of the member for a line corner. A side the
    tangent reached loses its edge - the arc ends on the vertex beyond it -
    and a side it has not reached is trimmed to the tangent point, which is a
    new vertex. When both sides are consumed the corner vertex goes with
    them; one consumed side takes it too, since nothing references it after
    its own edge is gone.
    """
    entry = plan["entries"][0]
    mode = plan["mode"]
    consume_prev, consume_next = entry["consume_prev"], entry["consume_next"]
    ends = geometry._sewing_ends_on(pattern, [
        (entry["prev_uuid"], entry["prev_points"]),
        (entry["next_uuid"], entry["next_points"])])
    edges = pattern.edges if entry["line_index"] is None         else pattern.internal_lines[entry["line_index"]].edges
    prev_edge = edges[entry["prev_index"]]
    next_edge = edges[entry["next_index"]]
    start_uuid = prev_edge.vertex0.global_uuid
    end_uuid = next_edge.vertex1.global_uuid
    prev_index, next_index = prev_edge.get_index(), next_edge.get_index()
    corner_position = min(prev_index, next_index)
    corner_vertex = entry["index"]
    # The draw side lets go of everything it holds for the edges about to be
    # removed - the same courtesy the element-delete flow pays first.
    draw_manager = global_data.temp_draw_manager
    if draw_manager is not None:
        draw_manager.clear()
    # Removals first: the consumed edges and the corner vertex leave, and
    # every surviving edge is shifted onto the smaller vertex pool. The
    # tangent vertices are added after - their indices are final from the
    # moment they are created - and each survivor is read back by its place
    # in the collection, which an add or a remove just retired.
    for index in sorted((prev_index if consume_prev else -1,
                         next_index if consume_next else -1), reverse=True):
        if index >= 0:
            edges.remove(index)
    pattern.vertices.remove(corner_vertex)
    for edge in pattern.edges:
        _shift_vertex_index(edge, corner_vertex)
    for line in pattern.internal_lines:
        for edge in line.edges:
            _shift_vertex_index(edge, corner_vertex)
    pattern.refresh_collection_uuid(pattern.vertices)
    pattern.refresh_collection_uuid(pattern.edges)
    for line in pattern.internal_lines:
        pattern.refresh_collection_uuid(line.edges)
    warnings = []
    start_index = global_data.get_obj_by_uuid(start_uuid, check_uuid=False).get_index()
    end_index = global_data.get_obj_by_uuid(end_uuid, check_uuid=False).get_index()
    second_start = second_end = -1
    if not consume_prev:
        prev_edge = edges[prev_index - (1 if consume_next and next_index < prev_index else 0)]
        second_start = pattern.add_vertex(
            (float(entry["tangent1"][0]), float(entry["tangent1"][1])))
        pattern.vertices[second_start].get_temp_data()
        prev_edge.vertex_index[1] = second_start
    if not consume_next:
        next_edge = edges[next_index - (1 if consume_prev and prev_index < next_index else 0)]
        second_end = pattern.add_vertex(
            (float(entry["tangent2"][0]), float(entry["tangent2"][1])))
        pattern.vertices[second_end].get_temp_data()
        next_edge.vertex_index[0] = second_end
    corner = edges.add()
    corner.vertex_index[0] = start_index
    corner.vertex_index[1] = end_index
    corner.pattern = pattern
    corner.get_temp_data()
    corner_uuid = corner.global_uuid
    arc = entry["arc"]
    if mode == "CHAMFER":
        corner.set_curve("straight")
    else:
        corner.set_curve("bezier",
                         handle1=(float(arc["handle1"][0]), float(arc["handle1"][1])),
                         handle2=(float(arc["handle2"][0]), float(arc["handle2"][1])),
                         handle1_type="FREE", handle2_type="FREE")
    corner.update(pattern)
    if corner.get_index() != corner_position:
        edges.move(corner.get_index(), corner_position)
    pattern.refresh_collection_uuid(pattern.vertices)
    pattern.refresh_collection_uuid(pattern.edges)
    for line in pattern.internal_lines:
        pattern.refresh_collection_uuid(line.edges)
    # The sections are rebuilt before the full refresh, so the sampling pass
    # and the C++ intersect pass both read chains that match the topology as
    # it stands - the order the element-delete flow has always used.
    pattern.recreate_sections()
    pattern.forced_update()
    geometry._resample(pattern)
    # Where a seam endpoint that sat on a touched edge goes: a consumed edge
    # maps its endpoints onto the corner treatment, a trimmed one keeps its
    # own place shortened by the tangent.
    pieces = {}
    if consume_prev:
        pieces[entry["prev_uuid"]] = [(corner_uuid, 0.0, entry["prev_length"])]
    else:
        pieces[entry["prev_uuid"]] = [(entry["prev_uuid"], 0.0, entry["tangent"])]
    if consume_next:
        pieces[entry["next_uuid"]] = [(corner_uuid, 0.0, entry["next_length"])]
    else:
        pieces[entry["next_uuid"]] = [(entry["next_uuid"], 0.0, entry["tangent"])]
    moved = geometry._remap_sewing_ends_on(pattern, ends, pieces, trimmed=True)
    relinked = geometry._mark_sewings(pattern, ends)
    pattern.generate_mesh()
    return {
        "corners": [{"index": entry["index"], "tangent_mm": entry["tangent"],
                     "edge": corner_uuid, "merged": True}],
        "corner_uuids": [corner_uuid], "warnings": warnings,
        "sewings_moved": moved, "sewings_marked": relinked,
    }


def _shift_vertex_index(edge, removed_index):
    """Close the gap a removed vertex left in the ends of an edge."""
    for slot in (0, 1):
        if int(edge.vertex_index[slot]) > removed_index:
            edge.vertex_index[slot] = int(edge.vertex_index[slot]) - 1


def _corner_member(pattern, plan) -> dict:
    """Write one member's corners, and return what happened.

    The plan names its edges by index, which is the same in every member of
    the chain - so the member's own edges are what get trimmed and moved. An
    `edges.add()` retires every wrapper the collection handed out before it,
    so the member's edges are carried as uuids and read back fresh from the
    uuid map whenever they are needed again.
    """
    entries, trims = plan["entries"], plan["trims"]

    def container_of(entry):
        return pattern.edges if entry["line_index"] is None \
            else pattern.internal_lines[entry["line_index"]].edges

    def member_edge(entry, role):
        return global_data.get_obj_by_uuid(resolved[entry[f"{role}_uuid"]],
                                           check_uuid=False)

    touched, seen, resolved = [], set(), {}
    for entry in entries:
        edges = container_of(entry)
        resolved[entry["prev_uuid"]] = edges[entry["prev_index"]].global_uuid
        resolved[entry["next_uuid"]] = edges[entry["next_index"]].global_uuid
        for role in ("prev", "next"):
            if entry[f"{role}_uuid"] not in seen:
                seen.add(entry[f"{role}_uuid"])
                touched.append((resolved[entry[f"{role}_uuid"]],
                                entry[f"{role}_points"]))
    ends = geometry._sewing_ends_on(pattern, touched)
    warnings, pieces, corner_uuids = [], {}, []
    # Structural changes first: adding a vertex and an edge retires wrappers,
    # so the uuids held above are what the writes resolve through.
    second_vertices = []
    for entry in entries:
        # The corner vertex becomes the first tangent point - an edge still ends
        # at it - and the second is a new vertex on the edge that leaves it.
        pattern.vertices[entry["index"]].co = entry["tangent1"]
        second = pattern.add_vertex(tuple(entry["tangent2"]))
        pattern.vertices[second].get_temp_data()
        second_vertices.append(second)
    pattern.refresh_collection_uuid(pattern.vertices)
    for entry, second in zip(entries, second_vertices):
        edges = container_of(entry)
        pattern.refresh_collection_uuid(edges)
        corner = edges.add()
        corner.vertex_index[0] = entry["index"]
        corner.vertex_index[1] = second
        corner.pattern = pattern
        corner.get_temp_data()
        corner_uuids.append(corner.global_uuid)
        # The edge that leaves the corner now starts at the second tangent point.
        member_edge(entry, "next").vertex_index[0] = second
    for entry, corner_uuid in zip(entries, corner_uuids):
        edges = container_of(entry)
        pattern.refresh_collection_uuid(edges)
        corner = global_data.get_obj_by_uuid(corner_uuid, check_uuid=True)
        prev_edge = member_edge(entry, "prev")
        next_edge = member_edge(entry, "next")
        if corner is None:
            raise geometry.GeometryRefused("the corner edges could not be resolved again",
                                  "the panel was left as it was")
        for target, piece, role in ((prev_edge, _corner_piece(trims[entry["prev_uuid"]]), "before"),
                                    (next_edge, _corner_piece(trims[entry["next_uuid"]]), "after")):
            if target is None or len(piece) == 0:
                continue
            reached, error = geometry._write_piece(target, piece)
            if not reached:
                warnings.append({"edge": target.get_index(), "piece": role,
                                 "error_mm": error})
        arc = entry["arc"]
        if plan["mode"] == "CHAMFER":
            corner.set_curve("straight")
        else:
            # Plain tuples: the edge's own writer tests the handles for a value,
            # and an array has no truth value.
            corner.set_curve("bezier",
                             handle1=(float(arc["handle1"][0]), float(arc["handle1"][1])),
                             handle2=(float(arc["handle2"][0]), float(arc["handle2"][1])),
                             handle1_type="FREE", handle2_type="FREE")
        corner.update(pattern)
        # The corner edge belongs between the two edges it joins, so the chain
        # stays the ordered run the panel samples.
        position = prev_edge.get_index() + 1
        if corner.get_index() != position:
            container_of(entry).move(corner.get_index(), position)
        # Where a seam endpoint that sat on a touched edge goes: the same edge it
        # was on, shortened to what the corner left of it.
        pieces[entry["prev_uuid"]] = [(entry["prev_uuid"], 0.0, entry["tangent"])]
        pieces[entry["next_uuid"]] = [(entry["next_uuid"], 0.0, entry["tangent"])]
    pattern.refresh_collection_uuid(pattern.edges)
    pattern.refresh_collection_uuid(pattern.vertices)
    for entry in entries:
        if entry["line_index"] is not None:
            pattern.refresh_collection_uuid(
                pattern.internal_lines[entry["line_index"]].edges)
    pattern.forced_update()
    moved = geometry._remap_sewing_ends_on(pattern, ends, pieces, trimmed=True)
    relinked = geometry._mark_sewings(pattern, ends)
    # The corner edges are in and the neighbours are trimmed, so build the
    # samples from the sections the outline has now before anything measures.
    geometry._resample(pattern)
    pattern.generate_mesh()
    return {
        "corners": [{"index": entry["index"], "tangent_mm": entry["tangent"],
                     "edge": uuid_value}
                    for entry, uuid_value in zip(entries, corner_uuids)],
        "corner_uuids": corner_uuids, "warnings": warnings,
        "sewings_moved": moved, "sewings_marked": relinked,
    }

def corner_vertices(pattern, vertex_indices, *, radius, mode="ROUND",
                    merge=False) -> dict:
    """Round, chamfer or hollow the corners at the selected vertices.

    One corner is replaced by two points placed at the tangent length on the
    two adjacent edges, joined by the edge the mode asks for: the tangent arc
    (`ROUND`), a straight edge (`CHAMFER`), or the arc mirrored across the
    chord between the tangent points, which adds material instead of removing
    it (`CONCAVE`). The adjacent edges are trimmed to their tangent points, so
    the outline stays one closed loop, and the result is tested for a
    self-crossing before anything is written. Without `merge` no vertex or
    edge is removed.

    With `merge` the corner is pulled to the very end instead: each side
    merges as the tangent reaches that side's own far vertex - its edge is
    consumed and the arc ends on the vertex beyond it - while the other side
    keeps its trim until the tangent reaches its end too, and the corner
    vertex goes with the first side that merges. Merging works on one corner
    at a time.
    """
    if merge:
        order = sorted({int(index) for index in vertex_indices})
        if len(order) != 1:
            raise geometry.GeometryRefused(
                "merging a corner works on one corner at a time",
                "treat the other corners with a radius that fits them")
        plan = plan_corner_merge(pattern, order[0], radius=radius, mode=mode)
        members = geometry._chain_members(pattern)
        report = None
        for member in members:
            result = _corner_member_merge(member, plan)
            if report is None:
                report = result
        report.update({
            "action": "corner_vertices", "mode": mode, "panel": pattern.name,
            "radius": plan["radius"], "largest_radius": plan["radius"],
            "smallest_radius": 0.0, "copies": len(members) - 1, "merged": True,
        })
        return report
    plan = plan_corner(pattern, vertex_indices, radius=radius, mode=mode)
    members = geometry._chain_members(pattern)
    report = None
    for member in members:
        result = _corner_member(member, plan)
        if report is None:
            report = result
    report.update({
        "action": "corner_vertices", "mode": mode, "panel": pattern.name,
        "radius": plan["radius"], "largest_radius": plan["largest_radius"],
        "smallest_radius": plan["smallest_radius"], "copies": len(members) - 1,
    })
    return report


register, unregister = register_classes_factory((NODE_OT_corner,))
