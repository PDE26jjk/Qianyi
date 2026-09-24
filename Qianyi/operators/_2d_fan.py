"""Open a fan at a pivot: click the pivot, click the target, drag the angle."""

import math

import numpy as np
from bpy.props import BoolProperty, FloatProperty, FloatVectorProperty, StringProperty
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators
from ..model import pattern_geometry as geometry
from ..model.generator import refuse_generated_edit
from ..model.geometry import Edge2D, Vertex2D
from ..model.model_data import owner_pattern
from ..model.pattern import boundary_self_intersection
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.coords_transform import region2view_coord
from ..utilities.curve_fit import cumulative_length, slice_by_arc_length
from ..utilities.node_tree import get_active_node_tree
from ..utilities.snap import snapped_point, vertex_near_cursor
from ._2d_operator_base import Operator2DBase, select_edges, show_redo_panel

# Anything below this is a click that never opened the fan, not a fan.
SMALLEST_FAN_ANGLE = math.radians(0.5)


class NODE_OT_fan(Operator2DBase):
    """Extend a panel by rotating one half of it about a pivot.

    The two points are chosen one click at a time and neither click takes the
    pointer: the first click on the outline is the pivot, the second is the
    target. Only the angle is a modal drag - it starts on the click that took
    the target, follows the pointer, and applies when the button is released -
    so the view can still be navigated while the points are being chosen, and
    the drag itself is the one step that has to hold the pointer.

    The two points and the angle are the operator's own properties, so Blender's
    adjust-last-operation panel re-runs the command from the state that existed
    before it: a wider or narrower angle rebuilds the fan from the original
    panel rather than opening a second sector.
    """

    bl_idname = Operators.Fan2D
    bl_label = "pivot fan"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    # Transient gesture state, with defaults so a step can never be the first
    # thing to look at a flag that was not set yet.
    blocked = None
    plan = None
    armed = False

    # The two points and the panel are what the redo panel re-runs from: a tool
    # gesture has no selection step of its own, so the operator is the only
    # place that knows what it acted on.
    pivot_location: FloatVectorProperty(name="Pivot", size=2)
    target_location: FloatVectorProperty(name="Target", size=2)
    pattern_name: StringProperty(name="Panel")
    angle: FloatProperty(
        name="Angle",
        description="How far the sector opens, in degrees",
        default=math.radians(30.0),
        min=0.0,
        max=math.pi,
        unit='ROTATION',
        subtype='ANGLE',
    )
    cancel: BoolProperty(
        name="Cancel",
        description="Set by the tool's escape key: forget the points taken so "
                    "far instead of opening a fan",
        default=False,
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context: Context):
        return get_active_node_tree(context) is not None

    def draw(self, context: Context):
        """The adjust-last-operation panel: the angle the run used."""
        self.layout.prop(self, "angle")

    def invoke(self, context: Context, event: Event):
        ensure_edit_mode(context, "EDGE", "EDGE_VERTEX")
        project = get_active_node_tree(context)
        if project is None:
            return {'CANCELLED'}
        manager = global_data.temp_draw_manager
        if manager is not None and event is not None:
            # The point under the pointer: the gizmo writes it on every move,
            # and a click may be the first event of all.
            manager.mouse_location = (event.mouse_region_x, event.mouse_region_y)
        if self.cancel:
            self.forget(context, project)
            self.report({'INFO'}, "the fan was cancelled: nothing was changed")
            return {'CANCELLED'}
        if project.fan_pivot is None:
            if not self.take_click(context, project, "pivot"):
                return {'CANCELLED'}
            # Each click is a new operator instance, so the panel has to be
            # taken from the stored gesture every time it is needed.
            self.pattern_name = project.fan_pivot[0]
            self.report({'INFO'}, "pivot set: click the target on the outline")
            return {'FINISHED'}
        if project.fan_target is None:
            if not self.take_click(context, project, "target"):
                return {'CANCELLED'}
            # The angle is the one step that needs the pointer to itself: it
            # starts here and applies on release.
            self.pivot_location = project.fan_pivot[1]
            self.target_location = project.fan_target[1]
            self.pattern_name = project.fan_pivot[0]
            self.angle = 0.0
            self.plan = None
            self.armed = False
            if manager is not None:
                manager.preview_locked = True
            context.window.cursor_modal_set("CROSSHAIR")
            context.window_manager.modal_handler_add(self)
            self.refresh(context, event)
            return {'RUNNING_MODAL'}
        return {'CANCELLED'}

    def modal(self, context: Context, event: Event):
        if event.type == 'MOUSEMOVE':
            self.refresh(context, event)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if not self.armed:
                # The release of the click that took the target: the gesture
                # goes on until a click of its own.
                self.armed = True
                return {'RUNNING_MODAL'}
            return self.finish(context)
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            project = get_active_node_tree(context)
            if project is not None:
                self.forget(context, project)
            self.report({'INFO'}, "the fan was cancelled: nothing was changed")
            self.cleanup(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def refresh(self, context: Context, event: Event) -> None:
        """Open the fan by the angle the pointer is at, and draw the result."""
        pattern = self.pattern(context)
        if pattern is None:
            # The preview cannot be drawn without the panel, and doing nothing
            # quietly is what makes a broken gesture look like a dead tool.
            self.report({'WARNING'},
                        f"the fan lost the panel it was started on "
                        f"({self.pattern_name!r})")
            return
        self.angle = self.pointer_angle(context, event)
        try:
            plan = plan_fan(pattern, tuple(self.pivot_location),
                                     tuple(self.target_location), angle=self.angle)
        except geometry.GeometryRefused as refused:
            # The fan cannot be opened this wide from here: keep the last shape
            # that works and say the run would be refused as it stands.
            self.blocked = refused
            return
        self.blocked = None
        self.plan = plan
        manager = global_data.temp_draw_manager
        if manager is not None:
            manager.clear_tool_preview()
            manager.set_tool_points([
                (pattern, tuple(self.pivot_location), "pivot"),
                (pattern, tuple(self.target_location), "target")])
            # What the panel would look like: the whole outline the command
            # would leave behind, drawn as one polyline - an outline has a
            # sample per few millimetres, so a segment at a time would crawl.
            outline = fan_preview(plan)
            spots = [pattern.pattern_to_view_pos(spot) for spot in outline]
            spots.append(spots[0])
            manager.set_tool_polyline(spots)
        workspace = getattr(context, "workspace", None)
        if workspace is not None:
            workspace.status_text_set(
                f"fan: angle {math.degrees(self.angle):.1f} degrees "
                f"({plan['added_area']:.0f} mm2 added) - left click to apply, "
                "right click or Esc to cancel")
        if context.area is not None:
            context.area.tag_redraw()

    def finish(self, context: Context):
        if self.blocked is not None:
            result = self.refuse(self.blocked)
        else:
            result = self.execute(context)
        project = get_active_node_tree(context)
        if project is not None:
            self.forget(context, project)
        self.cleanup(context)
        if result == {'FINISHED'}:
            show_redo_panel(context)
        return result

    def forget(self, context: Context, project) -> None:
        """Drop the points the gesture had taken, and its preview with them."""
        project.fan_pivot = None
        project.fan_target = None
        manager = global_data.temp_draw_manager
        if manager is not None:
            manager.clear_tool_preview()
            manager.preview_locked = False
        if context.area is not None:
            context.area.tag_redraw()

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

    def take_click(self, context: Context, project, which) -> bool:
        """Read the point under the pointer as a point on the outline."""
        hover = context.scene.qmyi.hover_object
        manager = global_data.temp_draw_manager
        location = getattr(manager, "mouse_location", None)
        if location is None:
            return False
        if isinstance(hover, Vertex2D) and owner_pattern(hover) is not None:
            # The pointer is on a vertex, and the tool's own preview snaps to
            # vertices: a click there has to take it, or snapping would mean
            # that the point it snaps to is the one point that cannot be used.
            panel = manager.picked_pattern() or project.active_pattern
            point = np.asarray(hover.co, dtype=np.float64)
            vertex = hover.get_index() if geometry.is_outline_vertex(hover) else None
        elif isinstance(hover, Edge2D) and manager.picked_pattern() is not None:
            panel = manager.picked_pattern()
            view = region2view_coord(context, location)
            point = np.asarray(panel.view_to_pattern_pos(view), dtype=np.float64)
            # A click close to a vertex lands on it: the pivot and the target are
            # usually corners, and a corner has to be exact to split the panel
            # the way the fan expects.
            point, vertex = snapped_point(context, panel, point, location)
        else:
            # Nothing under the pointer: take the point the tool's own preview
            # is showing, which is the nearest point of the nearest outline.
            # That is the cyan dot, so a click somewhere near a panel is never
            # answered with a message about not being on one.
            panel, point = self.nearest_outline_point(context, project, location)
            if panel is None:
                return False
            vertex = None
        if which == "pivot":
            project.fan_pivot = (panel.name, (float(point[0]), float(point[1])))
        else:
            stored = project.fan_pivot
            if stored is None or panel.name != stored[0]:
                self.report({'INFO'},
                            "the target has to be on the same panel as the pivot")
                return False
            apart = float(np.hypot(*(point - np.asarray(stored[1], dtype=np.float64))))
            if apart <= geometry.MERGE_THRESHOLD_MM:
                self.report({'INFO'}, "the target has to be away from the pivot")
                return False
            project.fan_target = (panel.name, (float(point[0]), float(point[1])))
        if vertex is not None:
            self.report({'INFO'}, f"snapped to vertex {vertex} of {panel.name}")
        return True

    def pointer_angle(self, context: Context, event: Event) -> float:
        """How far the pointer turns the radius, clockwise from the pivot.

        The rotating half is the one on the right of the radius, so a pointer
        that stays on that side opens the sector by the angle it turned through.
        """
        pattern = self.pattern(context)
        location = pointer_location(context, event)
        if pattern is None or location is None:
            return self.angle
        view = region2view_coord(context, location)
        point = np.asarray(pattern.view_to_pattern_pos(view), dtype=np.float64)
        pivot = np.asarray(self.pivot_location, dtype=np.float64)
        base = np.asarray(self.target_location, dtype=np.float64) - pivot
        here = point - pivot
        if float(np.hypot(*here)) <= 1e-9:
            return 0.0
        turned = -math.atan2(float(np.cross(base, here)), float(np.dot(base, here)))
        return min(max(turned, 0.0), math.pi)

    def nearest_outline_point(self, context: Context, project, location):
        """The point the tool's own preview is showing under the pointer.

        The preview snaps to a vertex and otherwise to the nearest point of the
        nearest outline, so a click that lands on neither still has a point to
        take - the one the user is looking at.
        """
        panel, vertex = find_vertex_under(context, project, location)
        if vertex is not None:
            return panel, np.asarray(vertex.co, dtype=np.float64)
        project.find_nearest_point_on_edge(region2view_coord(context, location))
        if project.nearest_point is None or project.nearest_pattern is None:
            return None, None
        return (project.patterns[project.nearest_pattern],
                np.asarray(project.nearest_point, dtype=np.float64))

    def pattern(self, context: Context):
        """The panel the gesture started on, by name."""
        project = get_active_node_tree(context)
        if project is None:
            return None
        for panel in project.patterns:  # loop: one panel per name check
            if panel.name == self.pattern_name:
                return panel
        return None

    def execute(self, context: Context):
        project = get_active_node_tree(context)
        if project is None:
            return {'CANCELLED'}
        pattern = self.pattern(context)
        if pattern is None:
            self.report({'ERROR'}, f"no panel named {self.pattern_name!r}")
            return {'CANCELLED'}
        if refuse_generated_edit(self, project, pattern):
            return {'CANCELLED'}
        try:
            report = pivot_fan(pattern, tuple(self.pivot_location),
                                        tuple(self.target_location), angle=self.angle)
        except geometry.GeometryRefused as refused:
            return self.refuse(refused)
        # The outline changed, so the finder the tools snap against is stale:
        # without this the next click snaps to the shape that used to be there.
        project.clear_edge_finder()
        select_edges(project, report["arc_uuids"])
        self.report({'INFO'}, describe(report))
        return {'FINISHED'}

    def refuse(self, refused):
        """Report a refusal and its hints, the way every command here does."""
        self.report({'ERROR'}, refused.reason)
        for hint in refused.hints:  # loop: one report line per hint
            self.report({'INFO'}, hint)
        return {'CANCELLED'}


def pointer_location(context: Context, event: Event):
    """Where the pointer is, from the event or from the gizmo's own record."""
    if event is not None:
        return (event.mouse_region_x, event.mouse_region_y)
    manager = global_data.temp_draw_manager
    return getattr(manager, "mouse_location", None)


def find_vertex_under(context: Context, project, cursor):
    """The outline vertex of the project nearest the cursor, within the snap."""
    best = None
    for panel in project.patterns:  # loop: one panel's vertices per search
        near = vertex_near_cursor(context, panel, cursor)
        if near is not None and (best is None or near[1] < best[1]):
            best = (near[0], near[1], panel)
    if best is None:
        return None, None
    return best[2], best[2].vertices[best[0]]


def describe(report) -> str:
    """One line for the info area: what the fan produced."""
    message = (f"opened {report['panel']} by {report['angle_deg']:.1f} degrees "
               f"around a {report['radius_mm']:.1f} mm radius, adding "
               f"{report['added_area_mm2']:.1f} mm2")
    if report["copies"]:
        message += f", with {report['copies']} linked copies"
    if report["sewings_moved"]:
        message += f", {report['sewings_moved']} seam end(s) moved"
    if report["sewings_followed"]:
        message += f", {report['sewings_followed']} seam(s) followed the rotation"
    return message


# --- the command's own computation

FAN_MIN_ANGLE = 1e-9           # a smaller opening adds no sector

def _check_loop_order(pattern) -> None:
    """The outline has to be one closed loop in the edges' own order."""
    count = len(pattern.edges)
    if count < 3:
        raise geometry.GeometryRefused(f"{pattern.name!r} has {count} edge(s)",
                              "an outline needs at least three edges")
    for index in range(count):
        edge = pattern.edges[index]
        following = pattern.edges[(index + 1) % count]
        if edge.vertex_index[1] != following.vertex_index[0]:
            raise geometry.GeometryRefused(
                f"the edges of {pattern.name!r} are not one loop in order",
                "the outline has to be a single closed loop before it is changed")

def _outline_location(pattern, point, what) -> dict:
    """Where a point sits on the outline: the edge, the arc length, the point.

    The point is projected onto the nearest edge; one further from the outline
    than the panel's own sampling step cannot be meant as a point on it.
    """
    point = np.asarray(point, dtype=np.float64)
    if point.shape != (2,):
        raise geometry.GeometryRefused(f"{what} is not a point in the panel's space")
    best = None
    for index in range(len(pattern.edges)):
        points = np.asarray(pattern.edges[index].render_points, dtype=np.float64)
        if points.ndim != 2 or len(points) < 2:
            continue
        lengths = cumulative_length(points)
        starts, spans = points[:-1], points[1:] - points[:-1]
        denominator = (spans * spans).sum(axis=1)
        fraction = np.divide((point - starts) * spans, denominator[:, None],
                             out=np.zeros_like(spans), where=denominator[:, None] > 0.0)
        fraction = np.clip(fraction.sum(axis=1), 0.0, 1.0)
        projected = starts + spans * fraction[:, None]
        distance = np.linalg.norm(projected - point, axis=1)
        step = int(distance.argmin())
        if best is None or distance[step] < best["distance"]:
            best = {"edge": index, "distance": float(distance[step]),
                    "arc": float(lengths[step] + fraction[step]
                                 * (lengths[step + 1] - lengths[step])),
                    "point": projected[step].copy(), "points": points,
                    "length": float(lengths[-1]),
                    # The edge by identity, for a caller that writes later:
                    # splitting an edge inserts a piece right after it, which
                    # moves every index above it.
                    "edge_uuid": pattern.edges[index].global_uuid}
    if best is None:
        raise geometry.GeometryRefused(f"{pattern.name!r} has no outline to measure")
    tolerance = max(float(pattern.granularity), geometry.MERGE_THRESHOLD_MM)
    if best["distance"] > tolerance:
        raise geometry.GeometryRefused(
            f"{what} is {best['distance']:.3f} mm off the outline of {pattern.name!r}",
            f"a point on the outline is within {tolerance:.3f} mm of it")
    return best

def _path_ranges(pattern, start_at, end_at) -> list:
    """The (edge, from arc, to arc) runs of the loop from one point to another."""
    count = len(pattern.edges)
    start_edge, end_edge = start_at["edge"], end_at["edge"]
    if start_edge == end_edge and start_at["arc"] < end_at["arc"]:
        return [(start_edge, start_at["arc"], end_at["arc"])]
    runs = [(start_edge, start_at["arc"], start_at["length"])]
    index, guard = (start_edge + 1) % count, 0
    while index != end_edge and guard <= count:
        edge = pattern.edges[index]
        runs.append((index, 0.0, float(cumulative_length(
            np.asarray(edge.render_points, dtype=np.float64))[-1])))
        index, guard = (index + 1) % count, guard + 1
    if index != end_edge:
        raise geometry.GeometryRefused(f"the outline of {pattern.name!r} is not one loop")
    runs.append((end_edge, 0.0, end_at["arc"]))
    return runs

def _path_samples(pattern, start_at, end_at) -> np.ndarray:
    """The outline samples from one point on it to another, in loop order."""
    pieces = []
    for index, from_arc, to_arc in _path_ranges(pattern, start_at, end_at):
        # A zero-length run is the point the path starts or ends on, which is
        # already in the path: repeating it reads as a self-intersection.
        if to_arc - from_arc <= 1e-9:
            continue
        points = np.asarray(pattern.edges[index].render_points, dtype=np.float64)
        piece = slice_by_arc_length(points, from_arc, to_arc)
        pieces.append(piece if not pieces else piece[1:])
    return np.concatenate(pieces)

def _signed_area(points) -> float:
    """The signed area of a polyline closed back on itself."""
    points = np.asarray(points, dtype=np.float64)
    x, y = points[:, 0], points[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))

