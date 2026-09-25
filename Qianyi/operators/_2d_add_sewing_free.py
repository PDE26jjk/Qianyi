"""Draw a sewing: one half on a pattern, then the other half on the pattern it joins.

Each half is drawn by dragging along a pattern's outline. The drag snaps to what a
seam is made against - the outline's own vertices, and the ends of halves that
are already there - and the second half snaps again to the place that is exactly
as long as the first one, which is what makes the two sides match without the
user measuring anything.

The first half is kept in the project while the second is drawn, the way the fan
keeps its pivot: the two halves are two drags, and the view stays usable between
them. Escape during a drag drops that drag; escape between them, from the tool's
own keymap, drops the first half.
"""

import numpy as np
from bpy.props import BoolProperty, FloatVectorProperty
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators
from ..model import sewing_geometry as sewing
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.console import console
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree
from ._2d_operator_base import Operator2DBase
from .select import _clear_selection, update_selection_cache
from .states.IState import IState
from .states.PointSelectionState import MouseOperator, PointPickState
from .states.RefuseState import RefuseState
from .states.StatefulOperator import ReturnState, StateOperator

# The sub-mode the editor is put into while this tool is active.
SUBMODE = "ADD_SEWING_FREE"
# A half shorter than this is a click, not a drawn seam. Millimetres.
SMALLEST_HALF_MM = 0.5
# How far from the outline, in pixels, a press still counts as being on it. The
# nearest-outline search always answers with something - the closest point of
# any pattern, however far away - so a press in empty space is turned down here
# rather than drawing a half from wherever the search landed.
GRAB_PIXELS = 24.0


def armed_half(project):
    """The first half this tool drew and has not joined yet, or None."""
    half = project.sewing_free_half
    if not half:
        return None
    if global_data.get_obj_by_uuid(int(half["pattern"]), check_uuid=False) is None:
        # The pattern it was drawn on is gone: the half goes with it.
        project.sewing_free_half = None
        return None
    return half


def forget(project) -> None:
    """Drop the half that is waiting for its partner."""
    project.sewing_free_half = None


def half_pattern(project, half):
    """The pattern a stored half was drawn on, or None when it is gone."""
    return global_data.get_obj_by_uuid(int(half["pattern"]), check_uuid=False)


def place_under(context, project, pointer_region):
    """Where on a pattern's outline the pointer is: ``(pattern, distance, point)``.

    The answer comes from the project's own nearest-outline search, which is the
    same one the add-vertex tool snaps with, and is turned into a distance around
    the outline - the space a seam stores its ends in. The pointer is the
    caller's: a running drag is the one that owns the events, so the position has
    to come from the event that moved, not from anything the editor kept for a
    different purpose.
    """
    if pointer_region is None:
        return None
    project.find_nearest_point_on_edge(region2view_coord(context, pointer_region))
    if project.nearest_point is None or project.nearest_pattern is None:
        return None
    try:
        pattern, edge, point, fraction = project.get_nearest_point_data()
        distance = sewing.outline_origin(pattern, edge, fraction)
    except (ValueError, KeyError):
        # The snapshot behind the answer went stale between the search and the
        # read: the next move asks again.
        return None
    view = region2view_coord(context, pointer_region)
    radius = sewing.snap_radius(context, pattern, pointer_region, GRAB_PIXELS)
    if radius > 0.0:
        drawn = pattern.view_points([point])[0]
        if float(np.linalg.norm(np.asarray(drawn) - np.asarray(view))) > radius:
            return None
    return pattern, float(distance), np.asarray(point, dtype=np.float64)


def snapped_place(context, project, pattern, pointer_region, entries=None):
    """The snap candidate near the pointer: ``(distance, kind)``, or None."""
    if entries is None:
        entries = sewing.snap_candidates(project, pattern)
    found = sewing.nearest_candidate(context, pattern,
                                     region2view_coord(context, pointer_region), entries)
    if found is None:
        return None
    _away, point, kind, _uuid = found
    return sewing.nearest_outline_distance(pattern, point), kind


