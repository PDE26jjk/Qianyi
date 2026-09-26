"""Move a sewing's half: one end of it, or the half itself.

Point at a half: its two ends are drawn as points over it, and the one the
pointer is on is the one a press takes. Press on an end and drag, and that end
follows the pointer while the half grows or shrinks; press anywhere on the half
between its ends and it slides along the outline, both ends together, keeping its
length. What the press takes is what the pass drew under the pointer, so a press
beside an end is a press on the half. An end dragged past the other one lays the
half the long way round the outline instead of flipping it over: the run keeps
the direction it had, and its length wraps at the place the two ends meet, so a
half can span almost the whole outline. A dragged end snaps to what a seam is
made against: the outline's vertices, the ends of other halves, and - on a seam
whose sides are one to one - the place that makes this side exactly as long as
the other one. A sliding half snaps each of its two ends on its own, each one
measured where that end is.

Nothing is accumulated: every move asks the drag's own starting shape and the
pointer where the half would be now, so dragging back and forth is exact and the
half never drifts. One drag is one undo step, and the seam graph is linked again
when it is released, because moving a half moves the cuts its seam asked for.
"""

import numpy as np
from bpy.props import FloatVectorProperty
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators
from ..model import sewing_geometry as sewing
from ..model.qianyi_data import ensure_edit_mode
from ..model.sewing import SewingOneSide
from ..utilities.console import console
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree
from ._2d_add_sewing_free import GRAB_PIXELS, place_under, set_preview
from ._2d_operator_base import Operator2DBase
from .states.IState import IState
from .states.PointSelectionState import MouseOperator, PointPickState
from .states.RefuseState import RefuseState
from .states.StatefulOperator import ReturnState, StateOperator

SUBMODE = "EDIT_SEWING"
# A half left shorter than this by a move is no half at all: the move is refused
# and the seam keeps the shape it had. Millimetres.
SMALLEST_HALF_MM = 0.5
# How far the pointer has to move, in view units, before a drag counts as one:
# the release of a press that never moved would otherwise write the half back
# where it already was, and pay for a linking run to do it.
DRAG_DEAD_ZONE = 1e-3
# How far a snap reaches, in pixels: half of what drawing a seam reaches with.
# An end is placed against its own candidates while the half is being moved, and
# the two ends of the half being moved are candidates of their own, so the reach
# that suits drawing a seam is too wide for editing one.
SNAP_PIXELS = GRAB_PIXELS / 2.0

# What a pick under the pointer stands for. The id pass draws a half as a line
# and its two ends as points over it, so the pointer says which of the three a
# press takes.
PICK_GRABS = {"sewing_start": "start", "sewing_end": "end", "sewing_side": "body"}


def picked_target(manager):
    """What the pointer is over: ``(side, "start" | "end" | "body")``, or None.

    The id pass gives each half an id and each of its ends an id of its own, so
    the answer comes from what was drawn under the pointer rather than from how
    close the press happened to land to an end: an end answers "start" or "end"
    and the half between them answers "body". Anything else - an edge, a vertex -
    is another tool's business, and answers None.
    """
    pick = manager.hover_pick if manager is not None else None
    if pick is None:
        return None
    _pattern, _kind, element = pick
    grab = PICK_GRABS.get(_kind)
    if grab is None or not isinstance(element, SewingOneSide):
        return None
    return element, grab


def other_side(sewing, side):
    """The half of the same seam that this one is sewn to."""
    return sewing.side2 if side.global_uuid == sewing.side1.global_uuid else sewing.side1


