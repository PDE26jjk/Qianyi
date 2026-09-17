import bpy
import numpy as np
from bpy.props import FloatVectorProperty, BoolProperty
from bpy.types import Context
from bpy.utils import register_classes_factory
from mathutils import Vector

from ..model.pattern_instance import collect_unique_instances
from ..model import pattern
from ..model.internal_line import InternalLine
from ..model.pattern import Pattern
from ..model.generator import refuse_generated_edit
from ..gizmos.moving_curve import MovingCurve
from ..utilities.console import console
from ._2d_operator_base import Operator2DBase
from .states.CurvePenState import CurvePenState
from .states.IState import IState
from .states.StatefulOperator import StateOperator, ReturnState
from .. import global_data
from ..declarations import Operators
from ..gizmos.temp_draw_manager import TempDrawManager
from ..utilities.node_tree import get_active_node_tree


class NODE_OT_internal_line_create_by_pen(Operator2DBase, StateOperator):
    bl_idname = Operators.InternalLinePen
    bl_label = "internal line pen"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context):
        if not context.scene.qmyi.edit_mode == "PATTERN":
            return False
        project = get_active_node_tree(context)
        return project is not None

    def setup_state_machine(self, context):
        # console.success("setup_state_machine")
        context.window_manager.modal_handler_add(self)
        # self.draw_manager: TempDrawManager = global_data.temp_draw_manager
        # self.draw_manager.clear()

        # self.initialized = False
        self.project = get_active_node_tree(context)
        self.pattern = None
        qmyi = context.scene.qmyi
        hover_object = qmyi.hover_object
        if hover_object is not None and hover_object.global_uuid != -1 and isinstance(hover_object, Pattern):
            obj = global_data.get_obj_by_uuid(hover_object.global_uuid, check_uuid=False)
            if obj:
                self.pattern = obj
        if not self.pattern:
            for item in self.project.selected_patterns:
                if item.uuid != -1:
                    obj = global_data.get_obj_by_uuid(item.uuid, check_uuid=False)
                    if obj:
                        self.pattern = obj
                        break
        # A generated panel refuses geometry edits, internal lines included.
        if refuse_generated_edit(self, self.project, self.pattern):
            self.return_state = ReturnState.CANCELLED
            return
        if not self.pattern:
            self.return_state = ReturnState.CANCELLED
            console.info("No pattern found")
            return
        else:
            self.project.selected_patterns.clear()
            item = self.project.selected_patterns.add()
            item.uuid = self.pattern.global_uuid
            self.pattern.is_selected = True

        p1state = self.register_state(CurvePenState())
        p1state.no_blocking = True

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
        pattern = self.pattern
        collect_unique_instances({pattern})
        v_index_offset = len(pattern.vertices)
        # inv_mat = pattern.calc_inv_matrix()
        for mc in state.moving_curves:
            mc.vertex0.co = pattern.view_to_pattern_pos(mc.vertex0.co)
            mc.vertex1.co = pattern.view_to_pattern_pos(mc.vertex1.co)
            mc.handle1.co = pattern.view_to_pattern_pos(mc.handle1.co)
            mc.handle2.co = pattern.view_to_pattern_pos(mc.handle2.co)

        for ins in pattern.instances:
            il: InternalLine = ins.internal_lines.add()
            il.is_loop = state.circle
            vertices_size = len(moving_curves)
            if not state.circle:
                vertices_size += 1
            for i, mc in enumerate(moving_curves):
                ins.add_vertex(mc.vertex0.co)
                next_i = (i + 1) % vertices_size
                il.add_edge(i + v_index_offset, next_i + v_index_offset, mc.handle1.co, mc.handle2.co,
                            mc.handle1_type, mc.handle2_type, update=False)
            if not state.circle:
                ins.add_vertex(moving_curves[-1].vertex1.co)
            ins.recreate_sections()
            ins.forced_update()
            ins.generate_mesh()

    def handle_failure(self, context, state: IState):
        self.return_state = ReturnState.CANCELLED

    def fini(self, context: Context):
        if hasattr(self, '_draw_handler') and self._draw_handler:
            bpy.types.SpaceNodeEditor.draw_handler_remove(self._draw_handler, 'WINDOW')
        context.area.tag_redraw()


register, unregister = register_classes_factory((NODE_OT_internal_line_create_by_pen,))