def second_half_target(context, project, pattern, start_distance, travel, first,
                       pointer_region):
    """The place that is exactly as long as the first half, when it is near.

    The second half is measured from its own start, in the direction it is being
    drawn, so the two halves end up the same length even though they run on
    different patterns. Returns ``(distance, point)`` or None.
    """
    if first is None:
        return None
    length = abs(float(first["travel"]))
    if length <= 0.0:
        return None
    direction = 1.0 if travel >= 0.0 else -1.0
    distance = start_distance + direction * length
    try:
        _edge, _pos, point = sewing.outline_place(pattern, distance)
    except ValueError:
        return None
    if pointer_region is None:
        return None
    view = region2view_coord(context, pointer_region)
    radius = sewing.snap_radius(context, pattern, pointer_region)
    drawn = pattern.view_points([point])[0]
    if float(np.linalg.norm(np.asarray(drawn) - np.asarray(view))) > radius:
        return None
    return float(distance), np.asarray(point, dtype=np.float64)


def set_preview(context, project, pattern, start_distance, start_point, travel,
                first=None, equal=None) -> None:
    """Draw the half being dragged, and what it would snap to.

    One polyline - the half itself, in the order it is drawn - and the markers:
    where the half starts, where the pointer has got to, the place that matches
    the first half's length, and the two ends of the first half while the second
    is being drawn.
    """
    manager = global_data.temp_draw_manager
    if manager is None or pattern is None:
        return
    entries = [(pattern, start_point, "pivot")]
    if abs(float(travel)) > 1e-9:
        # A press that has not moved yet draws its start and nothing else: there
        # is no run to draw until the pointer has gone somewhere.
        try:
            run = sewing.run_from(pattern, start_distance, travel)
        except ValueError:
            return
        manager.set_tool_polyline(pattern.view_points(run["polyline"]))
        entries.append((pattern, run["end_point"], "hover"))
    else:
        manager.set_tool_polyline([])
    if equal is not None:
        entries.append((pattern, equal[1], "target"))
    if first is not None:
        pattern = half_pattern(project, first)
        if pattern is not None:
            try:
                first_run = sewing.run_from(pattern, float(first["start"]),
                                            float(first["travel"]))
                entries.append((pattern, first_run["polyline"][0], "pivot"))
                entries.append((pattern, first_run["end_point"], "target"))
            except ValueError:
                pass
    manager.set_tool_points(entries)