def _fan_halves(pattern, pivot_at, target_at) -> dict:
    """Which half of the panel the fan rotates, and which stays put.

    The path on the right of the directed radius rotates: turning it clockwise
    is what opens the sector rather than closing it.
    """
    _check_loop_order(pattern)
    forward = _path_samples(pattern, pivot_at, target_at)
    backward = _path_samples(pattern, target_at, pivot_at)
    direction = target_at["point"] - pivot_at["point"]
    middle = geometry._point_on(forward, float(cumulative_length(forward)[-1]) / 2.0)
    return {"rotates_forward": bool(geometry._cross(direction, middle - pivot_at["point"]) < 0.0),
            "forward_area": _signed_area(forward),
            "backward_area": _signed_area(backward)}

def _check_chord(pattern, pivot_at, target_at) -> None:
    """Refuse a radius whose chord leaves the panel.

    The chord is the two halves' common boundary: if it crosses the outline
    anywhere but at its own two ends, rotating one half would fold the panel onto
    itself. A chord that runs along one edge between the two points is the
    legitimately short way round a bulge.
    """
    first, second = pivot_at["point"], target_at["point"]
    direction = second - first
    same_edge = pivot_at["edge"] == target_at["edge"]
    low, high = sorted((pivot_at["arc"], target_at["arc"]))
    for index in range(len(pattern.edges)):
        points = np.asarray(pattern.edges[index].render_points, dtype=np.float64)
        if points.ndim != 2 or len(points) < 2:
            continue
        lengths = cumulative_length(points)
        starts, spans = points[:-1], points[1:] - points[:-1]
        offset = starts - first
        denominator = direction[0] * spans[:, 1] - direction[1] * spans[:, 0]
        usable = np.abs(denominator) > 1e-12
        along, across = np.zeros_like(denominator), np.zeros_like(denominator)
        along[usable] = ((offset[usable, 0] * spans[usable, 1]
                          - offset[usable, 1] * spans[usable, 0]) / denominator[usable])
        across[usable] = ((offset[usable, 0] * direction[1]
                           - offset[usable, 1] * direction[0]) / denominator[usable])
        hit = (usable & (along >= -1e-9) & (along <= 1.0 + 1e-9)
               & (across >= -1e-9) & (across <= 1.0 + 1e-9))
        for step in np.flatnonzero(hit):
            crossing = starts[step] + spans[step] * across[step]
            if float(np.hypot(*(crossing - first))) <= geometry.MERGE_THRESHOLD_MM:
                continue
            if float(np.hypot(*(crossing - second))) <= geometry.MERGE_THRESHOLD_MM:
                continue
            if same_edge and index == pivot_at["edge"]:
                arc = float(lengths[step] + across[step] * (lengths[step + 1] - lengths[step]))
                if low - geometry.MERGE_THRESHOLD_MM <= arc <= high + geometry.MERGE_THRESHOLD_MM:
                    continue
            raise geometry.GeometryRefused(
                "the radius between the pivot and the target leaves the panel",
                f"it meets the outline at ({crossing[0]:.1f}, {crossing[1]:.1f}) mm, so "
                "the two points are not on the same side of it",
                "pick a target that the straight line from the pivot reaches without "
                "crossing the outline")

