"""Draw a many-to-many seam: the runs of the first side, Enter, then the second.

One long edge sewn to several short ones is drawn the way the free-sewing tool
draws a single seam, one run at a time. Each drag along a pattern's chain adds
one run to the side being drawn; Enter closes that side and starts the other, and
the seam is created as soon as the second side has a run. Both sides of one seam
lie on one pattern each, so a run that would put a side on a second pattern is
refused with that reason - the seam joins two patterns and no more.

The side being drawn waits in the project between drags (`QianyiProject.sewing_m2n`),
so the view can be moved between them; Escape, from the tool's own keymap, drops
what this tool is holding.
"""

import numpy as np
from bpy.props import BoolProperty, FloatVectorProperty
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators
from ..model import sewing_geometry as sewing
from ..model.model_data import define_temp_prop
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.console import console
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree
from ._2d_operator_base import Operator2DBase
from ._2d_add_sewing_free import (GRAB_PIXELS, place_under, set_preview,
                                  snapped_place)
from .select import _clear_selection, update_selection_cache
from .states.IState import IState
from .states.PointSelectionState import MouseOperator, PointPickState
from .states.RefuseState import RefuseState
from .states.StatefulOperator import ReturnState, StateOperator

# The sub-mode the editor is put into while this tool is active.
SUBMODE = "ADD_SEWING_M2N"
# A run shorter than this is a click, not a drawn span. Millimetres.
SMALLEST_RUN_MM = 0.5


def held_sets(project):
    """What this tool is holding, or None when it holds no run at all.

    ``{"which", "patterns", "runs"}``: which side is being drawn (1 or 2), the
    pattern each side is being drawn on (-1 while it holds nothing), and the runs
    of both sides in the order they were drawn.
    """
    held = project.sewing_m2n
    if not held:
        return None
    if not any(held.get("runs") or ()):
        return None
    return held


def forget(project) -> None:
    """Drop the runs of the side being drawn."""
    project.sewing_m2n = None


def start_sets(project) -> dict:
    """Begin a new seam: the first side is being drawn."""
    project.sewing_m2n = {"which": 1, "patterns": [-1, -1], "runs": [[], []]}
    return project.sewing_m2n


def start_place(context, project, pointer_region):
    """Where a run begins: the place under the pointer, snapped if close.

    A run has to be able to begin exactly on a point of its chain, or on the end
    of a run already sewn along it, because that is what makes two runs meet at
    one vertex. The snap radius is the same one every sewing tool snaps with: the
    pointer's own, in screen pixels, taken into the pattern's millimetres.
    """
    place = place_under(context, project, pointer_region)
    if place is None:
        return None
    pattern, run, distance, point = place
    snapped = snapped_place(context, project, pattern, run, pointer_region)
    if snapped is not None:
        distance, _kind = snapped
        _edge, _pos, point = sewing.run_place(run, distance)
    return pattern, run, float(distance), np.asarray(point, dtype=np.float64)


def snapped_end(context, project, pattern, run, pointer_region, distance) -> float:
    """Where a run ends: the place under the pointer, snapped if close.

    The same candidates the start snaps to - the chain's own points and the ends
    of the runs already sewn along it - so a drag released near one lands on it
    instead of a hair beside it. A release away from all of them keeps the place
    the pointer is on, which is what a run ending in the middle of an edge is.
    """
    snapped = snapped_place(context, project, pattern, run, pointer_region)
    return float(distance) if snapped is None else float(snapped[0])


def side_runs(held, side):
    """The drawn runs of what is held, as the model's own span tuples."""
    return [(int(run["line1"]), float(run["pos1"]), int(run["line2"]),
             float(run["pos2"]), bool(run["reverse"]))
            for run in held["runs"][side - 1]]


