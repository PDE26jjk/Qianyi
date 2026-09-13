import bpy
from bpy.props import FloatVectorProperty
from bpy.utils import register_classes_factory, register_class
from mathutils import Vector

from .states.IState import IState
from ..utilities.node_tree import get_active_node_tree
from ..utilities.coords_transform import region2view_coord
from ..gizmos.temp_draw_manager import TempDrawManager
from .. import global_data
from .states.PointSelectionState import PointPickState
from ..declarations import Operators, Panels
from .states.StatefulOperator import StateOperator, ReturnState
from bpy.types import Operator, Context


class NODE_OT_add_poly(Operator, StateOperator):
    """添加多边形"""
    bl_idname = Operators.AddPoly
    bl_label = "添加多边形"
    bl_options = {'REGISTER', 'UNDO'}

    # location: FloatVectorProperty(
    #     name="位置",
    #     subtype="XYZ",
    #     size=2,
    #     default=(0.0, 0.0),
    # )
    @classmethod
    def poll(cls, context: Context):
        return get_active_node_tree(context) is not None

    def setup_state_machine(self, context):
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)
        self.draw_manager: TempDrawManager = global_data.temp_draw_manager
        self.draw_manager.clear()

        p1state = self.register_state(PointPickState())
        self.rect = None

        def cb1(_self, _context):
            n1 = len(self.draw_manager.lines)
            self.rect = self.draw_manager.add_Rect()
            co = region2view_coord(context, _self.point_position)
            context.workspace.status_text_set(f"cb1 : {co} ")
            self.rect.set_p1(co)
            self.rect.set_p2(co)
            # context.workspace.status_text_set(f"cb1 : {_self.point_position}")

        p1state.succeed_cb.append(cb1)

        p2state = self.register_state(PointPickState())

        def cb2(_self, _context):
            self.rect.set_p2(region2view_coord(context, _self.point_position))
            context.area.tag_redraw()

        p2state.data_change_cb.append(cb2)

        self.define_transition(p1state, p2state)

    def handle_success(self, context: Context, state):
        node_tree = get_active_node_tree(context)
        if node_tree is not None:
            p = node_tree.add_pattern()
            p.add_vertex(self.rect.l1.p1)
            p.add_vertex(self.rect.l1.p2)
            p.add_vertex(self.rect.l3.p1)
            p.add_vertex(self.rect.l3.p2)
            p.add_edge(0, 1)
            p.add_edge(1, 2)
            p.add_edge(2, 3)
            p.add_edge(3, 0)
            p.ensure_edge_ccw()

    def handle_failure(self, context, state: IState):
        self.return_state = ReturnState.CANCELLED
    def fini(self, context: Context):
        self.draw_manager.clear()
        context.area.tag_redraw()


_register, _unregister = register_classes_factory((NODE_OT_add_poly,))


def register():
    _register()


def unregister():
    _unregister()
