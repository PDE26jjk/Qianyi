import bpy
import numpy as np
from bpy.types import Context
from bpy.utils import register_classes_factory
from mathutils import Vector

from ._2d_operator_base import Operator2DBase
from .states.CurvePenState import CurvePenState
from .states.IState import IState
from .states.StatefulOperator import StateOperator, ReturnState
from ..declarations import Operators
from ..gizmos.moving_curve import MovingCurve
from ..model.pattern import interactive_edit_allowed
from ..utilities.node_tree import get_active_node_tree
from ..model.qianyi_data import ensure_edit_mode


class NODE_OT_pattern_create_by_pen(Operator2DBase, StateOperator):
    bl_idname = Operators.PatternPen
    bl_label = "pattern pen"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context):
        # The mode is not part of the poll: `setup_state_machine` puts the
        # editor into this tool's mode, so picking the tool is enough to use it.
        project = get_active_node_tree(context)
        return project is not None

    def setup_state_machine(self, context):
        ensure_edit_mode(context, "PATTERN")
        # console.success("setup_state_machine")
        context.window_manager.modal_handler_add(self)
        # self.draw_manager: TempDrawManager = global_data.temp_draw_manager
        # self.draw_manager.clear()

        p1state = self.register_state(CurvePenState())
        p1state.no_blocking = True
        # self.initialized = False
        self.project = get_active_node_tree(context)

        def cb1(_self, _context):
            if _self.moving_curves:
                for mc in _self.moving_curves:
                    mc.update()
            context.area.tag_redraw()

        p1state.data_change_cb.append(cb1)
        self._draw_handler = bpy.types.SpaceNodeEditor.draw_handler_add(
            self._draw_preview, (context, p1state), 'WINDOW', 'POST_VIEW')

    def _draw_preview(self, context, state: CurvePenState):
        if state.moving_curves:
            for mc in state.moving_curves:
                mc.renderer.draw_preview((1, 1, 1, 1), 2)

    def handle_success(self, context: Context, state):
        state: CurvePenState
        moving_curves = state.moving_curves
        if not moving_curves:
            self.return_state = ReturnState.CANCELLED
            return
        checking_edge_points = []
        if not state.circle:
            mc = MovingCurve()
            first_mc = moving_curves[0]
            last_mc = moving_curves[-1]
            mc.vertex0.co = last_mc.vertex1.co
            mc.handle1_type = last_mc.handle2_type
            if mc.handle1_type == "ALIGNED":
                mc.handle1.co = 2 * Vector(mc.vertex0.co) - Vector(last_mc.handle2.co)
            mc.vertex1.co = first_mc.vertex0.co
            mc.handle2_type = first_mc.handle1_type
            if mc.handle2_type == "ALIGNED":
                mc.handle2.co = 2 * Vector(mc.vertex1.co) - Vector(first_mc.handle1.co)
            mc.update()

            moving_curves.append(mc)
        for mc in moving_curves:
            checking_points = mc.render_points
            checking_edge_points.append(checking_points[:-1])
        checking_edge_points = np.concatenate(checking_edge_points, dtype=np.float32)
        if not interactive_edit_allowed(context, checking_edge_points):
            self.return_state = ReturnState.CANCELLED
            return

        project = get_active_node_tree(context)
        p = project.add_pattern()
        center = sum([Vector(mc.vertex0.co) for mc in moving_curves], Vector((0, 0))) / len(moving_curves)
        p.anchor = center
        for i, mc in enumerate(moving_curves):
            next_i = (i + 1) % len(moving_curves)
            p.add_vertex(Vector(mc.vertex0.co) - center)
            p.add_edge(i, next_i, Vector(mc.handle1.co) - center, Vector(mc.handle2.co) - center,
                       mc.handle1_type, mc.handle2_type, update=False)
        p.ensure_edge_ccw()
        p.generate_mesh()

    def handle_failure(self, context, state: IState):
        self.return_state = ReturnState.CANCELLED

    def fini(self, context: Context):
        if hasattr(self, '_draw_handler') and self._draw_handler:
            bpy.types.SpaceNodeEditor.draw_handler_remove(self._draw_handler, 'WINDOW')
        context.area.tag_redraw()


register, unregister = register_classes_factory((NODE_OT_pattern_create_by_pen,))
