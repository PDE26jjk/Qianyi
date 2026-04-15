import numpy as np
from bpy.props import FloatVectorProperty, BoolProperty
from bpy.types import Context
from bpy.utils import register_classes_factory

from ..model.geometry import Edge2D, Vertex2D
from utilities.console import console
from ._2d_operator_base import Operator2DBase
from .states.IState import IState
from .states.PointSelectionState import PointPickState
from .states.StatefulOperator import StateOperator, ReturnState
from .. import global_data
from ..declarations import Operators
from ..gizmos.temp_draw_manager import TempDrawManager
from ..gizmos.moving_curve import ProxyPoint
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree


class NODE_OT_edge_mode_move(Operator2DBase, StateOperator):
    bl_idname = Operators.EdgeElementsMove2D
    bl_label = "edge mode move"
    bl_options = {'BLOCKING', 'GRAB_CURSOR', 'REGISTER', 'UNDO'}

    origin_mouse_location: FloatVectorProperty(size=2, default=(0.0, 0.0), options={"SKIP_SAVE"})
    initialized: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        if not context.scene.qmyi.edit_mode == "EDGE":
            return False
        project = get_active_node_tree(context)
        if project is not None:
            if len(project.get_selected_objects_by_mode("EDGE", "EDGE_VERTEX")) > 0:
                return True
        return False

    def setup_state_machine(self, context):
        # console.info("in setup_state_machine")
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)
        self.draw_manager: TempDrawManager = global_data.temp_draw_manager
        self.draw_manager.clear()

        p1state = self.register_state(PointPickState())
        start_point = (0.0, 1e-6)
        self.origin_mouse_location = start_point
        self.initialized = False
        self.project = get_active_node_tree(context)

        move_point_set = set()
        # move_edges = []
        self.moving_curves = []
        self.pattern_set = set()
        self.point_proxys = []
        objs = self.project.get_selected_objects_by_mode("EDGE", "EDGE_VERTEX")
        console.info(objs)
        for obj in objs:
            self.pattern_set.add(obj.pattern)
        for p in self.pattern_set:
            p.calc_inv_matrix()
            for v in p.vertices:
                v.impacted = False
        for obj in objs:
            if isinstance(obj, Edge2D):
                move_point_set.add(obj.vertex0)
                move_point_set.add(obj.vertex1)
            elif isinstance(obj, Vertex2D):
                move_point_set.add(obj)
        for p in move_point_set:
            p.impacted = True

        for point in move_point_set:
            self.point_proxys.append(ProxyPoint(point))

        for p in self.pattern_set:
            for e in p.edges:
                if e.vertex0.impacted or e.vertex1.impacted or e.handle1.impacted or e.handle2.impacted:
                    if e.vertex0.impacted or e.vertex1.impacted:
                        mc = self.draw_manager.add_moving_curve_whole(e)
                    else:
                        mc = self.draw_manager.add_moving_curve(e)
                    # move_edges.append(e)
                    self.moving_curves.append(mc)
                    e.proxy = mc
                else:
                    e.proxy = None
        # console.info(self.moving_curves)
        for p in move_point_set:
            p.impacted = False  # reset
        self.updated = False
        def cb1(_self, _context):
            co = region2view_coord(context, _self.point_position)
            if not self.initialized:
                self.initialized = True
                self.origin_mouse_location = co
                self.origin_pattern_locations = {}
                return
            self.updated = True
            loc = list(self.origin_mouse_location)
            offset = list(co)
            offset[0] -= loc[0]
            offset[1] -= loc[1]
            for p in self.point_proxys:
                p.update_offset(offset)
            for mc in self.moving_curves:
                mc.update()

            context.area.tag_redraw()

        p1state.data_change_cb.append(cb1)

    def handle_success(self, context: Context, state):
        if not self.updated:
            self.return_state = ReturnState.CANCELLED
            return
        res = None
        for p in self.pattern_set:
            checking_edge_points = []
            for e in p.edges:
                checking_points = e.render_points if e.proxy is None else e.proxy.render_points
                checking_edge_points.append(checking_points[:-1])
            checking_edge_points = np.concatenate(checking_edge_points,dtype=np.float32)
            from Qianyi_DP import pattern_helper
            res = pattern_helper.check_edge_intersection(checking_edge_points)
            # console.warning(res)
            if res['intersected']:
                break
        if res['intersected']:
            def draw(self, context):
                self.layout.label(text="edges intersected!")
            context.window_manager.popup_menu(draw, title="Error", icon='ERROR')
            self.return_state = ReturnState.CANCELLED
            return

        for p in self.point_proxys:
            p.apply_proxy()
        for mc in self.moving_curves:
            mc.apply_moving()
        for p in self.pattern_set:
            p.forced_update()
            p.generate_mesh()

    def handle_failure(self, context, state: IState):
        self.return_state = ReturnState.CANCELLED

    def fini(self, context: Context):
        self.draw_manager.clear()
        context.area.tag_redraw()


register, unregister = register_classes_factory((NODE_OT_edge_mode_move,))