def fan_outline(pattern, pivot_at, target_at, halves, arc) -> np.ndarray:
    """The outline the fan would write, as one closed polyline.

    The same assembly the self-crossing test uses, so a preview drawn from this
    is the shape the command would leave behind.
    """
    forward = _path_samples(pattern, pivot_at, target_at)
    backward = _path_samples(pattern, target_at, pivot_at)
    if halves["rotates_forward"]:
        stationary, rotating = backward[::-1], forward
    else:
        stationary, rotating = forward, backward[::-1]
    angle = 0.0 if arc is None else abs(arc["sweep"])
    turned = np.array([_rotate_about(point, pivot_at["point"], -angle)
                       for point in rotating])
    chunks = [stationary]
    if arc is not None:
        chunks.append(arc["points"][::-1][1:])
    chunks.append(turned[::-1][1:])
    candidate = np.concatenate(chunks, dtype=np.float64)
    # The panel samples its outline without repeating the point it closes on.
    if len(candidate) > 1 and float(np.hypot(*(candidate[-1] - candidate[0]))) <= 1e-9:
        candidate = candidate[:-1]
    return candidate

def _check_fan_outline(pattern, pivot_at, target_at, halves, arc) -> None:
    """Refuse a fan whose result would cross itself."""
    candidate = fan_outline(pattern, pivot_at, target_at, halves, arc)
    if len(candidate) < 3:
        return
    intersected, crossing = boundary_self_intersection(candidate.astype(np.float32))
    if intersected:
        where = (f"the crossing is at ({crossing[0]:.1f}, {crossing[1]:.1f}) mm"
                 if crossing else "the outline is too small to enclose an area")
        raise geometry.GeometryRefused("the fan would make the outline cross itself", where,
                              "a smaller angle, or another target, keeps the outline simple")

