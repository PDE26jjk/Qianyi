import bpy
import numpy as np
from bpy.utils import register_classes_factory

from .pattern import Pattern

from .fabric import Fabric
from .model_data import ModelData, define_temp_prop
from .sewing import Sewing, calc_sewing_geo_point
from ..declarations import Panels


class UuidType(bpy.types.PropertyGroup):
    uuid: bpy.props.IntProperty(default=-1)


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

    # def update(self):
    #     pass
    #
    def calc_sewing_geo_point(self):
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

    def get_sewings_for_simulation(self):
        self.calc_sewing_geo_point()
        sewings = []
        for sewing in self.sewings:
            start1, end1 = sewing.sections1
            start2, end2 = sewing.sections2
            patterns = (sewing.get_side1().line1.pattern.mesh_object.qmyi_simulation_props.simulation_index,
                        sewing.get_side2().line1.pattern.mesh_object.qmyi_simulation_props.simulation_index)
            max_sec = 10000
            sec = start1
            sec2 = start2
            stitches = []
            while sec is not end1 and max_sec > 0:
                if sec.edge.start_point == -1:
                    sec.edge.pattern.get_geo_points_unique()
                if sec2.edge.start_point == -1:
                    sec2.edge.pattern.get_geo_points_unique()
                assert sec.seg == sec2.seg, "sec.seg != sec2.seg"

                stitches1 = np.arange(sec.seg) + sec.edge.start_point + sec.start_point
                stitches2 = np.arange(sec.seg) + sec2.edge.start_point + sec2.start_point
                stitches.append(np.column_stack((stitches1, stitches2)))

                sec = sec.next
                sec2 = sec2.next if sewing.reverse else sec2.prev
                max_sec -= 1
            if max_sec == 0:
                raise ValueError("Sections are in different patterns!!!")
            stitches = np.concatenate(stitches)
            sewings.append({'patterns': patterns, 'stitches': stitches, 'angle': 0.})
        return sewings

define_temp_prop(QianyiProject, "initialized", False)

register, unregister = register_classes_factory((UuidType, QianyiProject))
