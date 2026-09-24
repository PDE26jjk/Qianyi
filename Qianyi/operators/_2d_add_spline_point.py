import numpy as np
from bpy.props import FloatVectorProperty, BoolProperty
from bpy.types import Context
from bpy.utils import register_classes_factory

from ..utilities.cubic_spline import get_handles_after_split
from ..utilities.geometric_operation import sample_polyline
from ..model.pattern import Pattern, interactive_edit_allowed
from ..model.generator import refuse_generated_edit
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.console import console
from ._2d_operator_base import Operator2DBase
from .. import global_data
from ..declarations import Operators
from ..gizmos.temp_draw_manager import TempDrawManager
from ..gizmos.moving_curve import ProxyPoint, TempPoint
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree


class NODE_OT_add_spline_point(Operator2DBase):
    bl_idname = Operators.AddSplinePoint2D
    bl_label = "add spline point"
    bl_options = {'BLOCKING', 'GRAB_CURSOR', 'REGISTER', 'UNDO'}

    origin_mouse_location: FloatVectorProperty(size=2, default=(0.0, 0.0), options={"SKIP_SAVE"})
    initialized: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        # The mode is not part of the poll: `invoke` puts the editor into this
        # tool's mode, so picking the tool is enough to use it.
        project = get_active_node_tree(context)
        if project is not None and project.nearest_point is not None:
            return True
        return False

    def invoke(self, context, event):
        ensure_edit_mode(context, "EDGE", "ADD_SPLINE_POINT")
        qmyi = context.scene.qmyi

        project = get_active_node_tree(context)

        pattern, edge, add_point_pos, t = project.get_nearest_point_data()
        if refuse_generated_edit(self, project, pattern):
            return {'CANCELLED'}
        if len(edge.render_points) > 200:
            add_point_pos = sample_polyline(edge.render_points, t)
        edge_index = edge.get_index()
        edge_points = [p.co for p in edge.spline_points]
        q = np.array((edge.vertex0.co, *edge_points, edge.vertex1.co))
        old_t = np.r_[0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
        old_t /= old_t[-1]
        insert_at = np.searchsorted(old_t, t, side='right')
        # console.info(old_t, t, insert_at)
        left_idx = max(0, insert_at - 1)
        right_idx = min(len(q) - 1, insert_at)

        def dist_sqr(p1, p2):
            return (p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2

        # Check if new point too close to old points.
        eps = 1  # mm^2
        # console.info(add_point_pos, edge.vertex0.co, edge.vertex1.co)
        # console.info(dist_sqr(add_point_pos, edge.vertex0.co), dist_sqr(add_point_pos, edge.vertex1.co))
        points_to_check = [edge.vertex0.co, edge.vertex1.co, q[left_idx], q[right_idx]]
        for point in points_to_check:
            if dist_sqr(add_point_pos, point) < eps:
                def draw(self, context):
                    self.layout.label(text="points too close together!")

                context.window_manager.popup_menu(draw, title="Error", icon='ERROR')
                return {'CANCELLED'}

        draw_manager: TempDrawManager = global_data.temp_draw_manager
        draw_manager.clear()

        mc = draw_manager.add_moving_curve(edge)
        # Check if intersected when add new point
        temp_point = TempPoint(add_point_pos)
        mc.spline_points.insert(insert_at - 1, temp_point)  # not include endpoint

        h1 = edge.vertex0.co if edge.handle1_type == "VECTOR" else edge.handle1.co
        h2 = edge.vertex1.co if edge.handle2_type == "VECTOR" else edge.handle2.co
        handle_a, handle_b = get_handles_after_split(old_t, q, h1, h2, t)
        mc.handle1 = TempPoint(handle_a)
        mc.handle2 = TempPoint(handle_b)

        mc.update()
        checking_edge_points = []
        for i, e in enumerate(pattern.edges):
            if i == edge_index:
                checking_edge_points.append(mc.render_points[:-1])
            else:
                checking_edge_points.append(e.render_points[:-1])
        checking_edge_points = np.concatenate(checking_edge_points, dtype=np.float32)
        if not interactive_edit_allowed(context, checking_edge_points):
            draw_manager.clear()
            return {'CANCELLED'}

        draw_manager.clear()
        insert_at_final = max(0, min(len(edge.spline_points), insert_at - 1))
        # One Sketch per instance chain: the control point is written once. This
        # panel meshes from it now; the other readers were marked by the write.
        e = pattern.edges[edge_index]
        sp = e.spline_points.add()
        sp.get_temp_data()
        sp.co = temp_point.co
        if insert_at_final != len(e.spline_points) - 1:
            e.spline_points.move(len(e.spline_points) - 1, insert_at_final)
        e.handle1.co = handle_a
        e.handle2.co = handle_b

        pattern.refresh_collection_uuid(e.spline_points)
        # The control point and the handles were written straight into the
        # Sketch's own objects, so the write signal is sent here: the panels that
        # read the Sketch are marked and their display is rebuilt.
        sketch = pattern.sketch
        if sketch is not None:
            sketch.geometry_written()
        # One Sketch serves the whole instance chain, so the control point is
        # one edit for every member: the Sketch builds each of their meshes.
        pattern.require_sketch().rebuild_meshes()
        # The outline moved, so the finder the tools snap against is stale.
        project.clear_edge_finder()
        sp = pattern.edges[edge_index].spline_points[insert_at_final]
        sp.get_temp_data()
        project.selected_vertices.clear()
        v = project.selected_vertices.add()
        v.uuid = sp.global_uuid
        return {'FINISHED'}


register, unregister = register_classes_factory((NODE_OT_add_spline_point,))