class NODE_OT_sewing_edit(Operator2DBase, StateOperator):
    """Move one end of a seam's half, or slide the half along the outline."""

    bl_idname = Operators.SewingEdit2D
    bl_label = "edit a sewing"
    bl_options = {'BLOCKING', 'GRAB_CURSOR', 'REGISTER', 'UNDO'}

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
        target = picked_target(manager)
        if target is None:
            console.info("edit a sewing: no seam half under the pointer")
            self.register_state(RefuseState())
            return
        side, grab = target
        if side.pattern is None or side.sewing is None:
            # What a stale pick resolves to: a half whose pattern or seam is
            # gone has nothing left to edit.
            console.info("edit a sewing: that seam half is not part of a seam")
            self.register_state(RefuseState())
            return
        self.project = project
        self.side_uuid = side.global_uuid
        self.pattern = side.pattern
        self.other = other_side(side.sewing, side)
        # The shape the drag is measured from, and what the press took hold of.
        try:
            # What the half runs on: the pattern's outline, or the internal line
            # it was made on.
            self.run, self.start, self.travel = sewing.side_run(side)
        except ValueError as refused:
            console.info("edit a sewing: this half cannot be measured:", refused)
            self.register_state(RefuseState())
            return
        pointer = place_under(context, project, self.press_location)
        if (pointer is None
                or sewing.run_key(pointer[1]) != sewing.run_key(self.run)):
            console.info("edit a sewing: the pointer is not on the chain of this half")
            self.register_state(RefuseState())
            return
        self.candidates = sewing.run_candidates(project, self.run,
                                                exclude_side_uuid=self.side_uuid)
        # What the half is now, so a move the linking run refuses can be taken
        # back without touching the seam's own data.
        self.before = (side.line1_uuid, float(side.pos1), side.line2_uuid,
                       float(side.pos2), bool(side.reverse))
        self.press_place = pointer[2]
        self.pointer_region = tuple(self.press_location)
        self.press_view = region2view_coord(context, self.press_location)
        self.pointer_view = self.press_view
        self.pointer_place = pointer[2]
        self.snapped_mark = None
        self.updated = False
        # What the press took, as the pass drew it: an end once the pointer is on
        # an end's own point, the half itself anywhere between the two.
        self.grab = grab
        if manager is not None:
            manager.preview_locked = True
            manager.clear_tool_preview()
        state = self.register_state(PointPickState(MouseOperator.RELEASE))
        state.data_change_cb.append(self.pointer_moved)
        self.refresh(context)
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)

    # ------------------------------------------------------------- the drag

    def pointer_moved(self, state: IState, context: Context):
        """One move: take the pointer's place on the chain the half runs on."""
        self.pointer_view = region2view_coord(context, tuple(state.point_position))
        self.pointer_region = tuple(state.point_position)
        if float(np.linalg.norm(np.asarray(self.pointer_view)
                                - np.asarray(self.press_view))) <= DRAG_DEAD_ZONE:
            # The press, or its release without a drag: nothing to move yet.
            return
        pointer = place_under(context, self.project, tuple(state.point_position))
        if (pointer is None
                or sewing.run_key(pointer[1]) != sewing.run_key(self.run)):
            # Off this half's chain: the half keeps the shape it last had.
            return
        self.pointer_place = pointer[2]
        self.updated = True
        self.refresh(context)

    def refresh(self, context: Context):
        """Work out where the half would be now, and draw it."""
        try:
            places = self.drag_places(context)
        except ValueError as refused:
            console.info("edit a sewing:", refused)
            return
        self.places = places
        _edge, _pos, point = sewing.run_place(self.run, places[0])
        set_preview(context, self.project, self.pattern, self.run, places[0], point,
                    places[1], None, self.snapped_mark)
        if context.area is not None:
            context.area.tag_redraw()

    def drag_places(self, context: Context) -> tuple:
        """The half's two ends as ``(start, travel)`` for the pointer as it is now.

        A drag changes how far the run goes. On a closed outline it keeps the
        direction the half already had, so an end dragged past the other one keeps
        going and lays the run the long way round: the length wraps at the place
        where the two ends meet, and a half can span almost the whole outline. An
        open chain has no other way round, so the run simply turns round there.
        """
        self.snapped_mark = None
        direction = 1.0 if self.travel >= 0.0 else -1.0
        if self.grab == "body":
            step = sewing.run_step(self.run, self.press_place, self.pointer_place)
            start = self.start + step
            first = self.snapped(context, start, None)
            second = self.snapped(context, start + self.travel, None)
            # Each end is measured where it is, and a closed chain's own length
            # and zero are one place: an end that snaps near the chain's start
            # answers a distance near zero while the other answers one near the
            # chain's length, and subtracting those turns the half round. The
            # distance between the two is the one that keeps the direction the
            # half already runs in.
            return first, sewing.run_travel(self.run, first, second, direction)
        if self.grab == "start":
            fixed = self.start + self.travel
            moved = self.snapped(context, self.pointer_place, fixed)
            # The end being dragged is the one the run starts from here, so the
            # run reaches from it to the end that stayed.
            return moved, sewing.run_travel(self.run, moved, fixed, direction)
        fixed = self.start
        moved = self.snapped(context, self.pointer_place, fixed)
        return fixed, sewing.run_travel(self.run, fixed, moved, direction)

    def snapped(self, context: Context, place, fixed):
        """`place`, or a place near that end that it snaps onto.

        The candidates are the pattern's vertices and the ends of other halves; on
        top of those - for an end that has another end to be measured from - is
        the place that makes this half exactly as long as the half it is sewn to,
        which is what the two sides of a one-to-one seam want.

        Each end is measured where that end would be, not where the pointer is:
        a half being slid moves both of its ends at once, and measuring them
        against one pointer pulled both onto the same candidate the moment the
        pointer came near one.
        """
        radius = sewing.snap_radius(context, self.pattern, self.pointer_region, SNAP_PIXELS)
        end_view = self.pattern.pattern_to_view_pos(
            sewing.run_place(self.run, place)[2])
        found = sewing.nearest_candidate(context, self.pattern, end_view,
                                         self.candidates, radius)
        if found is not None:
            distance = sewing.run_nearest_distance(self.run, found[1])
            self.snapped_mark = (distance, np.asarray(found[1], dtype=np.float64))
            return distance
        if fixed is not None:
            equal = self.equal_length_place(context, fixed, end_view)
            if equal is not None:
                self.snapped_mark = equal
                return equal[0]
        return place

    def equal_length_place(self, context: Context, fixed, end_view):
        """The place that makes this half as long as the one it is sewn to.

        It is measured from the end that is not moving, in the direction the half
        is drawn, and it only answers when the end being placed is close to it.
        """
        if self.other is None or self.other.pattern is None:
            return None
        try:
            _other_run, _other_start, other_travel = sewing.side_run(self.other)
        except ValueError:
            return None
        length = abs(other_travel)
        if length <= 0.0:
            return None
        direction = 1.0 if self.travel >= 0.0 else -1.0
        distance = fixed + direction * length
        try:
            _edge, _pos, point = sewing.run_place(self.run, distance)
        except ValueError:
            # An open internal line has ends: the place that would match the
            # other half's length need not be on this chain at all, and then
            # there is nothing to snap to.
            return None
        radius = sewing.snap_radius(context, self.pattern, self.pointer_region, SNAP_PIXELS)
        drawn = self.pattern.view_points([point])[0]
        if float(np.linalg.norm(np.asarray(drawn) - np.asarray(end_view))) > radius:
            return None
        return float(distance), np.asarray(point, dtype=np.float64)

    # ------------------------------------------------------------- writing

    def handle_success(self, context: Context, state: IState):
        if not self.updated:
            # A press that never moved leaves the seam as it was.
            self.return_state = ReturnState.CANCELLED
            return
        try:
            places = self.drag_places(context)
        except ValueError as refused:
            console.info("edit a sewing:", refused)
            self.return_state = ReturnState.CANCELLED
            return
        if abs(places[1]) < SMALLEST_HALF_MM:
            console.info("edit a sewing: that would leave the half with no length")
            self.return_state = ReturnState.CANCELLED
            return
        side = self.side()
        if side is None:
            console.info("edit a sewing: the half this drag was started on is gone")
            self.return_state = ReturnState.CANCELLED
            return
        first_edge, first_pos, _point = sewing.run_place(self.run, places[0])
        second_edge, second_pos, _point = sewing.run_place(self.run, places[0] + places[1])
        side.update_data(first_edge, first_pos, second_edge, second_pos,
                         places[1] < 0.0, pattern=self.pattern)
        seam = side.sewing
        # Moving a half moves the cuts its seam asked for: the seam graph is
        # linked again (and the guard looks at it, so a seam this edit made
        # impossible is flagged instead of breaking the mesh later).
        try:
            self.project.sewings_changed([self.pattern])
        except Exception as refused:  # noqa: BLE001 - the linker's reason is the report
            # The edit asked for a seam graph the linker will not have - two runs
            # crossing each other, say. The half goes back to what it was and the
            # graph is linked again, so a refused drag leaves the project as it
            # found it instead of half edited.
            self.restore(side)
            try:
                self.project.sewings_changed([self.pattern])
            except Exception as again:  # noqa: BLE001
                console.warning("edit a sewing: the seam graph could not be linked "
                                "again:", again)
            console.info("edit a sewing: that move was refused:", refused)
            self.return_state = ReturnState.CANCELLED
            return
        if seam is not None:
            seam.need_render_update = True
            seam.update()
            for pattern in (seam.pattern1, seam.pattern2):  # loop: the two patterns
                if pattern is not None:
                    pattern.need_sewing_update = True
        console.info(f"edit a sewing: the half is {abs(places[1]):.2f} mm long now, "
                     f"{'the other way round' if places[1] < 0.0 else 'the same way round'}")

    def side(self):
        """The half this drag took, read back by identity."""
        found = global_data.get_obj_by_uuid(self.side_uuid, check_uuid=False)
        return found if isinstance(found, SewingOneSide) else None

    def restore(self, side) -> None:
        """Put a half back to the record this drag started from."""
        line1_uuid, pos1, line2_uuid, pos2, reverse = self.before
        side.line1_uuid = line1_uuid
        side.pos1 = pos1
        side.line2_uuid = line2_uuid
        side.pos2 = pos2
        side.reverse = reverse

    def handle_failure(self, context: Context, state: IState):
        self.return_state = ReturnState.CANCELLED

    def fini(self, context: Context):
        manager = global_data.temp_draw_manager
        if manager is not None:
            manager.clear_tool_preview()
            manager.preview_locked = False
        if context.area is not None:
            context.area.tag_redraw()


register, unregister = register_classes_factory((NODE_OT_sewing_edit,))