def fan_preview(plan) -> np.ndarray:
    """The outline a fan plan would write, for a preview to draw."""
    return fan_outline(plan["pattern"], plan["pivot"], plan["target"],
                       plan["halves"], plan["arc"])

def plan_fan(pattern, pivot, target, *, angle) -> dict:
    """What the fan would do, without writing anything.

    `pivot` and `target` are two points on the outline and the distance between
    them is the radius: the chord between them divides the panel, and the half on
    the right of the directed radius rotates rigidly about the pivot by `angle`
    (clockwise, so the sector opens). The chord and the result are tested before
    anything is written.
    """
    angle_value = float(angle)
    if angle_value < -FAN_MIN_ANGLE:
        raise geometry.GeometryRefused(
            f"an angle of {math.degrees(angle_value):.1f} degrees closes the fan",
            "a fan only opens: give an angle of zero or more")
    if angle_value > math.pi + FAN_MIN_ANGLE:
        raise geometry.GeometryRefused(
            f"an angle of {math.degrees(angle_value):.1f} degrees is too wide",
            "the widest fan that stays a simple outline is 180 degrees")
    angle_value = max(angle_value, 0.0)
    geometry._ensure_shape(pattern, range(len(pattern.edges)))
    pivot_at = _outline_location(pattern, pivot, "the pivot")
    target_at = _outline_location(pattern, target, "the target")
    radius = float(np.hypot(*(target_at["point"] - pivot_at["point"])))
    if radius <= geometry.MERGE_THRESHOLD_MM:
        raise geometry.GeometryRefused(
            f"the pivot and the target are {radius:.3f} mm apart",
            f"the radius has to be at least {geometry.MERGE_THRESHOLD_MM:g} mm, so the two points "
            "have to be further apart")
    _check_chord(pattern, pivot_at, target_at)
    halves = _fan_halves(pattern, pivot_at, target_at)
    if min(abs(halves["forward_area"]), abs(halves["backward_area"])) <= geometry.MERGE_THRESHOLD_MM ** 2:
        raise geometry.GeometryRefused(
            "the radius lies along the outline, so it does not divide the panel",
            "give the target on another edge: the radius has to cut the panel into two "
            "halves with material on both sides of it")
    arc = None
    if angle_value > FAN_MIN_ANGLE:
        rotated = _rotate_about(target_at["point"], pivot_at["point"], -angle_value)
        arc = geometry._arc_between(rotated, target_at["point"], pivot_at["point"], radius)
    _check_fan_outline(pattern, pivot_at, target_at, halves, arc)
    return {"pattern": pattern, "pivot": pivot_at, "target": target_at, "radius": radius,
            "angle": angle_value, "added_area": 0.5 * radius * radius * angle_value,
            "rotates_forward": halves["rotates_forward"], "halves": halves, "arc": arc}

