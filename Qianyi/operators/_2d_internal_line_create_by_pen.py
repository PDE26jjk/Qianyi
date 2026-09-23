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
from ..model.qianyi_data import ensure_edit_mode


class NODE_OT_internal_line_create_by_pen(Operator2DBase, StateOperator):
    bl_idname = Operators.InternalLinePen
    bl_label = "internal line pen"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context):
        # The mode is not part of the poll: `setup_state_machine` puts the
        # editor into this tool's mode, so picking the tool is enough to use it.
        project = get_active_node_tree(context)
        return project is not None

    def setup_state_machine(self, context):
        ensure_edit_mode(context, "PATTERN", "INTERNAL_POINT")
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
        # The line goes to every panel of the instance list, by index - which
        # only means the same line while the chain's lines have not drifted.
        # A copy that lost a line would take this one at a different index.
        drifted = [ins.name for ins in pattern.instances
                   if len(ins.internal_lines) != len(pattern.internal_lines)]
        if drifted:
            self.report(
                {'ERROR'},
                f"{', '.join(drifted)} "
                f"{'does not share' if len(drifted) == 1 else 'do not share'} "
                f"{pattern.name}'s internal lines - detach or rebuild "
                f"{'it' if len(drifted) == 1 else 'them'} before drawing one")
            self.return_state = ReturnState.CANCELLED
            return
        # View coordinates to pattern space once, then let the model layer write
        # the same line into every panel of the instance list.
        segments = []
        for mc in state.moving_curves:
            segments.append({
                "p0": pattern.view_to_pattern_pos(mc.vertex0.co),
                "p1": pattern.view_to_pattern_pos(mc.vertex1.co),
                "h1": pattern.view_to_pattern_pos(mc.handle1.co),
                "h2": pattern.view_to_pattern_pos(mc.handle2.co),
                "h1_type": mc.handle1_type,
                "h2_type": mc.handle2_type,
            })
        for ins in pattern.instances:
            ins.add_internal_line(segments, is_loop=state.circle)
            ins.generate_mesh()

    def handle_failure(self, context, state: IState):
        self.return_state = ReturnState.CANCELLED

    def fini(self, context: Context):
        if hasattr(self, '_draw_handler') and self._draw_handler:
            bpy.types.SpaceNodeEditor.draw_handler_remove(self._draw_handler, 'WINDOW')
        context.area.tag_redraw()


register, unregister = register_classes_factory((NODE_OT_internal_line_create_by_pen,))
