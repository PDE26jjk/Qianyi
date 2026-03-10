from bpy.props import FloatVectorProperty, BoolProperty
from bpy.types import Context
from bpy.utils import register_classes_factory

from utilities.console import console_print
from ._2d_operator_base import Operator2DBase
from .states.IState import IState
from .states.PointSelectionState import PointPickState
from .states.StatefulOperator import StateOperator, ReturnState
from .. import global_data
from ..declarations import Operators
from ..gizmos.temp_draw_manager import TempDrawManager
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree


class NODE_OT_pattern_move(Operator2DBase, StateOperator):
    bl_idname = Operators.PatternMove2D
    bl_label = "pattern move"
    bl_options = {'BLOCKING', 'GRAB_CURSOR', 'REGISTER', 'UNDO'}

    origin_mouse_location: FloatVectorProperty(size=2, default=(0.0, 0.0), options={"SKIP_SAVE"})
    initialized: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        project = get_active_node_tree(context)
        if project is not None:
            if len(project.selected_patterns) > 0:
                return True
        return False

    def setup_state_machine(self, context):
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)
        # self.draw_manager: TempDrawManager = global_data.temp_draw_manager
        # self.draw_manager.clear()

        p1state = self.register_state(PointPickState())
        start_point = (0.0, 1e-6)
        self.origin_mouse_location = start_point
        self.initialized = False
        self.project = get_active_node_tree(context)

        def cb1(_self, _context):
            co = region2view_coord(context, _self.point_position)
            if not self.initialized:
                self.initialized = True
                self.origin_mouse_location = co
                self.origin_pattern_locations = {}
                for item in self.project.selected_patterns:
                    if item.uuid != -1:
                        obj = global_data.get_obj_by_uuid(item.uuid, check_uuid=False)
                        if obj:
                            self.origin_pattern_locations[item.uuid] = list(obj.anchor)
                return
            loc = list(self.origin_mouse_location)
            offset = list(co)
            offset[0] -= loc[0]
            offset[1] -= loc[1]
            for item in self.project.selected_patterns:
                if item.uuid in self.origin_pattern_locations:
                    obj = global_data.get_obj_by_uuid(item.uuid, check_uuid=False)
                    if obj:
                        target_location = self.origin_pattern_locations[item.uuid][:]
                        target_location[0] += offset[0]
                        target_location[1] += offset[1]
                        obj.anchor = target_location

            # context.workspace.status_text_set(f"cb1 else: {loc, offset}")
            context.area.tag_redraw()

        p1state.data_change_cb.append(cb1)

    # def handle_success(self, context: Context, state):
    #     node_tree = get_active_node_tree(context)
        # self.return_state = ReturnState.CANCELLED

    def handle_failure(self, context, state: IState):
        for item in self.project.selected_patterns:
            if item.uuid in self.origin_pattern_locations:
                obj = global_data.get_obj_by_uuid(item.uuid, check_uuid=False)
                if obj:
                    obj.anchor = self.origin_pattern_locations[item.uuid]
        self.return_state = ReturnState.CANCELLED

    def fini(self, context: Context):
        # self.draw_manager.clear()
        context.area.tag_redraw()


register, unregister = register_classes_factory((NODE_OT_pattern_move,))