def _at_vertex(location) -> bool:
    """Whether a point measured on the outline is already one of its vertices."""
    return (location["arc"] <= geometry.MERGE_THRESHOLD_MM
            or location["length"] - location["arc"] <= geometry.MERGE_THRESHOLD_MM)

def _vertex_at(pattern, point) -> int:
    """The vertex of the outline at this point, as the split left it."""
    point = np.asarray(point, dtype=np.float64)
    best = None
    for index, vertex in enumerate(pattern.vertices):
        distance = float(np.hypot(*(np.asarray(vertex.co, dtype=np.float64) - point)))
        if best is None or distance < best[1]:
            best = (index, distance)
    if best is None or best[1] > geometry.MERGE_THRESHOLD_MM:
        raise geometry.GeometryRefused(
            f"the outline has no vertex within {geometry.MERGE_THRESHOLD_MM:g} mm of the point the "
            "fan pivots on",
            (f"the nearest of its {len(pattern.vertices)} vertices is {best[1]:.3f} mm away"
             if best else "the panel has no vertices"),
            "the panel changed since the fan was measured; run the command again")
    return best[0]

def _loop_edges(pattern, start_vertex, end_vertex) -> list:
    """The edges of the loop from one vertex to another, in loop order."""
    edges = list(pattern.edges)
    starts = {int(edge.vertex_index[0]): index for index, edge in enumerate(edges)}
    if start_vertex not in starts:
        raise geometry.GeometryRefused("the outline does not pass through the pivot")
    path, vertex, guard = [], int(start_vertex), 0
    while vertex != end_vertex and guard <= len(edges):
        index = starts.get(vertex)
        if index is None:
            raise geometry.GeometryRefused(f"the outline of {pattern.name!r} is not one loop")
        path.append(index)
        vertex, guard = int(edges[index].vertex_index[1]), guard + 1
    if vertex != end_vertex:
        raise geometry.GeometryRefused(f"the outline of {pattern.name!r} is not one loop")
    return path

