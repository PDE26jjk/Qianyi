"""Drag one edge into shape: the curve follows the point the pointer took."""

import numpy as np
from bpy.props import BoolProperty, FloatVectorProperty
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators
from ..model import pattern_geometry as geometry
from ..model.generator import refuse_generated_edit
from ..model.geometry import Edge2D
from ..model.model_data import owner_pattern
from ..model.pattern import interactive_edit_allowed
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.console import console
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree
from ._2d_operator_base import Operator2DBase
from .states.IState import IState
from .states.PointSelectionState import MouseOperator, PointPickState
from .states.RefuseState import RefuseState
from .states.StatefulOperator import ReturnState, StateOperator

# A press and a release at the same place is a click, not a drag: below this the
# gesture writes nothing, so a stray click cannot mark the pattern, rebuild its
# mesh and leave an undo step behind. Millimetres, like the pattern space.
DRAG_DEAD_ZONE_MM = 1e-3


def picked_edge(context: Context, manager):
    """The edge the pointer is on, with the pattern it is drawn on.

    The id pass recorded the pair, so a pointer over a copy of a pattern names
    that copy: an edge serves its whole instance chain, and the drag works in
    the space of the member the pointer was over. A pick that is not an edge - a
    point, or a handle - is left to the tools that move those.
    """
    pick = manager.hover_pick if manager is not None else None
    if pick is not None:
        pattern, _kind, element = pick
        return (element, pattern) if isinstance(element, Edge2D) else (None, None)
    hover = context.scene.qmyi.hover_object
    if isinstance(hover, Edge2D):
        pattern = (manager.picked_pattern() if manager is not None else None) \
            or owner_pattern(hover)
        return hover, pattern
    return None, None


class NODE_OT_curve_fit(Operator2DBase, StateOperator):
    """Reshape one edge by dragging it: the curve follows the pointer.

    The press takes hold of the edge at the point under the pointer; every move
    bends the piece so that point sits under the pointer, with both ends held
    where they are; the release writes the new shape into the Sketch it belongs
    to, which is one undo step and one mesh rebuild for the whole instance
    chain. Escape leaves the pattern as it was.

    The form the edge is in is the form it keeps - a line or a Bezier moves its
    two handles, a spline moves the control points it already has - so a drag
    never adds a point or turns one kind of edge into another.
    """

    bl_idname = Operators.CurveFit2D
    bl_label = "drag a curve"
    bl_options = {'BLOCKING', 'GRAB_CURSOR', 'REGISTER', 'UNDO'}

    updated: BoolProperty(default=False, options={"SKIP_SAVE"})
    press_location: FloatVectorProperty(size=2, default=(0.0, 0.0),
                                        options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        return get_active_node_tree(context) is not None

    def invoke(self, context: Context, event: Event):
        # Where the edge is taken hold of: the state machine starts on this same
        # press, so the position is kept here and read by `setup_state_machine`.
        self.press_location = (event.mouse_region_x, event.mouse_region_y)
        return super().invoke(context, event)

    def setup_state_machine(self, context: Context):
        project = get_active_node_tree(context)
        manager = global_data.temp_draw_manager
        if project is None:
            self.return_state = ReturnState.CANCELLED
            return
        ensure_edit_mode(context, "EDGE", "EDGE_VERTEX")
        edge, pattern = picked_edge(context, manager)
        if edge is None or pattern is None:
            console.info("drag a curve: no edge under the pointer")
            self.register_state(RefuseState())
            return
        if refuse_generated_edit(self, project, pattern):
            self.register_state(RefuseState())
            return
        grab = pattern.view_to_pattern_pos(region2view_coord(context, self.press_location))
        try:
            self.drag = geometry.EdgeDrag(edge, grab)
        except geometry.GeometryRefused as refused:
            console.info("drag a curve:", refused.reason)
            self.register_state(RefuseState())
            return
        self.project = project
        self.pattern = pattern
        self.origin = np.asarray(grab, dtype=np.float64)
        self.offset = np.zeros(2, dtype=np.float64)
        self.samples = None
        self.updated = False
        if manager is not None:
            # The gesture draws its own preview; the tool's cursor preview stays
            # out of the way until it is over.
            manager.preview_locked = True
            manager.clear_tool_preview()
        state = self.register_state(PointPickState(MouseOperator.RELEASE))
        state.data_change_cb.append(self.pointer_moved)
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)

    def pointer_moved(self, state: IState, context: Context):
        """One move: bend the preview so the grabbed point is under the pointer."""
        point = self.pattern.view_to_pattern_pos(
            region2view_coord(context, state.point_position))
        self.offset = np.asarray(point, dtype=np.float64) - self.origin
        if float(np.hypot(*self.offset)) <= DRAG_DEAD_ZONE_MM:
            return
        form = self.drag.form(self.offset)
        self.samples = form["samples"]
        self.updated = True
        manager = global_data.temp_draw_manager
        if manager is not None:
            manager.set_tool_polyline(self.pattern.view_points(self.samples))
        context.area.tag_redraw()

    def handle_success(self, context: Context, state: IState):
        if not self.updated:
            # A press that never moved is not a drag.
            self.return_state = ReturnState.CANCELLED
            return
        if not self.crossing_allowed(context):
            self.return_state = ReturnState.CANCELLED
            return
        try:
            form = self.drag.apply(self.offset)
        except geometry.GeometryRefused as refused:
            console.warning("drag a curve:", refused.reason)
            self.return_state = ReturnState.CANCELLED
            return
        sketch = self.pattern.require_sketch()
        sketch.geometry_written()
        # One mesh for every member of the chain, now: the shape on screen is
        # what the drag was showing, and a member left marked would keep the
        # outline it used to have.
        sketch.rebuild_meshes()
        self.project.clear_edge_finder()
        console.info(f"drag a curve: wrote a {form['kind']} edge, "
                     f"the pointer point is {form['miss']:.3f} mm off the curve")

    def handle_failure(self, context: Context, state: IState):
        self.return_state = ReturnState.CANCELLED

    def fini(self, context: Context):
        manager = global_data.temp_draw_manager
        if manager is not None:
            manager.clear_tool_preview()
            manager.preview_locked = False
        if context.area is not None:
            context.area.tag_redraw()

    def crossing_allowed(self, context: Context) -> bool:
        """Whether the outline the drag produced may be written as it stands.

        The pattern's own samples with the dragged edge's new shape in place of
        the old one - what the scene's Check Self-Intersection switch decides
        about, exactly as the move tool tests its result. An edge of an
        internal line is not part of the outline: there the mesh stage is what
        reports a shape it cannot triangulate.
        """
        replaced = False
        checking = []
        for edge in self.pattern.edges:  # loop: one run per outline edge
            if edge.global_uuid == self.drag.edge_uuid:
                checking.append(np.asarray(self.samples, dtype=np.float32)[:-1])
                replaced = True
            else:
                checking.append(np.asarray(edge.render_points, dtype=np.float32)[:-1])
        if not replaced:
            return True
        return interactive_edit_allowed(context, np.concatenate(checking))


register, unregister = register_classes_factory((NODE_OT_curve_fit,))
