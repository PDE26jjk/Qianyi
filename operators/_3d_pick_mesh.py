import bpy
import numpy as np
from bpy_extras import view3d_utils
from bpy.props import FloatVectorProperty, BoolProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory
from mathutils import Vector, geometry

from utilities.console import console_print
from .states.IState import IState
from .states.PointSelectionState import PointPickState, MouseOperator
from .states.StatefulOperator import StateOperator, ReturnState
from .. import global_data
from ..declarations import Operators
from ..utilities.coords_transform import region2view_coord, region3view_coord


def get_camera_frame_data(context):
    """获取当前视口的相机坐标系数据"""
    rv3d = context.region_data
    # 视角矩阵的逆矩阵，其第三列（索引2）就是视口看向的世界方向
    view_matrix = rv3d.view_matrix.inverted()
    view_direction = view_matrix.to_3x3() @ Vector((0, 0, -1))

    return {
        'view_direction': view_direction.normalized(),
        'view_matrix': view_matrix,
        'view_location': view_matrix.to_translation()
    }


def get_mouse_position_on_plane(context, event, plane_point, plane_normal):
    """
    将当前鼠标位置投影到指定的平面上
    plane_point: 平面上的一点（通常是初始命中点）
    plane_normal: 平面的法线（通常是相机的视方向）
    """
    region = context.region
    rv3d = context.region_data
    coord = (event.mouse_region_x, event.mouse_region_y)

    # 1. 计算当前鼠标位置产生的射线
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
    ray_direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)

    # 2. 计算射线与平面的交点
    # 公式：Intersection of line (P0, V) and plane (P_plane, N_plane)
    hit_location = geometry.intersect_line_plane(
        ray_origin,
        ray_origin + ray_direction,
        plane_point,
        plane_normal
    )

    return hit_location


# https://devtalk.blender.org/t/pick-material-under-mouse-cursor/6978/6
def get_triangle_with_scene_ray_cast(context, event):
    """使用 Blender 场景级别的 ray_cast - 最高效"""
    region = context.region
    rv3d = context.region_data
    coord = event.mouse_region_x, event.mouse_region_y

    # get the ray from the viewport and mouse
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord).normalized()
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

    depsgraph = context.evaluated_depsgraph_get()
    # console_print(origin, direction,depsgraph)

    # 调用 ray_cast
    result = context.scene.ray_cast(
        depsgraph=depsgraph,
        origin=origin,
        direction=direction,
        distance=100.0  # 最大距离
    )

    # 结果是命名元组
    # result: (success: bool, location: Vector, normal: Vector, index: int, object: Object, matrix: Matrix)

    success, location, normal, index, obj, matrix = result
    if success:
        return {
            'object': obj,
            'polygon_index': index,
            'location': location,
            'normal': normal,
            'matrix': matrix
        }

    return None


class VIEW3D_OT_qmyi_pick3d(Operator, StateOperator):
    bl_idname = Operators.Pick3D
    bl_label = "pick mesh"
    bl_options = {'BLOCKING', 'REGISTER'}

    origin_mouse_location: FloatVectorProperty(size=2, default=(0.0, 0.0), options={"SKIP_SAVE"})

    # initialized: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        qmyi = context.scene.qmyi
        res = qmyi.simulation.enable_simulation
        console_print("VIEW3D_OT_pick_mesh poll", res)
        return res
        # return True

    def setup_state_machine(self, context):
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)
        console_print("setup_state_machine")
        # context.window_manager.modal_handler_add(self)

        p1state = self.register_state(PointPickState())
        p2state = self.register_state(PointPickState(MouseOperator.RELEASE))
        self.origin_mouse_location = (0.0, 0.0)

        # self.initialized = False
        self.hit = False
        import Qianyi_DP as qydp
        simulator = qydp.simulator

        def cb1(_self, _context):
            co = _self.point_position
            self.origin_mouse_location = co
            res = get_triangle_with_scene_ray_cast(_context, _self.event)
            if res is not None:
                obj = res['object']
                if obj.type == 'MESH' and obj.qmyi_simulation_props.is_pattern_mesh:
                    self.hit = True
                    self.initial_hit_location = res['location']
                    self.hit_obj_index = obj.qmyi_simulation_props.simulation_index
                    self.hit_tri_index = res['polygon_index']
                    self.pick_index = simulator.pick_triangle(self.hit_obj_index, self.hit_tri_index,
                                                              np.array(self.initial_hit_location))
                    console_print(self.pick_index, self.hit_obj_index, self.hit_tri_index, self.initial_hit_location)
            console_print(res)

        p1state.succeed_cb.append(cb1)

        def cb2(_self, _context):
            if not self.hit:
                return
            co = _self.point_position
            loc = list(self.origin_mouse_location)
            offset = list(co[:])
            offset[0] -= loc[0]
            offset[1] -= loc[1]
            cam_data = get_camera_frame_data(context)

            # 计算当前鼠标在“初始点击平面”上的世界坐标
            current_world_pos = get_mouse_position_on_plane(
                context,
                _self.event,
                self.initial_hit_location,
                cam_data['view_direction']
            )
            simulator.pick_triangle_update(self.pick_index, np.array(current_world_pos))
            console_print(current_world_pos)
            # context.area.tag_redraw()

        p2state.data_change_cb.append(cb2)

        def cb3(_self, _context):
            if self.hit:
                simulator.pick_triangle_remove(self.pick_index)

        p2state.succeed_cb.append(cb3)
        self.define_transition(p1state, p2state)

    # def fini(self, context: Context):
    #     # self.draw_manager.clear()
    #     context.area.tag_redraw()


register, unregister = register_classes_factory((VIEW3D_OT_qmyi_pick3d,))
