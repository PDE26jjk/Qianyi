import numpy as np
from bpy.types import Context
from bpy.utils import register_classes_factory

from ..model.pattern_instance import collect_unique_instances
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
            selected_patterns = project.get_selected_objects_by_mode("PATTERN")
            if len(selected_patterns) == 0:
                return {"CANCELLED"}
            project.remove_patterns(selected_patterns)

        elif edit_mode == "EDGE":
            draw_manager: TempDrawManager = global_data.temp_draw_manager
            draw_manager.clear()
            pattern_set = set()
            point_set = set()
            objs = project.get_selected_objects_by_mode("EDGE", "EDGE_VERTEX")
            for obj in objs:
                pattern_set.add(obj.pattern)
            pattern_set = collect_unique_instances(pattern_set)
            for p in pattern_set:
                for v in p.vertices:
                    v.impacted = False
            objs = {o for o in objs if o.pattern.impacted}
            for obj in objs:
                if isinstance(obj, Edge2D):
                    point_set.add(obj.vertex0)
                    point_set.add(obj.vertex1)
                elif isinstance(obj, Vertex2D):
                    point_set.add(obj)
            for p in point_set:
                p.impacted = True

            res = None  # intersect test result
            sewing_map = dict()

            def insert_sewing_map(idx, sw):
                if idx not in sewing_map:
                    sewing_map[idx] = []
                sewing_map[idx].append(sw)

            for s in project.sewings:
                s.impacted = False
                insert_sewing_map(s.side1.line1_uuid, s)
                insert_sewing_map(s.side1.line2_uuid, s)
                insert_sewing_map(s.side2.line1_uuid, s)
                insert_sewing_map(s.side2.line2_uuid, s)

            for p in pattern_set:
                edges_del = []
                edges_rest = []  # [(e_uuid,e_v0_uuid,e_new_v1_uuid),...]
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
                    console.info(e, mc.render_points[:-1])
                checking_edge_points = np.concatenate(checking_edge_points, dtype=np.float32)
                from Qianyi_DP import pattern_helper
                res = pattern_helper.check_edge_intersection(checking_edge_points)
                # console.warning(checking_edge_points)
                console.warning(res)
                if res['intersected']:
                    break
                for i in sorted(edges_del, reverse=True):
                    for ins in p.instances:
                        edge_uuid = ins.edges[i].global_uuid
                        if edge_uuid in sewing_map:
                            for s in sewing_map[edge_uuid]:
                                s.impacted = True
                            del sewing_map[edge_uuid]
                        ins.edges.remove(i)
                for ins in p.instances:
                    ins.refresh_collection_uuid(ins.edges)
                vertices_del = [v.get_index() for v in p.vertices if v.impacted]
                for i in sorted(vertices_del, reverse=True):
                    for ins in p.instances:
                        ins.vertices.remove(i)
                for ins in p.instances:
                    ins.refresh_collection_uuid(ins.vertices)
                for e_ in edges_rest:
                    e_index = global_data.get_obj_by_uuid(e_[0]).get_index()
                    v0_index = global_data.get_obj_by_uuid(e_[1]).get_index()
                    v1_index = global_data.get_obj_by_uuid(e_[2]).get_index()
                    for ins in p.instances:
                        e = ins.edges[e_index]
                        e.vertex_index[0] = v0_index
                        e.vertex_index[1] = v1_index
                for ins in p.instances:
                    ins.create_sections()
                    ins.forced_update()
                    ins.generate_mesh()
            if res is None or res['intersected']:
                def draw(self, context):
                    self.layout.label(text="edges intersected!")

                context.area.tag_redraw()
                context.window_manager.popup_menu(draw, title="Error", icon='ERROR')
            draw_manager.clear()
            sewings_del = [s.get_index() for s in project.sewings if s.impacted]
            for i in sorted(sewings_del, reverse=True):
                project.sewings.remove(i)
            if len(sewings_del):
                project.refresh_collection_uuid(project.sewings)
                project.selected_sewings.clear()

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