def _sewings_on(pattern, edge_indices) -> int:
    """How many seams have an endpoint on one of these edges."""
    uuids = set(edge_indices)
    count = 0
    for sewing in pattern.project.sewings:
        for side in sewing.sides:
            if side.line1_uuid in uuids or side.line2_uuid in uuids:
                count += 1
                break
    return count


def _edge_index_of(pattern, edge_uuid) -> int:
    """Where an edge sits in the outline now, found by its identity.

    A plan's edge index is the outline as it was before anything was written,
    and splitting an edge inserts its pieces right after it: every index above
    it moves. The write therefore finds each edge again by identity, which is
    what keeps the second of two cuts on the edge it was measured on.
    """
    for index in range(len(pattern.edges)):  # loop: one edge per look
        if pattern.edges[index].global_uuid == edge_uuid:
            return index
    raise geometry.GeometryRefused(
        f"the outline of {pattern.name!r} changed while the fan was written",
        "run the command again")

def _fan_member(pattern, plan) -> dict:
    """Write one member's fan, and return what happened."""
    pivot_at, target_at, angle = plan["pivot"], plan["target"], plan["angle"]
    touched, seen = [], set()
    for index in (pivot_at["edge"], target_at["edge"]):
        if index not in seen:
            seen.add(index)
            touched.append((index, np.asarray(pattern.edges[index].render_points,
                                              dtype=np.float64)))
    ends = geometry._sewing_ends(pattern, touched)
    warnings, pieces, own_points = [], {}, {}
    # The two points become vertices first: everything after this works on the
    # outline the splits produced, which is the outline a seam can point at. A
    # point that is already a vertex is not split again - a cut at either end of
    # an edge would leave a piece of no length behind.
    # Each edge is found again by identity before it is cut, and the pieces are
    # keyed the way the seam remap reads them: by the uuid of the edge that was
    # split.
    if pivot_at["edge"] == target_at["edge"]:
        index = _edge_index_of(pattern, pivot_at["edge_uuid"])
        table = geometry._table(pattern, index)
        cuts = sorted({round(location["arc"], 9) for location in (pivot_at, target_at)
                       if not _at_vertex(location)})
        for location in (pivot_at, target_at):
            own_points[id(location)] = geometry._point_on(table["points"], location["arc"])
        if cuts:
            warnings.extend(geometry._split_edge(pattern, index, cuts, table))
            pieces[pivot_at["edge_uuid"]] = geometry._piece_table(
                pattern, index, geometry._piece_lengths(table["length"], cuts))
    else:
        for location in (pivot_at, target_at):
            index = _edge_index_of(pattern, location["edge_uuid"])
            table = geometry._table(pattern, index)
            own_points[id(location)] = geometry._point_on(table["points"], location["arc"])
            if _at_vertex(location):
                continue
            warnings.extend(geometry._split_edge(pattern, index, [location["arc"]], table))
            pieces[location["edge_uuid"]] = geometry._piece_table(
                pattern, index, geometry._piece_lengths(table["length"], [location["arc"]]))
    pattern.refresh_collection_uuid(pattern.edges)
    pattern.refresh_collection_uuid(pattern.vertices)
    pivot_vertex = _vertex_at(pattern, own_points.get(id(pivot_at), pivot_at["point"]))
    target_vertex = _vertex_at(pattern, own_points.get(id(target_at), target_at["point"]))
    # The rotating half is walked in the loop's own direction, and the target end
    # is the one that leaves the outline: the copy is made for it.
    if plan["rotates_forward"]:
        rotating, detached_at_start = _loop_edges(pattern, pivot_vertex, target_vertex), False
    else:
        rotating, detached_at_start = _loop_edges(pattern, target_vertex, pivot_vertex), True
    rotated_target = pattern.add_vertex(tuple(pattern.vertices[target_vertex].co))
    pattern.vertices[rotated_target].get_temp_data()
    if detached_at_start:
        pattern.edges[rotating[0]].vertex_index[0] = rotated_target
    else:
        pattern.edges[rotating[-1]].vertex_index[1] = rotated_target
    pattern.refresh_collection_uuid(pattern.vertices)
    rotated_vertices = [pattern.edges[index].vertex_index[0] for index in rotating]
    if not detached_at_start:
        rotated_vertices.append(rotated_target)
    for vertex_index in rotated_vertices:
        if vertex_index == pivot_vertex:
            continue  # the pivot is the centre of the rotation: it does not move
        pattern.vertices[vertex_index].co = _rotate_about(
            pattern.vertices[vertex_index].co, pivot_at["point"], -angle)
    for index in rotating:
        edge = pattern.edges[index]
        for handle in (edge.handle1, edge.handle2):
            handle.co = _rotate_about(handle.co, pivot_at["point"], -angle)
        for point in edge.spline_points:
            point.co = _rotate_about(point.co, pivot_at["point"], -angle)
    # Read the rotated edges now: adding the arc edge below inserts a piece and
    # moves the indices above it.
    rotated_uuids = [pattern.edges[index].global_uuid for index in rotating]
    pattern.refresh_collection_uuid(pattern.edges)
    arc_uuid = None
    if plan["arc"] is not None:
        arch = plan["arc"]
        if detached_at_start:
            # The loop reaches the target first, so the arc runs from it to the
            # copy: the same circle, with the handles the other way round.
            start, end = target_vertex, rotated_target
            handle1, handle2 = arch["handle2"], arch["handle1"]
        else:
            start, end = rotated_target, target_vertex
            handle1, handle2 = arch["handle1"], arch["handle2"]
        edge = pattern.add_edge(start, end, update=False)
        arc_uuid = edge.global_uuid
        pattern.refresh_collection_uuid(pattern.edges)
        target_edge = global_data.get_obj_by_uuid(arc_uuid, check_uuid=True)
        target_edge.set_curve("bezier",
                              handle1=(float(handle1[0]), float(handle1[1])),
                              handle2=(float(handle2[0]), float(handle2[1])),
                              handle1_type="FREE", handle2_type="FREE")
        target_edge.update()
        position = rotating[0] if detached_at_start else rotating[-1] + 1
        if target_edge.get_index() != position:
            pattern.edges.move(target_edge.get_index(), position)
        pattern.refresh_collection_uuid(pattern.edges)
    pattern.refresh_collection_uuid(pattern.vertices)
    pattern.mark_geometry_changed()
    moved = geometry._remap_sewing_ends_on(pattern, ends, pieces, trimmed=True)
    relinked = geometry._mark_sewings(pattern, ends)
    # The halves have been turned and the arc edge added, so build the samples
    # from the sections the outline has now before anything measures.
    geometry._resample(pattern)
    # One Sketch serves the whole instance chain, so the fan is one edit for
    # every member: the Sketch builds each of their meshes.
    pattern.require_sketch().rebuild_meshes()
    return {
        "pivot_vertex": pivot_vertex, "target_vertex": target_vertex,
        "rotated_vertex": rotated_target,
        "rotated_edges": rotated_uuids,
        "arc_uuids": [] if arc_uuid is None else [arc_uuid],
        "stationary_edges": len(pattern.edges) - len(rotating),
        "warnings": warnings, "sewings_moved": moved, "sewings_marked": relinked,
        "sewings_followed": _sewings_on(pattern, rotated_uuids),
    }

