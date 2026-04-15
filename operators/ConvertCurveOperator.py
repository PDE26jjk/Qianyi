import bpy
from bpy.props import FloatVectorProperty
from bpy.utils import register_classes_factory, register_class
from mathutils import Vector

from utilities.console import Console, console
from ..utilities.node_tree import get_active_node_tree
from ..utilities.coords_transform import region2view_coord
from ..gizmos.temp_draw_manager import TempDrawManager
from .. import global_data
from .states.PointSelectionState import PointPickState
from ..model.pattern import Pattern
from ..declarations import Operators, Panels
from .states.StatefulOperator import StateOperator
from bpy.types import Operator, Context
import numpy as np


class NODE_OT_convert_curve(Operator):
    """添加多边形"""
    bl_idname = Operators.ConvertCurve
    bl_label = "添加多边形"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context):
        if len(context.selected_objects) > 0:
            return get_active_node_tree(context) is not None
        return True

    def invoke(self, context, event):
        node_tree = get_active_node_tree(context)
        if node_tree is None:
            return {"FINISHED"}

        selected_curves = [c for c in bpy.context.selected_objects if c.type == 'CURVE']
        if len(selected_curves) == 0:
            return {"FINISHED"}

        for curve in selected_curves:
            transform_matrix = curve.matrix_world
            for spline in curve.data.splines:
                if spline.type == 'BEZIER':
                    p: Pattern = node_tree.add_pattern()
                    points = []

                    # 贝塞尔曲线 - 获取控制点和句柄
                    for i, bezier_point in enumerate(spline.bezier_points):
                        scale = 1000.0
                        point = {}
                        # 对坐标应用完整的变换矩阵（包含缩放、旋转、位移）
                        co_world = transform_matrix @ bezier_point.co
                        handle_left_world = transform_matrix @ bezier_point.handle_left
                        handle_right_world = transform_matrix @ bezier_point.handle_right

                        # 转换为2D坐标并应用单位缩放
                        co_local = np.array(co_world[:2]) * scale
                        point["handle_left"] = np.array(handle_left_world[:2]) * scale
                        point["handle_right"] = np.array(handle_right_world[:2]) * scale

                        # # 获取坐标（局部空间）
                        # co_local = np.array(bezier_point.co[:2]) * scale
                        # point["handle_left"] = np.array(bezier_point.handle_left[:2]) * scale
                        # point["handle_right"] = np.array(bezier_point.handle_right[:2]) * scale
                        handle_left_type = bezier_point.handle_left_type
                        handle_right_type = bezier_point.handle_right_type
                        if handle_left_type != "VECTOR":
                            point["handle_left_type"] = "FREE"
                        else:
                            point["handle_left_type"] = "VECTOR"
                        if handle_right_type != "VECTOR":
                            point["handle_right_type"] = "FREE"
                        else:
                            point["handle_right_type"] = "VECTOR"
                        points.append(point)
                        p.add_vertex(co_local)

                    for i in range(len(points)):
                        next_i = (i + 1) % len(points)
                        point = points[i]
                        next_point = points[next_i]
                        e = p.add_edge(i, next_i, "BESSEL", point["handle_right"], next_point["handle_left"],
                                       point["handle_right_type"], next_point["handle_left_type"])
                    p.ensure_edge_ccw()

        context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory((NODE_OT_convert_curve,))
