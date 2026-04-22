import bpy
import numpy as np
from bpy.types import Operator, Context
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.pattern import Pattern
from ..utilities.node_tree import get_active_node_tree


class NODE_OT_qmyi_generate_all_mesh(Operator):
    """generate-all_mesh"""
    bl_idname = Operators.GenerateAllMesh
    bl_label = "GenerateAllMesh"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context):
        return get_active_node_tree(context) is not None

    def invoke(self, context, event):
        project = get_active_node_tree(context)
        project.calc_sewing_geo_point()
        for p in project.patterns:
            p.generate_mesh()
        context.area.tag_redraw()
        return {"FINISHED"}

class NODE_OT_qmyi_RemoveAllSimulationData(Operator):
    bl_idname = Operators.RemoveAllSimulationData
    bl_label = "RemoveAllSimulationData"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context):
        return get_active_node_tree(context) is not None

    def invoke(self, context, event):
        project = get_active_node_tree(context)
        for p in project.patterns:
            if p.mesh_object is not None:
                sim_pros = p.mesh_object.qmyi_simulation_props
                sim_pros.remove_shape_key(sim_pros.simulation_key_name)
        context.area.tag_redraw()
        return {"FINISHED"}

register, unregister = register_classes_factory((NODE_OT_qmyi_generate_all_mesh,NODE_OT_qmyi_RemoveAllSimulationData))
