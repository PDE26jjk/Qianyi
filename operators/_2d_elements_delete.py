import numpy as np
from bpy.types import Context
from bpy.utils import register_classes_factory

from ..model.sewing import SewingOneSide
from ..gizmos.moving_curve import TempPoint
from ..model.geometry import Edge2D, Vertex2D
from utilities.console import console_print, console
from ._2d_operator_base import Operator2DBase
from .. import global_data
from ..declarations import Operators
from ..gizmos.temp_draw_manager import TempDrawManager
from ..utilities.node_tree import get_active_node_tree


class NODE_OT_elements_delete(Operator2DBase):
    bl_idname = Operators.ElementsDelete2D
    bl_label = "elements delete"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context):
        project = get_active_node_tree(context)
        return project is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        qmyi = context.scene.qmyi
        edit_mode = qmyi.edit_mode
        project = get_active_node_tree(context)

        if edit_mode == "PATTERN":
            selected_patterns = list(project.selected_patterns)
            if len(selected_patterns) == 0:
                return {"CANCELLED"}
            project.remove_patterns(selected_patterns)
            # selected_patterns_uuid = [p.uuid for p in selected_patterns]
            # del_idx_list = []
            # for sw in project.sewings:
            #     if (sw.side1.line1.pattern.global_uuid in selected_patterns_uuid or
            #             sw.side2.line1.pattern.global_uuid in selected_patterns_uuid):
            #         del_idx_list.append(sw.get_index())
            #
            # for i in sorted(del_idx_list, reverse=True):
            #     project.sewings.remove(i)
            # project.selected_sewings.clear()
            # project.refresh_collection_uuid(project.sewings)
            #
            # del_idx_list = []
            # for p in selected_patterns:
            #     if p.uuid != -1:
            #         obj = global_data.get_obj_by_uuid(p.uuid, check_uuid=False)
            #         if obj is not None:
            #             del_idx_list.append(obj.get_index())
            #         else:
            #             console.error('cannot find pattern', p.uuid)
            # for i in sorted(del_idx_list, reverse=True):
            #     project.patterns.remove(i)

            project.refresh_collection_uuid(project.patterns)
        elif edit_mode == "EDGE":
            draw_manager: TempDrawManager = global_data.temp_draw_manager
            draw_manager.clear()
            pattern_set = set()
            point_set = set()
            objs = project.get_selected_objects_by_mode("EDGE", "EDGE_VERTEX")
            for obj in objs:
                pattern_set.add(obj.pattern)
            for p in pattern_set:
                p.calc_inv_matrix()
                for v in p.vertices:
                    v.impacted = False
            for obj in objs:
                if isinstance(obj, Edge2D):
                    point_set.add(obj.vertex0)
                    point_set.add(obj.vertex1)
                elif isinstance(obj, Vertex2D):
                    point_set.add(obj)
            for p in point_set:
                p.impacted = True
            res = None
            for p in pattern_set:
                edges_del = []
                edges_rest = []
                for e in p.edges:
                    if e.vertex0.impacted:
                        edges_del.append(e.get_index())
                    else:
                        edges_rest.append([e, e.vertex0.global_uuid])
                if len(edges_rest) < 2:
                    console.error('rest edges too few!')
                    break
                checking_edge_points = []
                for e in edges_rest:
                    start_ind = e[0].get_index()
                    ind = (start_ind + 1) % len(p.edges)
                    while ind != start_ind and p.edges[ind].vertex0.impacted:
                        ind = (ind + 1) % len(p.edges)
                    new_vertex = p.edges[ind].vertex0
                    e.append(new_vertex.global_uuid)
                    mc = draw_manager.add_moving_curve(e[0])
                    e[0] = e[0].global_uuid
                    mc.vertex1 = TempPoint(new_vertex.co)
                    mc.update()
                    checking_edge_points.append(mc.render_points[:-1])
                    console.info(e,mc.render_points[:-1])
                checking_edge_points = np.concatenate(checking_edge_points, dtype=np.float32)
                from Qianyi_DP import pattern_helper
                res = pattern_helper.check_edge_intersection(checking_edge_points)
                console.warning(checking_edge_points)
                console.warning(res)
                if res['intersected']:
                    break
                for i in sorted(edges_del, reverse=True):
                    p.edges.remove(i)
                p.refresh_collection_uuid(p.edges)
                vertices_del = [v.get_index() for v in p.vertices if v.impacted]
                for i in sorted(vertices_del, reverse=True):
                    p.vertices.remove(i)
                p.refresh_collection_uuid(p.vertices)
                for e_ in edges_rest:
                    e = global_data.get_obj_by_uuid(e_[0])
                    e.vertex_index[0] = global_data.get_obj_by_uuid(e_[1]).get_index()
                    e.vertex_index[1] = global_data.get_obj_by_uuid(e_[2]).get_index()
                p.create_sections()
                p.forced_update()
                p.generate_mesh()
            if res is None or res['intersected']:
                def draw(self, context):
                    self.layout.label(text="edges intersected!")

                context.area.tag_redraw()
                context.window_manager.popup_menu(draw, title="Error", icon='ERROR')
            draw_manager.clear()
        elif edit_mode == "SEWING":
            objs = project.get_selected_objects_by_mode("SEWING")
            del_idx_list = []
            for obj in objs:
                if isinstance(obj, SewingOneSide):
                    del_idx_list.append(obj.sewing.get_index())
            for i in sorted(del_idx_list, reverse=True):
                project.sewings.remove(i)
            project.refresh_collection_uuid(project.sewings)
        project.clear_selected_objects_by_mode(edit_mode)
        context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory((NODE_OT_elements_delete,))