class NODE_OT_add_sewing_m2n(Operator2DBase, StateOperator):
    """Draw one run of a many-to-many seam, and join the two sides when ready."""

    bl_idname = Operators.SewingAddMtoN2D
    bl_label = "draw a many-to-many sewing"
    bl_options = {'BLOCKING', 'GRAB_CURSOR', 'REGISTER', 'UNDO'}

    cancel: BoolProperty(
        name="Cancel",
        description="Set by the tool's escape key: drop the runs drawn so far, "
                    "instead of adding another one",
        default=False,
        options={"SKIP_SAVE"},
    )
    finish: BoolProperty(
        name="Finish side",
        description="Set by the tool's return key: the side being drawn is done, "
                    "and the next drag draws the one it is sewn to",
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
            console.info("draw a many-to-many sewing: what was drawn was dropped")
            self.register_state(RefuseState())
            return
        if self.finish:
            self.finish_side(context, project, manager)
            return
        held = held_sets(project)
        if held is None:
            held = start_sets(project)
        self.held = held
        self.pointer = tuple(self.press_location)
        place = start_place(context, project, self.pointer)
        if place is None:
            console.info("draw a many-to-many sewing: no outline under the pointer")
            self.register_state(RefuseState())
            return
        self.pattern, self.run, self.start_distance, self.start_point = place
        if not self.accept_pattern(project):
            self.register_state(RefuseState())
            return
        self.travel = 0.0
        if manager is not None:
            manager.preview_locked = True
        state = self.register_state(PointPickState(MouseOperator.RELEASE))
        state.data_change_cb.append(self.pointer_moved)
        self.refresh(context)
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)

    def finish_side(self, context: Context, project, manager) -> None:
        """Close the side being drawn, and start the one it is sewn to."""
        held = held_sets(project)
        if held is None or held["which"] != 1:
            console.info("draw a many-to-many sewing: draw the first side's runs, "
                         "then press return")
            self.register_state(RefuseState())
            return
        held["which"] = 2
        held["patterns"][1] = -1
        if manager is not None:
            manager.clear_tool_preview()
        console.info(f"draw a many-to-many sewing: the first side holds "
                     f"{len(held['runs'][0])} run(s); draw the side it is sewn to")
        self.register_state(RefuseState())

    def accept_pattern(self, project) -> bool:
        """Whether this run may join the side being drawn.

        Both sides of a seam lie on one pattern each, so a run on another pattern
        is refused with that reason rather than silently making a seam the engine
        cannot express.
        """
        held = getattr(self, "held", None)
        if held is None:
            return True
        slot = held["which"] - 1
        if held["patterns"][slot] == -1:
            held["patterns"][slot] = int(self.pattern.global_uuid)
            return True
        if held["patterns"][slot] == int(self.pattern.global_uuid):
            return True
        console.info("draw a many-to-many sewing: a side of a seam is on one "
                     "pattern, and this run is on another one")
        return False

    def pointer_moved(self, state: IState, context: Context):
        """One move: extend the run to the place under the pointer, snapped."""
        self.pointer = tuple(state.point_position)
        place = place_under(context, self.project(context), self.pointer)
        if place is None:
            return
        _pattern, run, distance, _point = place
        if sewing.run_key(run) != sewing.run_key(self.run):
            # The run stays on the chain it was started on; the pointer is
            # simply not over it any more.
            return
        here = self.start_distance + self.travel
        self.travel += sewing.run_step(
            self.run, here,
            snapped_end(context, self.project(context), self.pattern, self.run,
                        self.pointer, distance))
        self.refresh(context)

    def project(self, context):
        return get_active_node_tree(context)

    def refresh(self, context: Context):
        """Rebuild the preview for the drag as it stands."""
        held = getattr(self, "held", None)
        waiting = None
        runs = None if held is None else held["runs"][held["which"] - 1]
        if runs:
            last = runs[-1]
            waiting = {"pattern": held["patterns"][held["which"] - 1],
                       "run": last["run"],
                       "start": last["start"], "travel": last["travel"]}
        set_preview(context, self.project(context), self.pattern, self.run,
                    self.start_distance, self.start_point, self.travel, waiting)
        if context.area is not None:
            context.area.tag_redraw()

    def handle_success(self, context: Context, state: IState):
        project = self.project(context)
        try:
            run = sewing.run_from(self.run, self.start_distance, float(self.travel))
        except ValueError as refused:
            console.info("draw a many-to-many sewing:", refused)
            self.return_state = ReturnState.CANCELLED
            return
        if run["length"] < SMALLEST_RUN_MM:
            console.info("draw a many-to-many sewing: that drag covered no outline")
            self.return_state = ReturnState.CANCELLED
            return
        held = getattr(self, "held", None)
        if held is None:
            self.return_state = ReturnState.CANCELLED
            return
        drawn = held["runs"][held["which"] - 1]
        drawn.append({"run": sewing.run_key(self.run),
                      "line1": int(run["start_edge"].global_uuid),
                      "pos1": float(run["start_pos"]),
                      "line2": int(run["end_edge"].global_uuid),
                      "pos2": float(run["end_pos"]),
                      "reverse": bool(run["reverse"]),
                      "start": float(self.start_distance),
                      "travel": float(self.travel)})
        if held["which"] == 1:
            console.info(f"draw a many-to-many sewing: run {len(drawn)} of "
                         f"{run['length']:.1f} mm; press return to draw the side it "
                         f"is sewn to, or draw another run on this one")
            return
        self.join(project, held)

    def join(self, project, held) -> None:
        """Make the seam out of the side that was closed and this one."""
        first_pattern = global_data.get_obj_by_uuid(int(held["patterns"][0]), check_uuid=False)
        forget(project)
        if first_pattern is None:
            console.info("draw a many-to-many sewing: the first side's pattern is gone")
            self.return_state = ReturnState.CANCELLED
            return
        seam = project.add_sewing_spans(side_runs(held, 1), side_runs(held, 2),
                                        pattern1=first_pattern,
                                        pattern2=self.pattern)
        if seam is None:
            console.warning("draw a many-to-many sewing:",
                            project.last_sewing_error or "no seam was made")
            self.return_state = ReturnState.CANCELLED
            return
        self.select_sewing(project, seam)
        console.info(f"draw a many-to-many sewing: made seam {seam.get_index()} "
                     f"({len(seam.side1.spans)} run(s) to {len(seam.side2.spans)})")

    @staticmethod
    def select_sewing(project, sewing_made) -> None:
        """Leave the new seam selected, so it is what an edit acts on next."""
        _clear_selection(project.selected_sewings)
        for side in (sewing_made.side1, sewing_made.side2):
            update_selection_cache(project.selected_sewings, side, "SET", True)

    def handle_failure(self, context: Context, state: IState):
        # The drag is dropped; the runs already drawn stay, so a slip does not
        # cost the side.
        self.return_state = ReturnState.CANCELLED

    def fini(self, context: Context):
        manager = global_data.temp_draw_manager
        if manager is not None:
            manager.clear_tool_preview()
            manager.preview_locked = False
        if context.area is not None:
            context.area.tag_redraw()


register, unregister = register_classes_factory((NODE_OT_add_sewing_m2n,))
