import numpy as np
from bpy.props import FloatVectorProperty, BoolProperty
from bpy.types import Context
from bpy.utils import register_classes_factory

from ..utilities.cubic_spline import get_handles_after_split, compute_split_handles
from ..utilities.geometric_operation import split_bezier
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


class NODE_OT_add_vertex(Operator2DBase):
    bl_idname = Operators.AddVertex2D
    bl_label = "add vertex"
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
        ensure_edit_mode(context, "EDGE", "ADD_VERTEX")
        qmyi = context.scene.qmyi

        project = get_active_node_tree(context)

        pattern, edge, add_point_pos, t = project.get_nearest_point_data()
        if refuse_generated_edit(self, project, pattern):
            return {'CANCELLED'}
        edge_index = edge.get_index()
        edge_points = [p.co for p in edge.spline_points]
        q = np.array((edge.vertex0.co, *edge_points, edge.vertex1.co))
        old_t = np.r_[0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
        old_t /= old_t[-1]
        insert_at = np.searchsorted(old_t, t, side='right')
        insert_at_final = max(0, min(len(edge.spline_points), insert_at - 1))
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

        mc1 = draw_manager.add_moving_curve(edge)
        mc2 = draw_manager.add_moving_curve(edge)
        # Check if intersected when add new point
        temp_point = TempPoint(add_point_pos)
        handle_a = handle_b = handle_c = handle_d = temp_point
        h1 = edge.vertex0.co if edge.handle1_type == "VECTOR" else edge.handle1.co
        h2 = edge.vertex1.co if edge.handle2_type == "VECTOR" else edge.handle2.co

        is_straight_line = edge.handle1_type == "VECTOR" and edge.handle2_type == "VECTOR"
        is_bz = len(edge.spline_points) == 0
        if is_bz:
            if not is_straight_line:
                q = np.array([edge.vertex0.co, edge.handle1.co, edge.handle2.co, edge.vertex1.co])
                split_point, left_curve, right_curve = split_bezier(q, t)
                p0, m0, m3, m5 = left_curve
                m5, m4, m2, p3 = right_curve
                console.info(f"nearst_point:{add_point_pos}, split_point: {split_point},")
                handle_a, handle_b, handle_c, handle_d = TempPoint(m0), TempPoint(m3), TempPoint(m4), TempPoint(m2)
        else:
            handle_a_co, handle_d_co = get_handles_after_split(old_t, q, h1, h2, t)
            handle_b_co, handle_c_co = compute_split_handles(old_t, q, t,
                                                             None if edge.handle1_type == "VECTOR" else h1,
                                                             None if edge.handle2_type == "VECTOR" else h2)
            handle_a, handle_b, handle_c, handle_d = (TempPoint(handle_a_co), TempPoint(handle_b_co),
                                                      TempPoint(handle_c_co), TempPoint(handle_d_co))

        if not is_straight_line:
            mc1.handle2_type = "VECTOR"
            mc2.handle1_type = "VECTOR"
        mc1.vertex1 = temp_point
        mc1.handle1 = handle_a
        mc1.handle2 = handle_b
        mc2.vertex0 = temp_point
        mc2.handle1 = handle_c
        mc2.handle2 = handle_d
        console.info("insert_at_final",insert_at_final)
        if not is_bz:
            mc2.spline_points = mc1.spline_points[insert_at_final:]
            mc1.spline_points = mc1.spline_points[:insert_at_final]

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
        if not interactive_edit_allowed(context, checking_edge_points):
            draw_manager.clear()
            return {'CANCELLED'}

        draw_manager.clear()
        spline_points_size = len(edge.spline_points)
        console.info("old edge:", edge.vertex0.co, edge.vertex1.co, [p.co for p in edge.spline_points])
        # One Sketch per instance chain: the split is written once. This pattern
        # meshes from it now; the other readers of the Sketch were marked by the
        # write and rebuild when a consumer asks them for a mesh.
        v_index = pattern.add_vertex(temp_point.co)
        # Adding to a collection retires every wrapper it handed out before, so
        # each edge is read back by its place after the write that moved it: the
        # old edge is written before the new one exists, and both are read again
        # after that.
        e = pattern.edges[edge_index]
        old_end = int(e.vertex_index[1])
        old_end_type = e.handle2_type
        e.handle1.co = handle_a.co
        e.handle2.co = handle_b.co
        handle_type = "ALIGNED" if not is_straight_line else "VECTOR"
        new_edge = pattern.add_edge(v_index, old_end,
                                    control1=handle_c.co, control2=handle_d.co,
                                    handle1_type=handle_type, handle2_type=old_end_type,
                                    update=False)
        if not is_bz:
            e = pattern.edges[edge_index]
            new_edge = pattern.edges[len(pattern.edges) - 1]
            for i in range(insert_at_final, spline_points_size):
                point = new_edge.spline_points.add()
                point.get_temp_data()
                point.co = e.spline_points[i].co
            for i in range(insert_at_final, spline_points_size).__reversed__():
                e.spline_points.remove(i)
            # Both collections were rewritten, and adding or removing retires the
            # wrappers they handed out before: the map has to name the ones they
            # hold now, or a pick cannot read the control points back.
            pattern.refresh_collection_uuid(e.spline_points)
            pattern.refresh_collection_uuid(new_edge.spline_points)

        e = pattern.edges[edge_index]
        e.handle2_type = handle_type
        e.vertex_index[1] = v_index
        if edge_index + 2 != len(pattern.edges):
            pattern.edges.move(len(pattern.edges) - 1, edge_index + 1)
        pattern.refresh_collection_uuid(pattern.vertices)
        pattern.refresh_collection_uuid(pattern.edges)

        # One Sketch serves the whole instance chain, so the new point is one
        # edit for every member: the Sketch builds each of their meshes.
        pattern.require_sketch().rebuild_meshes()
        # The outline changed, so the finder the tools snap against is stale:
        # without this the next click snaps to the shape that used to be there,
        # and its offsets no longer fit the edges the pattern has now.
        project.clear_edge_finder()
        p = pattern.vertices[len(pattern.vertices) - 1]
        p.get_temp_data()
        project.selected_vertices.clear()
        v = project.selected_vertices.add()
        v.uuid = p.global_uuid
        return {'FINISHED'}


register, unregister = register_classes_factory((NODE_OT_add_vertex,))
