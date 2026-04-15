import numpy as np
from bpy.props import FloatVectorProperty, BoolProperty
from bpy.types import Context
from bpy.utils import register_classes_factory

from ..model.geometry import Vertex2D
from ..model.pattern import Pattern
from utilities.console import console
from ._2d_operator_base import Operator2DBase
from .. import global_data
from ..declarations import Operators
from ..gizmos.temp_draw_manager import TempDrawManager
from ..gizmos.moving_curve import ProxyPoint, TempPoint
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree


class NODE_OT_add_vertex(Operator2DBase):
    bl_idname = Operators.AddVertex2D
    bl_label = "add vertex"
    bl_options = {'BLOCKING', 'GRAB_CURSOR', 'REGISTER', 'UNDO'}

    origin_mouse_location: FloatVectorProperty(size=2, default=(0.0, 0.0), options={"SKIP_SAVE"})
    initialized: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        qmyi = context.scene.qmyi
        if not qmyi.edit_mode == "EDGE" or not qmyi.edit_sub_mode == "ADD_VERTEX":
            return False
        project = get_active_node_tree(context)
        if project is not None and project.nearest_point is not None:
            return True
        return False

    def invoke(self, context, event):
        qmyi = context.scene.qmyi

        project = get_active_node_tree(context)

        pattern: Pattern = project.patterns[project.nearest_pattern]
        point_offsets = [edge.start_point for edge in pattern.edges]
        edge_index = np.searchsorted(point_offsets, project.edge_point_offset, side='right') - 1
        # console.warning('edge_index', edge_index,point_offsets, project.edge_point_offset)
        edge = pattern.edges[edge_index]
        add_point_pos = project.nearest_point

        def dist_sqr(p1, p2):
            return (p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2

        eps = 1  # mm^2
        console.info(add_point_pos, edge.vertex0.co, edge.vertex1.co)
        console.info(dist_sqr(add_point_pos, edge.vertex0.co), dist_sqr(add_point_pos, edge.vertex1.co))
        if dist_sqr(add_point_pos, edge.vertex0.co) < eps or dist_sqr(add_point_pos, edge.vertex1.co) < eps:
            console.info(qmyi.hover_object)

            def draw(self, context):
                self.layout.label(text="points too close together!")

            context.window_manager.popup_menu(draw, title="Error", icon='ERROR')
            return {'CANCELLED'}

        draw_manager: TempDrawManager = global_data.temp_draw_manager
        draw_manager.clear()

        mc1 = draw_manager.add_moving_curve(edge)
        mc2 = draw_manager.add_moving_curve(edge)
        console.warning('add_point_pos', add_point_pos, project.nearest_point)

        temp_point = TempPoint(add_point_pos)
        mc1.vertex1 = temp_point
        mc1.handle2 = temp_point
        mc2.vertex0 = temp_point
        mc2.handle1 = temp_point
        mc1.update()
        mc2.update()
        checking_edge_points = []
        for i, e in enumerate(pattern.edges):
            if i == edge_index:
                checking_edge_points.append(mc1.render_points[:-1])
                checking_edge_points.append(mc2.render_points[:-1])
            else:
                checking_edge_points.append(e.render_points[:-1])
        checking_edge_points = np.concatenate(checking_edge_points, dtype=np.float32)
        from Qianyi_DP import pattern_helper
        res = pattern_helper.check_edge_intersection(checking_edge_points)
        console.warning(res)
        if res['intersected']:
            def draw(self, context):
                self.layout.label(text="edges intersected!")

            context.window_manager.popup_menu(draw, title="Error", icon='ERROR')
            draw_manager.clear()
            return {'CANCELLED'}

        draw_manager.clear()
        v_index = pattern.add_vertex(temp_point.co)
        pattern.add_edge(v_index, edge.vertex_index[1], edge.type,update=False)
        edge.vertex_index[1] = v_index
        if edge_index + 1 != len(pattern.edges):
            pattern.edges.move(len(pattern.edges) - 1, edge_index + 1)
        pattern.forced_update()
        return {'FINISHED'}


register, unregister = register_classes_factory((NODE_OT_add_vertex,))
