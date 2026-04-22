import bpy
import numpy as np
from bpy.utils import register_classes_factory

from utilities.console import console
from .. import global_data
from .pattern import Pattern

from .fabric import Fabric
from .model_data import ModelData, define_temp_prop
from .sewing import Sewing, calc_sewing_geo_point
from ..declarations import Panels


class UuidType(bpy.types.PropertyGroup):
    uuid: bpy.props.IntProperty(default=-1)


def get_unique_name(collection, base_name):
    if base_name not in collection:
        return base_name

    i = 1
    while f"{base_name}.{i:03d}" in collection:
        i += 1
    return f"{base_name}.{i:03d}"


class QianyiProject(bpy.types.NodeTree, ModelData):
    """ Qianyi Project for editor, a NodeTree"""
    bl_label = "Qianyi Project"
    bl_icon = 'FILE_SCRIPT'
    bl_idname = Panels.QianyiNodeTree

    patterns: bpy.props.CollectionProperty(
        type=Pattern,
        name="patterns",
        description="The patterns of this project",
    )

    sewings: bpy.props.CollectionProperty(
        type=Sewing,
        name="sewings",
        description="The sewings of this project",
    )
    fabrics: bpy.props.CollectionProperty(
        type=Fabric,
        name="fabrics",
        description="The fabrics of this project",
    )

    active_pattern_index: bpy.props.IntProperty(
        default=0,
        min=0,
        name="Active Pattern",
        description="The project editing",
        # update=update_active_pattern_index,
    )
    active_fabric_index: bpy.props.IntProperty(
        default=0,
        min=0,
        name="Active fabric",
        description="The project editing",
        # update=update_active_fabric_index,
    )

    index: bpy.props.IntProperty(
        default=-1,
        description="The index of this node tree in the node tree list",
        name="Index",
    )

    selected_patterns: bpy.props.CollectionProperty(type=UuidType)
    selected_vertices: bpy.props.CollectionProperty(type=UuidType)
    selected_edges: bpy.props.CollectionProperty(type=UuidType)
    selected_sewings: bpy.props.CollectionProperty(type=UuidType)

    # def update(self):
    #     pass
    #
    def calc_sewing_geo_point(self):
        self.refresh_collection_uuid(self.sewings)
        calc_sewing_geo_point(self)

    def get_default_fabric(self):
        if len(self.fabrics) < 1:
            self.fabrics.add()
            self.fabrics[0].name = "Default Fabric"
        return self.fabrics[0]

    def clear_temp_data(self):
        self.initialized = False

    def update_all(self, forced=False):
        if not self.initialized or forced:
            for p in self.patterns:
                f = p.fabric
            self.initialized = True
        # for p in self.patterns:
        #     p.forced_update()

    def get_selected_objects_by_mode(self, mode, submode=None):
        selected_objects = []
        if mode == "PATTERN":
            for uuid in self.selected_patterns:
                selected_objects.append(global_data.get_obj_by_uuid(uuid.uuid, check_uuid=True))
        elif mode == "EDGE":
            if submode == "EDGE_VERTEX":
                for uuid in self.selected_edges:
                    selected_objects.append(global_data.get_obj_by_uuid(uuid.uuid, check_uuid=True))
                for uuid in self.selected_vertices:
                    selected_objects.append(global_data.get_obj_by_uuid(uuid.uuid, check_uuid=True))
        elif mode == "SEWING":
            for uuid in self.selected_sewings:
                selected_objects.append(global_data.get_obj_by_uuid(uuid.uuid, check_uuid=True))
        return selected_objects

    def clear_selected_objects_by_mode(self, mode):
        if mode == "PATTERN":
            self.selected_patterns.clear()
        elif mode == "EDGE":
            self.selected_edges.clear()
            self.selected_vertices.clear()
        elif mode == "SEWING":
            self.selected_sewings.clear()

    def add_sewing(self, side1_line1, side1_pos1, side1_line2, side1_pos2, side1_reverse,
                   side2_line1, side2_pos1, side2_line2, side2_pos2, side2_reverse, update=True):
        sw = self.sewings.add()
        sw.side1.update_data(side1_line1, side1_pos1, side1_line2, side1_pos2, side1_reverse)
        sw.side2.update_data(side2_line1, side2_pos1, side2_line2, side2_pos2, side2_reverse)
        if update:
            try:
                self.calc_sewing_geo_point()
                sw.update()
            except Exception as e:
                console.warning("Failed to add sewing: ", e)
                self.sewings.remove(len(self.sewings) - 1)
                return None
        self.refresh_collection_uuid(self.sewings)
        return sw

    def add_sewing1to1(self, edge1, edge2, side1_reverse=False, side2_revers=True):
        return self.add_sewing(edge1, 0, edge1, 1, side1_reverse, edge2, 1, edge2, 0, side2_revers)

    def get_sewings_for_simulation(self):
        self.calc_sewing_geo_point()
        sewings = []
        for sewing in self.sewings:
            start1, end1 = sewing.sections1
            start2, end2 = sewing.sections2
            ss1 = sewing.side1
            ss2 = sewing.side2
            patterns = (ss1.line1.pattern.mesh_object.qmyi_simulation_props.simulation_index,
                        ss2.line1.pattern.mesh_object.qmyi_simulation_props.simulation_index)
            max_sec = 10000
            sec1 = start1
            sec2 = start2
            stitches = []
            same_order = ss1.reverse ^ ss2.reverse
            while sec1 is not end1 and max_sec > 0:
                if sec1.edge.start_point == -1:
                    sec1.edge.pattern.get_geo_points_unique()
                if sec2.edge.start_point == -1:
                    sec2.edge.pattern.get_geo_points_unique()
                assert sec1.seg == sec2.seg, "sec1.seg != sec2.seg"
                range1 = np.arange(sec1.seg)
                stitches1 = (range1 if not ss1.reverse else range1[
                    ::-1]) + sec1.edge.start_point + sec1.start_point
                stitches2 = (range1 if not ss2.reverse else range1[
                    ::-1]) + sec2.edge.start_point + sec2.start_point
                stitches.append(np.column_stack((stitches1, stitches2)))

                sec1 = sec1.next if not ss1.reverse else sec1.prev
                sec2 = sec2.next if not ss2.reverse else sec2.prev
                max_sec -= 1
            if max_sec == 0:
                raise ValueError("Sections are in different patterns!!!")
            stitches = np.concatenate(stitches)
            sewings.append({'patterns': patterns, 'stitches': stitches, 'angle': 0.})
        return sewings

    def update_edge_finder(self):
        edge_points = []
        edge_point_sizes = []
        matrices = []
        for p in self.patterns:
            ps = p.get_geo_points_unique()
            edge_points.append(ps)
            edge_point_sizes.append(len(ps))
            matrices.append(np.array(p.calc_matrix()))
        edge_points = np.concatenate(edge_points, dtype=np.float32)
        # console.info('edge_point_sizes', edge_point_sizes)
        edge_point_sizes = np.array(edge_point_sizes, dtype=np.int32)
        matrices = np.concatenate(matrices, dtype=np.float32)
        console.info('matrices', matrices)
        from Qianyi_DP import pattern_helper
        pattern_helper.update_edges(edge_points, edge_point_sizes, matrices)
        self.edge_points = edge_points
        self.edge_point_sizes = np.cumsum(edge_point_sizes)

    def find_nearest_point_on_edge(self, query_point):
        if self.edge_points is None:
            self.update_edge_finder()
        from Qianyi_DP import pattern_helper
        res = pattern_helper.find_nearest_edge(query_point)
        # console.info('res', res)
        # console.info('self.edge_point_sizes', self.edge_point_sizes)
        index = res['res_index']
        weight = res['res_weight']
        n = np.searchsorted(self.edge_point_sizes, index, side='left')
        next_index = index + 1
        if self.edge_point_sizes[n] - 1 == index:
            next_index = self.edge_point_sizes[n - 1] if n > 0 else 0
        if self.edge_point_sizes[n] == index:
            n += 1
        pattern_point_offset = 0 if n == 0 else self.edge_point_sizes[n - 1]
        self.edge_point_offset = index - pattern_point_offset

        self.nearest_pattern = n
        # console.info('n', n, self.edge_point_sizes[n])
        # console.info('next_index', next_index)
        self.nearest_point = self.edge_points[index] * (1 - weight) + self.edge_points[next_index] * weight
        # console.warning('self.nearest_point', self.nearest_point)

    def add_pattern(self):
        p = self.patterns.add()
        self.refresh_collection_uuid(self.patterns)
        name = f"pattern_{len(self.patterns):03d}"
        p.name = get_unique_name(self.patterns, name)
        return p

    def remove_patterns(self, patterns_to_delete):
        selected_patterns_uuid = [p.uuid for p in patterns_to_delete]
        del_idx_list = []
        for sw in self.sewings:
            if (sw.side1.line1.pattern.global_uuid in selected_patterns_uuid or
                    sw.side2.line1.pattern.global_uuid in selected_patterns_uuid):
                del_idx_list.append(sw.get_index())

        for i in sorted(del_idx_list, reverse=True):
            self.sewings.remove(i)
        self.selected_sewings.clear()
        self.refresh_collection_uuid(self.sewings)

        del_idx_list = []
        for p in patterns_to_delete:
            if p.uuid != -1:
                obj = global_data.get_obj_by_uuid(p.uuid, check_uuid=False)
                if hasattr(obj, 'mesh_object') and obj.mesh_object is not None:
                    bpy.data.objects.remove(obj.mesh_object)
                if obj is not None:
                    del_idx_list.append(obj.get_index())
                else:
                    console.error('cannot find pattern', p.uuid)
        for i in sorted(del_idx_list, reverse=True):
            self.patterns.remove(i)

        self.refresh_collection_uuid(self.patterns)


define_temp_prop(QianyiProject, "initialized", False)
define_temp_prop(QianyiProject, "edge_points", None)
define_temp_prop(QianyiProject, "edge_point_sizes", None)
define_temp_prop(QianyiProject, "nearest_point", None)
define_temp_prop(QianyiProject, "nearest_pattern", None)
define_temp_prop(QianyiProject, "edge_point_offset", None)
define_temp_prop(QianyiProject, "selected_sewing_edge1", None)

register, unregister = register_classes_factory((UuidType, QianyiProject))