def pivot_fan(pattern, pivot, target, *, angle) -> dict:
    """Extend the panel by rotating one half of it about a pivot.

    What opens between the radius and its image is filled by an arc edge centred
    on the pivot; the stationary half is untouched, no internal line is created
    for either radius, and the area grows by the sector.
    """
    plan = plan_fan(pattern, pivot, target, angle=angle)
    members = geometry._chain_members(pattern)
    # One Sketch serves the whole chain: the fan is written once. This panel
    # meshes from it; the other readers were marked by the write.
    report = _fan_member(pattern, plan)
    report.update({"action": "pivot_fan", "panel": pattern.name,
                   "angle_deg": math.degrees(plan["angle"]),
                   "radius_mm": plan["radius"],
                   "added_area_mm2": plan["added_area"],
                   "copies": len(members) - 1})
    return report

def _rotate_about(point, centre, angle) -> np.ndarray:
    """`point` rotated about `centre` by `angle` radians, counter-clockwise."""
    offset = np.asarray(point, dtype=np.float64) - np.asarray(centre, dtype=np.float64)
    cosine, sine = math.cos(angle), math.sin(angle)
    return np.asarray(centre, dtype=np.float64) + np.array(
        (offset[0] * cosine - offset[1] * sine, offset[0] * sine + offset[1] * cosine))


register, unregister = register_classes_factory((NODE_OT_fan,))
