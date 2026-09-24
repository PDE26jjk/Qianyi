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
from ..model.model_data import owner_pattern, refresh_all_uuids
from ..model.pattern import boundary_self_intersection, crossing_check_enabled
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.coords_transform import region2view_coord
from ..utilities.curve_fit import polyline_length, slice_by_arc_length
from ..utilities.node_tree import get_active_node_tree
from ._2d_operator_base import (Operator2DBase, select_edges, select_vertices,
                                show_redo_panel)

CORNER_MODES = ("ROUND", "CHAMFER", "CONCAVE")
STRAIGHT_CORNER_EPS = 1e-6
CORNER_EDGE_MARGIN_MM = 5.0  # the edge kept between a tangent point and the vertex beyond it

mode_property = EnumProperty(
    name="Corner",
    description="What replaces the corner",
    items=[
        ("ROUND", "Round", "Replace the corner with an arc tangent to both edges"),
        ("CHAMFER", "Chamfer",
         "Replace the corner with a straight edge between the same two points"),
        ("CONCAVE", "Hollow",
         "Mirror the arc across the chord, cutting a hollow into the panel"),
    ],
    default="ROUND",
)


class NODE_OT_corner(Operator2DBase):
    """Round, chamfer or hollow the selected corners: drag the radius, click to apply."""

    bl_idname = Operators.Corner2D
    bl_label = "corner"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}
    blocked = None   # why the radius under the pointer cannot be written
    noop = False     # below every radius this corner takes
    crossing = True  # the scene's Check Self-Intersection switch

    mode: mode_property
    from_tool: BoolProperty(name="From the toolbar", default=False,
                            description="Use the corner tool's own setting",
                            options={"SKIP_SAVE"})
    pattern_name: StringProperty(name="Panel", description="The panel this run treats")
    target_vertices: StringProperty(name="Corners", description="The vertices, as indices")
    radius: FloatProperty(name="Radius (mm)", default=10.0, min=0.001,
                          description="Radius in millimetres")

    @classmethod
    def poll(cls, context: Context):
        return get_active_node_tree(context) is not None

    def draw(self, context: Context):
        self.layout.prop(self, "mode")
        self.layout.prop(self, "radius")

    def invoke(self, context: Context, event: Event):
        ensure_edit_mode(context, "EDGE", "EDGE_VERTEX")
        project = get_active_node_tree(context)
        if project is None:
            return {'CANCELLED'}
        if self.from_tool:
            tool_mode = getattr(getattr(context.scene, "qmyi", None), "corner_mode", None)
            if tool_mode:
                self.mode = tool_mode
        if not self.take_hover(context, project):
            return {'CANCELLED'}
        try:
            if not self.prepare(context):
                return {'CANCELLED'}
            # The drag starts in the treatment window, from a radius this corner
            # can write; the merge window is what it can be pulled on to.
            self.radius = min(max(float(self.radius), self.smallest), self.largest)
            self.start_radius = self.radius
            self.corner = np.asarray(self.limits["entries"][0]["point"], dtype=np.float64)
            self.start_distance = self.pointer_distance(context, event)
        except geometry.GeometryRefused as refused:
            return self.refuse(refused)
        global_data.temp_draw_manager.preview_locked = True  # the gesture owns the preview
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)
        self.refresh_preview(context)
        return {'RUNNING_MODAL'}

    def prepare(self, context: Context) -> bool:
        """Read what this run works on and with: the panel, the corners, the radii.

        Both entry points need the same three things, and the radius range is two
        windows: below `largest` the corner is treated, from `merge_from` on it
        merges, and nothing in the gap between them can be written at all.
        """
        project = get_active_node_tree(context)
        if project is None:
            return False
        pattern, indices = self.resolve_target(project)
        if refuse_generated_edit(self, project, pattern):
            return False
        self.crossing = crossing_check_enabled(context)
        self.pattern, self.indices = pattern, indices
        self.project = project
        self.limits = corner_limits(pattern, indices, mode=self.mode,
                                    check_crossing=self.crossing)
        self.smallest, self.largest = self.limits["smallest"], self.limits["largest"]
        self.merge_from, self.merge_to = (None, None)
        if len(indices) == 1:
            self.merge_from, self.merge_to = merge_window(
                pattern, indices[0], self.mode, self.limits, check_crossing=self.crossing)
        self.blocked = None
        return True

    def resolve_target(self, project):
        """The corners this run treats: the ones the tool took, or the selection."""
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
        """Take the corner under the pointer; a click inside a selection keeps it."""
        hover = context.scene.qmyi.hover_object
        # The member under the pointer is where the run works: a copy does not
        # share the transform of the panel that owns the chain.
        panel = global_data.temp_draw_manager.picked_pattern() or owner_pattern(hover)
        if not isinstance(hover, Vertex2D) or panel is None:
            self.report({'INFO'}, "click a corner of the outline")
            return False
        if not geometry.is_outline_vertex(hover):
            self.report({'INFO'}, "that point is in the middle of an edge, not a corner")
            return False
        self.pattern_name = panel.name
        if hover.is_selected and len(project.selected_vertices) > 1:
            indices = [vertex.get_index()  # the click landed inside a selection
                       for vertex in project.get_selected_objects_by_mode("EDGE", strict=False)
                       if isinstance(vertex, Vertex2D) and geometry.is_outline_vertex(vertex)
                       and owner_pattern(vertex) == panel]
            self.target_vertices = ",".join(str(index) for index in sorted(indices))
            return True
        select_vertices(project, [hover])
        self.target_vertices = str(hover.get_index())
        return True

    def modal(self, context: Context, event: Event):
        if event.type == 'MOUSEMOVE':
            self.drag(context, event)
            return {'RUNNING_MODAL'}
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'RELEASE':
            result = self.finish(context)   # press, drag, release: this applies the radius
            if result == {'FINISHED'}:
                show_redo_panel(context)
            return result
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.cleanup(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def clamp(self, radius) -> float:
        """The nearest radius this corner can write."""
        radius = max(float(radius), 0.0)
        if self.merge_to is None:
            return min(radius, self.largest)
        radius = min(radius, self.merge_to)
        if self.largest < radius < self.merge_from:  # nothing in the gap is writeable
            return (self.largest if radius - self.largest <= self.merge_from - radius
                    else self.merge_from)
        return radius

    def drag(self, context: Context, event: Event) -> None:
        """Follow the pointer, as an offset from the radius the drag started at."""
        radius = self.clamp(self.start_radius + self.pointer_distance(context, event)
                            - self.start_distance)
        if abs(radius - self.radius) < 1e-4:
            return
        self.radius = radius
        self.refresh_preview(context)

    def pointer_distance(self, context: Context, event: Event) -> float:
        """How far the pointer is from the corner, in the panel's own space."""
        position = region2view_coord(context, (event.mouse_region_x, event.mouse_region_y))
        point = np.asarray(self.pattern.view_to_pattern_pos(position), dtype=np.float64)
        return float(np.hypot(*(point - self.corner)))

    def refresh_preview(self, context: Context) -> None:
        """Draw the arc this radius would write, or hold the last one and say why."""
        manager = global_data.temp_draw_manager
        if self.radius < self.smallest:
            self.noop, self.blocked = True, None  # nothing drawn, nothing applied
            if manager is not None:
                manager.clear_tool_preview()
            self.set_status(context, None)
        else:
            self.noop = False
            try:
                if self.merge_to is not None and self.radius >= self.merge_from - 1e-9:
                    plan = plan_corner_merge(self.pattern, self.indices[0], radius=self.radius,
                                             mode=self.mode, check_crossing=self.crossing)
                else:
                    # The radii this corner takes were read once, before the drag:
                    # measuring them again on every mouse move would run the
                    # crossing test again for every position of the pointer.
                    plan = plan_corner(self.pattern, self.indices, radius=self.radius,
                                       mode=self.mode, check_crossing=self.crossing,
                                       layout=self.limits)
            except geometry.GeometryRefused as refused:
                self.blocked = refused
            else:
                self.blocked = None
                self.draw_preview(context, plan)
        if context.area is not None:
            context.area.tag_redraw()

    def draw_preview(self, context: Context, plan) -> None:
        """Draw every arc that would be written, and its tangent lengths."""
        manager = global_data.temp_draw_manager
        if manager is None:
            return
        manager.clear_tool_preview()
        for entry in plan["entries"]:  # loop: one previewed corner per entry
            points = [self.pattern.pattern_to_view_pos(point) for point in entry["arc"]["points"]]
            for index in range(len(points) - 1):  # loop: one segment per pair
                manager.add_tool_line(points[index], points[index + 1])
            corner = self.pattern.pattern_to_view_pos(entry["point"])
            for tangent in (entry["tangent1"], entry["tangent2"]):
                manager.add_tool_line(corner, self.pattern.pattern_to_view_pos(tangent))
        manager.set_tool_points([(self.pattern, entry["point"], "target")  # the treated corner
                                 for entry in plan["entries"]])
        self.set_status(context, plan)

    def set_status(self, context: Context, plan) -> None:
        workspace = getattr(context, "workspace", None)
        if workspace is None:
            return
        if plan is None:
            text = (f"{self.mode.lower()} corner: {self.radius:.3f} mm is below the smallest "
                    f"that fits ({self.smallest:.3f} mm) - nothing will be applied")
        elif plan.get("merged"):
            text = (f"{self.mode.lower()} corner: merged at {plan['radius']:.3f} mm - the arc "
                    "ends on the far vertex of a consumed edge - left click to apply")
        else:
            text = (f"{self.mode.lower()} corner: {self.radius:.3f} mm (fits "
                    f"{plan['smallest_radius']:.3f} to {plan['largest_radius']:.3f}) - move to "
                    "size, left click to apply")
        workspace.status_text_set(text)

    def finish(self, context: Context):
        if self.noop:
            self.report({'INFO'}, "the radius is below what this corner can take: "
                                  "nothing was changed")
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
        """Apply the radius, clamped into a range this corner can write."""
        try:
            if not self.prepare(context):
                return {'CANCELLED'}
            if float(self.radius) < self.smallest:
                # Finished with nothing done: on a re-run Blender rolls the
                # operator's own step back first, and a step that cancels keeps
                # the previous result instead of leaving the panel alone.
                self.report({'INFO'}, "the radius is below what this corner can take: "
                                      "nothing was changed")
                return {'FINISHED'}
            self.radius = self.clamp(self.radius)
            report = corner_vertices(
                self.pattern, self.indices, radius=self.radius, mode=self.mode,
                merge=(self.merge_to is not None and self.radius >= self.merge_from - 1e-9),
                check_crossing=self.crossing)
        except geometry.GeometryRefused as refused:
            return self.refuse(refused)
        if report.get("merged"):
            # The run removed the vertex the pointer stood on, so the hover the
            # drawing pass keeps names something that is gone.
            qmyi = getattr(context.scene, "qmyi", None)
            if qmyi is not None:
                qmyi.set_hover_object(None)
        self.project.clear_edge_finder()  # the outline moved, so the snap finder is stale
        select_edges(self.project, report["corner_uuids"])
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
    copies = f", with {report['copies']} linked copies" if report["copies"] else ""
    seams = (f", {report['sewings_moved']} seam end(s) moved" if report["sewings_moved"] else "")
    fit = f", {len(report['warnings'])} piece(s) not fitted" if report["warnings"] else ""
    return (f"{done[report['mode']]} {len(report['corners'])} corner(s) of "
            f"{report['panel']} at {report['radius']:.3f} mm{copies}{seams}{fit}")


# --- the corner's own measurement, from the curves to the radii it takes


def selected_corner_run(project):
    """The outline corners the selection names, as (panel, indices)."""
    uuids = [entry.uuid for entry in project.selected_vertices]
    if not uuids:
        raise geometry.GeometryRefused("no vertex is selected",
                                       "select the corner of the outline to treat")
    vertices = [_outline_vertex(uuid_value) for uuid_value in uuids]
    vertices = [vertex for vertex in vertices if vertex is not None]
    if len(vertices) < len(uuids):
        # The identity map can be empty - a fresh session, an undo - while the
        # selection still names its elements: rebuild it and read again.
        refresh_all_uuids()
        vertices = [vertex for vertex in
                    (_outline_vertex(uuid_value) for uuid_value in uuids)
                    if vertex is not None]
    if not vertices:
        raise geometry.GeometryRefused("no corner of an outline is selected",
                                       "a point in the middle of an edge is not a corner")
    panel = owner_pattern(vertices[0])
    if any(owner_pattern(vertex) != panel for vertex in vertices):
        raise geometry.GeometryRefused("the selected vertices are on more than one panel",
                                       "treat the corners of one panel at a time")
    return panel, sorted({vertex.get_index() for vertex in vertices})


def _outline_vertex(uuid_value):
    """The outline vertex this identity names, or None if it is gone."""
    try:
        obj = global_data.get_obj_by_uuid(uuid_value, check_uuid=True)
    except Exception:
        return None
    return obj if geometry.is_outline_vertex(obj) else None


def _tangent_at(points, backwards) -> np.ndarray:
    """The direction the curve travels in at the corner end of an edge.

    The samples next to the corner are walked inwards until two of them differ,
    so a straight edge's tangent is not quantised by its sampling.
    """
    corner = np.asarray(points[-1] if backwards else points[0], dtype=np.float64)
    order = range(len(points) - 2, -1, -1) if backwards else range(1, len(points))
    for index in order:  # loop: one sample step inward
        other = np.asarray(points[index], dtype=np.float64)
        delta = corner - other if backwards else other - corner
        if float(np.hypot(*delta)) > 1e-9:
            return geometry._unit(delta)
    return geometry._unit(np.asarray(points[-1], dtype=np.float64)
                          - np.asarray(points[0], dtype=np.float64))


def _edge_points(pattern, index, edges=None) -> np.ndarray:
    """An edge's sampled polyline, refreshed if it has none."""
    edges = pattern.edges if edges is None else edges
    points = edges[index].render_points
    if points is None or len(points) < 2:  # the corner measures the curve as drawn
        pattern.sketch.update()
        points = edges[index].render_points
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or len(points) < 2:
        raise geometry.GeometryRefused(
            f"an edge at vertex {index} of {pattern.name!r} has no shape",
            "rebuild the panel's geometry first")
    return points


def _adjacency(pattern, index):
    """The edge arriving at one vertex and the edge leaving it, with their chain."""
    arriving, leaving = [], []
    chains = [(None, pattern.edges)] + [(position, line.edges) for position, line
                                        in enumerate(pattern.internal_lines)]
    for line_index, edges in chains:  # loop: one chain, the outline or a line
        for edge in edges:  # loop: one look per edge of this chain
            if edge.vertex_index[1] == index:
                arriving.append((edge, line_index))
            if edge.vertex_index[0] == index:
                leaving.append((edge, line_index))
    if len(arriving) == 1 and len(leaving) == 1:
        (prev_edge, prev_home), (next_edge, next_home) = arriving[0], leaving[0]
        if prev_home == next_home:
            return prev_edge, next_edge, prev_home
        raise geometry.GeometryRefused(
            f"vertex {index} of {pattern.name!r} is where the outline meets an internal line",
            "treating such a corner is not offered")
    raise geometry.GeometryRefused(
        f"vertex {index} of {pattern.name!r} is not a corner",
        f"a corner has one edge arriving and one leaving it; this vertex has "
        f"{len(arriving)} arriving and {len(leaving)} leaving")


def _corner_table(pattern, index, winding) -> dict:
    """What the two edges at one vertex say about treating that corner."""
    vertex = pattern.vertices[index]
    prev_edge, next_edge, line_index = _adjacency(pattern, index)
    edges = (pattern.edges if line_index is None
             else pattern.internal_lines[line_index].edges)
    prev_points = _edge_points(pattern, prev_edge.get_index(), edges)
    next_points = _edge_points(pattern, next_edge.get_index(), edges)
    tangent_in = _tangent_at(prev_points, backwards=True)
    tangent_out = _tangent_at(next_points, backwards=False)
    turn = math.atan2(geometry._cross(tangent_in, tangent_out),
                      float(np.dot(tangent_in, tangent_out)))
    # A counter-clockwise outline turns left at a convex corner and right at a
    # reflex one, which is what makes a reflex interior angle exceed a half turn.
    angle = math.pi - winding * turn
    if abs(angle - math.pi) < STRAIGHT_CORNER_EPS:
        raise geometry.GeometryRefused(
            f"the outline is straight at vertex {index} of {pattern.name!r}",
            "the two edges are collinear there, so there is no corner to treat")
    return {
        "index": index, "line_index": line_index, "angle": angle,
        "point": np.array((float(vertex.co[0]), float(vertex.co[1])), dtype=np.float64),
        # The tangent length one millimetre of radius costs, the same at a reflex
        # corner, where the arc is tangent to the same two edges.
        "factor": 1.0 / abs(math.tan(angle / 2.0)),
        "prev_index": prev_edge.get_index(), "next_index": next_edge.get_index(),
        "prev_uuid": prev_edge.global_uuid, "next_uuid": next_edge.global_uuid,
        "prev_length": polyline_length(prev_points),
        "next_length": polyline_length(next_points),
        "prev_points": prev_points, "next_points": next_points,
        "tangent_in": tangent_in, "tangent_out": tangent_out,
    }


def _mirror_across(start, end, point) -> np.ndarray:
    """`point` reflected across the line through `start` and `end`."""
    direction = geometry._unit(np.asarray(end) - np.asarray(start))
    offset = np.asarray(point, dtype=np.float64) - np.asarray(start, dtype=np.float64)
    along = float(np.dot(offset, direction)) * direction
    return np.asarray(start, dtype=np.float64) + along - (offset - along)


def _corner_arc(start, end, centre, radius, mode) -> dict:
    """What joins two points of a corner: a straight edge, or the arc between them."""
    if mode == "CONCAVE":  # the same arc mirrored across the chord
        centre = _mirror_across(start, end, centre)
    if mode == "CHAMFER":
        return {"points": np.linspace(start, end, 32, dtype=np.float64),
                "handle1": None, "handle2": None}
    return geometry._arc_between(start, end, centre, radius)


def _arc(entry, radius, mode) -> dict:
    """The arc that replaces one corner: its centre, handles and sampled points."""
    bisector = geometry._unit(geometry._unit(-entry["tangent_in"])
                              + geometry._unit(entry["tangent_out"]))
    centre = entry["point"] + bisector * (radius / math.sin(entry["angle"] / 2.0))
    return _corner_arc(entry["tangent1"], entry["tangent2"], centre, radius, mode)


def _corner_geometry(entries, radius, mode) -> None:
    """Fill in each entry's tangent point on both edges, and its arc."""
    for entry in entries:  # loop: one arc per treated corner
        entry["tangent"] = radius * entry["factor"]
        entry["tangent1"] = geometry._point_on(entry["prev_points"],
                                               entry["prev_length"] - entry["tangent"])
        entry["tangent2"] = geometry._point_on(entry["next_points"], entry["tangent"])
        entry["arc"] = _arc(entry, radius, mode)


def _corner_trims(entries) -> dict:
    """How much each touched edge loses at each end, by uuid."""
    trims = {}
    for entry in entries:  # loop: the two edges of one treated corner
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


def _joined(chunks) -> np.ndarray:
    """The chunks as one polyline, with repeated points dropped."""
    # A repeated point is a zero-length segment, which the crossing test does not
    # define: the outline the panel samples never repeats a point.
    candidate = np.concatenate(chunks, dtype=np.float64)
    keep = np.ones(len(candidate), dtype=bool)
    keep[1:] = np.linalg.norm(np.diff(candidate, axis=0), axis=1) > 1e-9
    return candidate[keep]


def corner_outline(pattern, entries, trims) -> np.ndarray:
    """The outline the corner treatment would write, as one closed polyline."""
    chunks = []
    for edge in pattern.edges:  # loop: one edge of the outline
        uuid_value = edge.global_uuid
        trim = trims.get(uuid_value)
        points = (np.asarray(edge.render_points, dtype=np.float64) if trim is None
                  else _corner_piece(trim))
        chunks.append(points[:-1])
        for corner in entries:  # loop: one arc per corner on this edge
            if corner["prev_uuid"] == uuid_value:
                chunks.append(corner["arc"]["points"][:-1])
    return _joined(chunks)


def _check_corner_outline(pattern, entries, trims) -> None:
    """Refuse a treatment whose outline would cross itself."""
    # Only called while the scene's Check Self-Intersection switch is on, and the
    # refusal names that switch: whoever wants the treatment anyway turns it off.
    candidate = corner_outline(pattern, entries, trims)
    if len(candidate) < 3:
        return
    intersected, crossing = boundary_self_intersection(candidate.astype(np.float32))
    if intersected:
        where = (f"the crossing is at ({crossing[0]:.1f}, {crossing[1]:.1f}) mm"
                 if crossing else "the outline is too small to enclose an area")
        raise geometry.GeometryRefused(
            "the corner would make the outline cross itself", where,
            "a smaller radius, or treating fewer corners at once, keeps the outline simple",
            "turn off Check Self-Intersection in the Pattern panel to treat it anyway")


def _crossing_limit(crosses, floor, ceiling):
    """The largest radius in ``[floor, ceiling]`` that does not cross, or None.

    Bisection: whether a radius crosses is answered by building its outline and
    testing it. `None` means every radius in the range crosses.
    """
    if not crosses(ceiling):
        return ceiling
    if ceiling <= floor:
        return None
    low, high = floor, ceiling
    for _ in range(16):  # loop: one halving per step
        middle = (low + high) / 2.0
        if crosses(middle):
            high = middle
        else:
            low = middle
    return None if crosses(low) else low


def _corner_crosses(pattern, entries, mode, radius) -> bool:
    """Whether the corner treatment at this radius would cross the outline."""
    trial = [dict(entry) for entry in entries]
    _corner_geometry(trial, radius, mode)
    try:
        _check_corner_outline(pattern, trial, _corner_trims(trial))
        return False
    except geometry.GeometryRefused:
        return True


def _merge_crosses(pattern, vertex_index, mode, radius) -> bool:
    """Whether the merge at this radius would cross the outline."""
    try:
        plan_corner_merge(pattern, vertex_index, radius=radius, mode=mode)
        return False
    except geometry.GeometryRefused:
        # A merge is refused either for a crossing or for two edges that give the
        # arc no centre; a caller asking how far it may be pulled wants neither.
        return True


def merge_window(pattern, vertex_index, mode, limits, *, check_crossing=True):
    """The radii that pull this corner to the end: ``(first, last)``.

    From `first` - the radius whose tangent reaches the shorter edge's far vertex
    - on, at least one side merges; `last` is the largest merge whose outline
    stays simple while the crossing check is on, which is as far as a drag may go.
    ``(None, None)`` means no merge can be written here.
    """
    entry = limits["entries"][0]
    first = min(entry["prev_length"], entry["next_length"]) / entry["factor"]
    last = max(entry["prev_length"], entry["next_length"]) / entry["factor"]
    if check_crossing:
        last = _crossing_limit(
            lambda radius: _merge_crosses(pattern, vertex_index, mode, radius), first, last)
        if last is None:
            return None, None
    return (None, None) if last < first - 1e-9 else (first, last)


def corner_limits(pattern, vertex_indices, *, mode="ROUND", check_crossing=True) -> dict:
    """The radii a corner run accepts, without writing anything.

    Every treated corner takes `radius * factor` from each of its two edges, so
    two corners on one edge share it. The largest radius is what the edges allow
    less `CORNER_EDGE_MARGIN_MM` at each end - cut back to the largest whose
    outline stays simple while the crossing check is on - and the smallest leaves
    a piece above the merge threshold.
    """
    if mode not in CORNER_MODES:
        raise geometry.GeometryRefused(f"unknown corner mode {mode!r}",
                                       f"use one of {', '.join(CORNER_MODES)}")
    if len(pattern.edges) < 3:
        raise geometry.GeometryRefused(
            f"{pattern.name!r} has {len(pattern.edges)} edge(s)",
            "a corner needs an outline with at least three edges")
    order = sorted({int(index) for index in vertex_indices})
    if not order:
        raise geometry.GeometryRefused("no vertex is selected", "select the corner to treat")
    for index in order:  # loop: one index check per treated corner
        if not 0 <= index < len(pattern.vertices):
            raise geometry.GeometryRefused(f"{pattern.name!r} has no vertex {index}",
                                           f"it has {len(pattern.vertices)} vertices")
    geometry._ensure_shape(pattern, range(len(pattern.edges)))
    winding = 1.0 if pattern.calc_area() >= 0.0 else -1.0
    entries = [_corner_table(pattern, index, winding) for index in order]
    homes = {entry["line_index"] for entry in entries}
    if len(homes) > 1:
        raise geometry.GeometryRefused(
            f"{pattern.name!r} has corners of the outline and of an internal line "
            f"selected together",
            "treat the corners of the outline, or of one line, at a time")
    line_index = next(iter(homes))
    if line_index is not None:
        edges = pattern.internal_lines[line_index].edges
        geometry._ensure_shape(pattern, range(len(edges)), edges)
    # loop: the two edges of one corner per entry - how much of each edge this
    # run's treated corners share, after the margin each end keeps.
    budgets = {}
    for entry in entries:
        for uuid_value, length in ((entry["prev_uuid"], entry["prev_length"]),
                                   (entry["next_uuid"], entry["next_length"])):
            usable = max(length - CORNER_EDGE_MARGIN_MM, 0.0)
            held, factors = budgets.get(uuid_value, (usable, 0.0))
            budgets[uuid_value] = (min(held, usable), factors + entry["factor"])
    limits = {entry["index"]: min(budgets[uuid][0] / budgets[uuid][1]
                                  for uuid in (entry["prev_uuid"], entry["next_uuid"]))
              for entry in entries}
    smallest = max(geometry.MERGE_THRESHOLD_MM / entry["factor"] for entry in entries)
    ceiling = min(limits.values())
    if ceiling <= 0.0 or ceiling < smallest:
        worst = min(limits, key=lambda index: limits[index])
        shortest = min(entry["prev_length"] for entry in entries)
        raise geometry.GeometryRefused(
            f"the edges next to vertex {worst} of {pattern.name!r} are too short to treat",
            f"the shortest one is {shortest:.3f} mm, and a corner needs "
            f"{CORNER_EDGE_MARGIN_MM:g} mm left on each side of it")
    if line_index is not None or not check_crossing:
        largest = ceiling
    else:
        largest = _crossing_limit(
            lambda radius: _corner_crosses(pattern, entries, mode, radius), 0.0, ceiling)
        largest = 0.0 if largest is None else largest  # a crossing outline: nothing to treat
    return {"pattern": pattern, "entries": entries, "order": order, "limits": limits,
            "margin": CORNER_EDGE_MARGIN_MM, "smallest": smallest,
            "line_index": line_index, "largest": largest}


def plan_corner(pattern, vertex_indices, *, radius, mode="ROUND",
                check_crossing=True, layout=None) -> dict:
    """Where the corner treatment would land, without writing anything.

    The measurement the command applies, so a preview and the command cannot
    disagree.
    """
    layout = layout or corner_limits(pattern, vertex_indices, mode=mode,
                                     check_crossing=check_crossing)
    radius_value = float(radius)
    smallest, largest = layout["smallest"], layout["largest"]
    if radius_value <= 0.0:
        raise geometry.GeometryRefused(
            f"a radius of {radius_value:g} mm would not change the corner",
            "give a radius greater than zero")
    if radius_value > largest + 1e-9:
        worst = min(layout["limits"], key=lambda index: layout["limits"][index])
        raise geometry.GeometryRefused(
            f"a radius of {radius_value:g} mm does not fit the corner at vertex {worst}",
            f"the largest radius that fits is {largest:.3f} mm",
            "the tangent length has to fit the two edges, which two corners on one "
            "edge share, and the result has to stay a simple outline")
    if radius_value < smallest - 1e-9:
        raise geometry.GeometryRefused(
            f"a radius of {radius_value:g} mm is too small to write",
            f"the smallest radius this corner can take is {smallest:.3f} mm",
            f"a shorter tangent would leave a piece below {geometry.MERGE_THRESHOLD_MM:g} mm")
    entries = layout["entries"]
    _corner_geometry(entries, radius_value, mode)
    trims = _corner_trims(entries)
    if check_crossing:
        _check_corner_outline(pattern, entries, trims)
    return {"pattern": pattern, "entries": entries, "trims": trims, "mode": mode,
            "radius": radius_value, "largest_radius": largest,
            "smallest_radius": smallest}


def plan_corner_merge(pattern, vertex_index, *, radius, mode="ROUND",
                      check_crossing=True) -> dict:
    """The corner pulled to the very end, one side at a time.

    The tangent length follows the radius like any corner's, and each side merges
    when the tangent reaches that side's own far vertex - that edge is consumed
    and the arc ends on the vertex beyond it - while the other side keeps its trim
    until the tangent reaches its end too. Both ends of the arc are the points the
    written outline is left with, read where they are rather than extrapolated
    along the tangents: on a curved edge the far vertex is not on the ray the
    corner measures in.
    """
    if mode not in CORNER_MODES:
        raise geometry.GeometryRefused(f"unknown corner mode {mode!r}",
                                       f"use one of {', '.join(CORNER_MODES)}")
    geometry._ensure_shape(pattern, range(len(pattern.edges)))
    winding = 1.0 if pattern.calc_area() >= 0.0 else -1.0
    entry = _corner_table(pattern, int(vertex_index), winding)
    edges = (pattern.edges if entry["line_index"] is None
             else pattern.internal_lines[entry["line_index"]].edges)
    up = -entry["tangent_in"]   # the ray from the corner to the first far vertex
    out = entry["tangent_out"]  # ... and to the second
    cos_a = float(np.dot(up, out))
    prev_length, next_length = entry["prev_length"], entry["next_length"]
    far_prev = np.asarray(edges[entry["prev_index"]].vertex0.co, dtype=np.float64)
    far_next = np.asarray(edges[entry["next_index"]].vertex1.co, dtype=np.float64)
    normal_next = geometry._unit(up - cos_a * out)  # inward normals: one per ray,
    normal_prev = geometry._unit(out - cos_a * up)  # each pointing at the other
    tangent = min(max(float(radius), 0.0) * entry["factor"], max(prev_length, next_length))
    consume_prev = tangent >= prev_length - 1e-9
    consume_next = tangent >= next_length - 1e-9
    if not consume_prev and not consume_next:
        # Not a merge at all: the normal command is what treats this corner.
        raise geometry.GeometryRefused(
            f"a radius of {float(radius):g} mm does not reach either edge's end",
            f"a corner merges when its tangent reaches {min(prev_length, next_length):g} mm",
            f"the largest radius that fits without merging is "
            f"{min(prev_length, next_length) / entry['factor']:.3f} mm")
    # What each side is left with: its own far vertex where the tangent reached
    # it, and its tangent point on the curve where it did not.
    trim_prev = far_prev if consume_prev else geometry._point_on(
        entry["prev_points"], prev_length - tangent)
    trim_next = far_next if consume_next else geometry._point_on(
        entry["next_points"], tangent)
    # The circle tangent to one edge at one end of the arc and through the other
    # end. A corner both of whose sides merge is tangent at the farther vertex,
    # which is the same construction: the one-sided cases are its two halves.
    if consume_prev and consume_next:
        if next_length >= prev_length:
            base, normal, other = far_next, normal_next, far_prev
        else:
            base, normal, other = far_prev, normal_prev, far_next
    elif consume_prev:
        base, normal, other = trim_next, normal_next, far_prev
    else:
        base, normal, other = trim_prev, normal_prev, far_next
    offset = np.asarray(other, dtype=np.float64) - np.asarray(base, dtype=np.float64)
    reach = float(np.dot(normal, offset))
    if reach <= 1e-9:
        raise geometry.GeometryRefused(
            f"the corner at vertex {vertex_index} of {pattern.name!r} cannot be merged",
            "the two edges are too close to a straight line to give the arc a centre")
    radius_value = float(np.dot(offset, offset)) / (2.0 * reach)
    centre = np.asarray(base, dtype=np.float64) + normal * radius_value
    start, end = trim_prev, trim_next
    arc = _corner_arc(start, end, centre, radius_value, mode)
    entry.update({"tangent": tangent, "tangent1": start, "tangent2": end,
                  "consume_prev": consume_prev, "consume_next": consume_next,
                  "arc": arc})
    if check_crossing:
        candidate = _merged_outline(pattern, entry)
        if len(candidate) >= 3:
            intersected, crossing = boundary_self_intersection(candidate.astype(np.float32))
            if intersected:
                where = (f"the crossing is at ({crossing[0]:.1f}, {crossing[1]:.1f}) mm"
                         if crossing else "the outline is too small to enclose an area")
                raise geometry.GeometryRefused(
                    "the merged corner would make the outline cross itself", where,
                    "turn off Check Self-Intersection in the Pattern panel to merge it anyway")
    return {"pattern": pattern, "entries": [entry], "trims": _corner_trims([entry]),
            "mode": mode,
            "radius": radius_value, "smallest_radius": 0.0,
            "largest_radius": radius_value, "merged": True}


def _merged_outline(pattern, entry) -> np.ndarray:
    """The corner's own chain with the merge in it, as one polyline.

    A consumed side is skipped - the arc stands in for it - and a side the
    tangent has not reached keeps the part of itself the corner leaves.
    """
    edges = (pattern.edges if entry["line_index"] is None
             else pattern.internal_lines[entry["line_index"]].edges)
    chunks = []
    for edge in edges:  # loop: one edge of the corner's chain
        uuid_value = edge.global_uuid
        points = edge.render_points
        if uuid_value == entry["prev_uuid"]:
            if not entry["consume_prev"]:
                chunks.append(slice_by_arc_length(np.asarray(points, dtype=np.float64),
                                                  0.0,
                                                  entry["prev_length"]
                                                  - entry["tangent"])[:-1])
        elif uuid_value == entry["next_uuid"]:
            chunks.append(entry["arc"]["points"][:-1])
            if not entry["consume_next"]:
                chunks.append(slice_by_arc_length(np.asarray(points, dtype=np.float64),
                                                  entry["tangent"],
                                                  entry["next_length"])[:-1])
        elif points is None:
            return np.zeros((0, 2), dtype=np.float64)
        else:
            chunks.append(np.asarray(points, dtype=np.float64)[:-1])
    return _joined(chunks)


# --- the two writes: a treated corner keeps the vertex, a merged one drops it


def _write_arc(edge, arc, mode) -> None:
    """Write the corner edge's own curve: a straight edge, or the arc as a Bezier."""
    if mode == "CHAMFER":
        edge.set_curve("straight")
    else:
        # Plain tuples: the writer tests the handles for a value, and an array has
        # no truth value.
        edge.set_curve("bezier",
                       handle1=(float(arc["handle1"][0]), float(arc["handle1"][1])),
                       handle2=(float(arc["handle2"][0]), float(arc["handle2"][1])),
                       handle1_type="FREE", handle2_type="FREE")
    edge.update()


def _refresh_ids(pattern) -> None:
    """Name the wrappers the collections hold now, after a structural write."""
    pattern.refresh_collection_uuid(pattern.vertices)
    pattern.refresh_collection_uuid(pattern.edges)
    for line in pattern.internal_lines:  # loop: one collection per line
        pattern.refresh_collection_uuid(line.edges)


def _shift_vertex_index(edge, removed_index) -> None:
    """Close the gap a removed vertex left in the ends of an edge."""
    for slot in (0, 1):
        if int(edge.vertex_index[slot]) > removed_index:
            edge.vertex_index[slot] = int(edge.vertex_index[slot]) - 1


def _finish_run(pattern, ends, pieces, warnings) -> dict:
    """Mark the write, re-home the seams on the touched edges, and mesh.

    The sections are rebuilt before the seams move, so the sampling pass and the
    C++ intersect pass both read chains that match the topology as it stands. One
    Sketch serves the whole chain, so the mesh step is the Sketch's: every member
    is meshed, since a member left marked would draw the shape it used to have.
    """
    pattern.mark_geometry_changed()
    geometry._resample(pattern)
    moved = geometry._remap_sewing_ends_on(pattern, ends, pieces, trimmed=True)
    relinked = geometry._mark_sewings(pattern, ends)
    pattern.require_sketch().rebuild_meshes()
    return {"warnings": warnings, "sewings_moved": moved, "sewings_marked": relinked}


def _write_corners(pattern, plan) -> dict:
    """Write the corners of one panel, and return what happened.

    A corner trims its two sides to their tangent points and joins them with the
    arc. A side whose tangent point is its own far vertex is *consumed* - the
    merge case: that edge leaves, the arc ends on the vertex beyond it, and the
    corner vertex goes with the first side that merges. A treated corner keeps its
    vertex as the first tangent point and only gains the second. Everything a
    removal has to read is read before the removals, since they retire it.
    """
    entries, trims = plan["entries"], plan["trims"]
    merge = plan.get("merged", False)
    roles = ("prev", "next")
    labels = {"prev": "before", "next": "after"}

    def edges_of(entry):
        return (pattern.edges if entry["line_index"] is None
                else pattern.internal_lines[entry["line_index"]].edges)

    def edge_of(entry, role):
        return global_data.get_obj_by_uuid(entry[f"{role}_uuid"], check_uuid=True)

    def consumed(entry, role):
        return bool(entry.get(f"consume_{role}"))

    # The seam endpoints on a touched edge, and the far vertex a consumed side
    # ends on: both are read while the edges they name are still here.
    touched, seen, far = [], set(), {}
    for entry in entries:
        for role in roles:
            if entry[f"{role}_uuid"] not in seen:
                seen.add(entry[f"{role}_uuid"])
                touched.append((entry[f"{role}_uuid"], entry[f"{role}_points"]))
            if consumed(entry, role):
                edge = edges_of(entry)[entry[f"{role}_index"]]
                far[role] = (edge.vertex0 if role == "prev" else edge.vertex1).global_uuid
    ends = geometry._sewing_ends_on(pattern, touched)
    warnings, pieces, corner_uuids = [], {}, []
    if merge:
        # What leaves: the consumed edges, and the corner vertex - nothing
        # references it after its own edges are gone. What the selection names
        # has to leave with them, since the selection outlives its elements.
        entry = entries[0]  # a merge works on one corner at a time
        gone = [int(pattern.vertices[entry["index"]].global_uuid)]
        for role in roles:
            if not consumed(entry, role):
                continue
            edge = edges_of(entry)[entry[f"{role}_index"]]
            gone.append(int(edge.global_uuid))
            gone.extend(int(point.global_uuid)
                        for point in (*edge.handles, *edge.spline_points))
        if global_data.temp_draw_manager is not None:
            global_data.temp_draw_manager.clear()
        pattern.id_data.forget_selected(gone)
        for role in sorted(roles, key=lambda role: entry[f"{role}_index"], reverse=True):
            if consumed(entry, role):
                edges_of(entry).remove(entry[f"{role}_index"])
        pattern.vertices.remove(entry["index"])
        for edge in pattern.sketch.all_edges():  # loop: one shift per survivor
            _shift_vertex_index(edge, entry["index"])
        _refresh_ids(pattern)
    for entry in entries:
        # Each side's end: the far vertex of a consumed edge, the corner vertex
        # itself for a treated corner, and a new vertex for a side kept otherwise.
        for role in roles:
            if consumed(entry, role):
                entry[role] = global_data.get_obj_by_uuid(far[role],
                                                          check_uuid=False).get_index()
            elif not merge and role == "prev":
                pattern.vertices[entry["index"]].co = entry["tangent1"]
                entry[role] = entry["index"]
            else:
                vertex = pattern.add_vertex(tuple(entry[f"tangent{1 if role == 'prev' else 2}"]))
                pattern.vertices[vertex].get_temp_data()
                edge_of(entry, role).vertex_index[0 if role == "next" else 1] = vertex
                entry[role] = vertex
    _refresh_ids(pattern)
    for entry in entries:
        edges = edges_of(entry)
        pattern.refresh_collection_uuid(edges)
        # A kept side keeps the part of its own curve the corner leaves: moving
        # the end of a curved edge would bend the whole of it.
        for role in roles:
            if consumed(entry, role):
                continue
            target, piece = edge_of(entry, role), _corner_piece(trims[entry[f"{role}_uuid"]])
            if target is None or len(piece) == 0:
                continue
            reached, error = geometry._write_piece(target, piece)
            if not reached:
                warnings.append({"edge": target.get_index(), "piece": labels[role],
                                 "error_mm": error})
        # The corner edge belongs right after the edge that arrives at it: the
        # trimmed one where that side was kept, or the edge that used to arrive at
        # the far vertex where it was consumed with it. Read before the edge is
        # added, since adding one retires the wrappers the collection handed out.
        if consumed(entry, "prev"):
            if consumed(entry, "next"):
                position = min(entry["prev_index"], entry["next_index"])
            else:
                before = next((edge for edge in edges
                               if int(edge.vertex_index[1]) == entry["prev"]), None)
                position = 0 if before is None else before.get_index() + 1
        else:
            position = edge_of(entry, "prev").get_index() + 1
        corner = edges.add()
        corner.vertex_index[0] = entry["prev"]  # the arc ends where the outline
        corner.vertex_index[1] = entry["next"]  # is left on each side
        corner.get_temp_data()
        corner_uuids.append(corner.global_uuid)
        _write_arc(corner, entry["arc"], plan["mode"])
        if corner.get_index() != position:
            edges.move(corner.get_index(), position)
        # Where a seam endpoint on a touched edge goes: a consumed edge maps onto
        # the corner treatment, a kept one stays on its own edge, shortened.
        for role in roles:
            if consumed(entry, role):
                pieces[entry[f"{role}_uuid"]] = [(corner.global_uuid, 0.0,
                                                  entry[f"{role}_length"])]
            else:
                pieces[entry[f"{role}_uuid"]] = [(entry[f"{role}_uuid"], 0.0,
                                                  entry["tangent"])]
    _refresh_ids(pattern)
    report = _finish_run(pattern, ends, pieces, warnings)
    report["corners"] = [{"index": entry["index"], "tangent_mm": entry["tangent"],
                          "edge": uuid_value}
                         for entry, uuid_value in zip(entries, corner_uuids)]
    report["corner_uuids"] = corner_uuids
    return report


def corner_vertices(pattern, vertex_indices, *, radius, mode="ROUND",
                    merge=False, check_crossing=True) -> dict:
    """Treat the corners at these vertices, or pull them to the end.

    Without `merge` one corner is replaced by the edge the mode asks for between
    its two tangent points; with it each side merges as the tangent reaches its
    own far vertex, which works on one corner at a time. One Sketch serves the
    whole chain, so the write is made once and this panel meshes from it.
    """
    if merge:
        order = sorted({int(index) for index in vertex_indices})
        if len(order) != 1:
            raise geometry.GeometryRefused(
                "merging a corner works on one corner at a time",
                "treat the other corners with a radius that fits them")
        plan = plan_corner_merge(pattern, order[0], radius=radius, mode=mode,
                                 check_crossing=check_crossing)
        report = _write_corners(pattern, plan)
        report.update({"merged": True, "smallest_radius": 0.0,
                       "largest_radius": plan["radius"]})
    else:
        plan = plan_corner(pattern, vertex_indices, radius=radius, mode=mode,
                           check_crossing=check_crossing)
        report = _write_corners(pattern, plan)
        report.update({"smallest_radius": plan["smallest_radius"],
                       "largest_radius": plan["largest_radius"]})
    report.update({"action": "corner_vertices", "mode": mode, "panel": pattern.name,
                   "radius": plan["radius"],
                   "copies": len(geometry._chain_members(pattern)) - 1})
    return report


register, unregister = register_classes_factory((NODE_OT_corner,))