class NODE_OT_add_sewing_free(Operator2DBase, StateOperator):
    """Draw one sewing, a half at a time.

    Press on the outline and drag: the half is the run of the outline the pointer
    sweeps, from where the press landed to where it is released. The first half
    is kept; the second is drawn the same way on the pattern the seam joins, and
    the seam is made when it is released. One drop of the button is one half, so
    the view can still be moved between them.
    """

    bl_idname = Operators.SewingAddFree2D
    bl_label = "draw a sewing"
    bl_options = {'BLOCKING', 'GRAB_CURSOR', 'REGISTER', 'UNDO'}

    cancel: BoolProperty(
        name="Cancel",
        description="Set by the tool's escape key: drop the half that is waiting "
                    "for its partner instead of drawing the second one",
        default=False,
        options={"SKIP_SAVE"},
    )
    press_location: FloatVectorProperty(size=2, default=(0.0, 0.0), options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        return get_active_node_tree(context) is not None

    def invoke(self, context: Context, event: Event):
        self.press_location = (event.mouse_region_x, event.mouse_region_y)
        return super().invoke(context, event)

    def setup_state_machine(self, context: Context):
        project = get_active_node_tree(context)
        manager = global_data.temp_draw_manager
        if project is None:
            self.return_state = ReturnState.CANCELLED
            return
        ensure_edit_mode(context, "SEWING", SUBMODE)
        if self.cancel:
            forget(project)
            if manager is not None:
                manager.clear_tool_preview()
            console.info("draw a sewing: the first half was dropped")
            self.register_state(RefuseState())
            return
        self.project = project
        self.first = armed_half(project)
        self.pointer = tuple(self.press_location)
        place = self.start_place(context, project, self.pointer)
        if place is None:
            console.info("draw a sewing: no outline under the pointer")
            self.register_state(RefuseState())
            return
        self.pattern, self.start_distance, self.start_point = place
        self.travel = 0.0
        self.equal = None
        if manager is not None:
            manager.preview_locked = True
        state = self.register_state(PointPickState(MouseOperator.RELEASE))
        state.data_change_cb.append(self.pointer_moved)
        self.refresh(context)
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)

    def start_place(self, context: Context, project, pointer_region):
        """Where the drag starts: the place under the pointer, snapped if close."""
        place = place_under(context, project, pointer_region)
        if place is None:
            return None
        pattern, distance, point = place
        snapped = snapped_place(context, project, pattern, pointer_region)
        if snapped is not None:
            distance, _kind = snapped
            _edge, _pos, point = sewing.outline_place(pattern, distance)
        return pattern, float(distance), np.asarray(point, dtype=np.float64)

    def pointer_moved(self, state: IState, context: Context):
        """One move: extend the half to the place under the pointer."""
        self.pointer = tuple(state.point_position)
        place = place_under(context, self.project, self.pointer)
        if place is None:
            return
        pattern, distance, _point = place
        if pattern.global_uuid != self.pattern.global_uuid:
            # The half stays on the pattern it was started on; the pointer is
            # simply not over it any more.
            return
        here = self.start_distance + self.travel
        self.travel += sewing.outline_step(self.pattern, here, distance)
        self.refresh(context)

    def refresh(self, context: Context):
        """Rebuild the preview for the drag as it stands."""
        equal = second_half_target(context, self.project, self.pattern,
                                   self.start_distance, self.travel, self.first,
                                   self.pointer)
        self.equal = equal
        set_preview(context, self.project, self.pattern, self.start_distance,
                    self.start_point, self.end_travel(), self.first, equal)
        if context.area is not None:
            context.area.tag_redraw()

    def end_travel(self) -> float:
        """How far the half runs: to the pointer, or to the place that matches."""
        if self.equal is None:
            return float(self.travel)
        return float(self.equal[0]) - float(self.start_distance)

    def handle_success(self, context: Context, state: IState):
        try:
            run = sewing.run_from(self.pattern, self.start_distance, self.end_travel())
        except ValueError as refused:
            console.info("draw a sewing:", refused)
            self.return_state = ReturnState.CANCELLED
            return
        if run["length"] < SMALLEST_HALF_MM:
            console.info("draw a sewing: that drag covered no outline")
            self.return_state = ReturnState.CANCELLED
            return
        if self.first is None:
            self.arm(self.project, run)
            return
        self.join(self.project, run)

    def arm(self, project, run) -> None:
        """Keep the first half, and say how to finish the seam."""
        project.sewing_free_half = {"pattern": self.pattern.global_uuid,
                                    "start": float(self.start_distance),
                                    "travel": float(self.end_travel())}
        console.info(f"draw a sewing: the first half is {run['length']:.1f} mm long; "
                     f"draw the other half on the pattern it joins")

    def join(self, project, run) -> None:
        """Make the seam out of the half that was waiting and this one."""
        first = self.first
        pattern = half_pattern(project, first)
        forget(project)
        if pattern is None:
            console.info("draw a sewing: the pattern of the first half is gone")
            self.return_state = ReturnState.CANCELLED
            return
        try:
            first_run = sewing.run_from(pattern, float(first["start"]), float(first["travel"]))
        except ValueError as refused:
            console.info("draw a sewing:", refused)
            self.return_state = ReturnState.CANCELLED
            return
        seam = project.add_sewing(
            first_run["start_edge"], first_run["start_pos"],
            first_run["end_edge"], first_run["end_pos"], first_run["reverse"],
            run["start_edge"], run["start_pos"],
            run["end_edge"], run["end_pos"], run["reverse"],
            pattern1=pattern, pattern2=self.pattern)
        if seam is None:
            console.warning("draw a sewing:", project.last_sewing_error or "no seam was made")
            self.return_state = ReturnState.CANCELLED
            return
        self.select_sewing(project, seam)
        console.info(f"draw a sewing: {first_run['length']:.1f} mm to "
                     f"{run['length']:.1f} mm joined")

    @staticmethod
    def select_sewing(project, sewing_made) -> None:
        """Leave the new seam selected, so it is what an edit acts on next."""
        _clear_selection(project.selected_sewings)
        for side in (sewing_made.side1, sewing_made.side2):
            update_selection_cache(project.selected_sewings, side, "SET", True)

    def handle_failure(self, context: Context, state: IState):
        # The drag is dropped; a first half that was already drawn stays, so a
        # slip on the second one does not cost the first.
        self.return_state = ReturnState.CANCELLED

    def fini(self, context: Context):
        manager = global_data.temp_draw_manager
        if manager is not None:
            manager.clear_tool_preview()
            manager.preview_locked = False
        if context.area is not None:
            context.area.tag_redraw()


register, unregister = register_classes_factory((NODE_OT_add_sewing_free,))
