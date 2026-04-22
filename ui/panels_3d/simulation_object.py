import bpy

from utilities.console import console
from ... import declarations
from . import VIEW_3D_PT_qmyi_base
from ...utilities.node_tree import get_active_node_tree, get_all_node_tree


class QY_PT_simulation_object(VIEW_3D_PT_qmyi_base):
    bl_category = "Qianyi"
    bl_label = "Simulation props"
    bl_idname = declarations.Panels.SimulationObject
    bl_category = "Qianyi"

    def draw(self, context):
        layout = self.layout
        obj = context.object
        if obj and obj.qmyi_simulation_props:
            props = obj.qmyi_simulation_props
            if props.is_pattern_mesh:
                try:
                    pattern = props.pattern
                    layout.label(text=f"pattern: {pattern.name}")
                    fabric = pattern.fabric
                    # assert fabric is not None
                    # console.print( pattern ,pattern.fabric_uuid)
                    layout.prop(props,'fabric_enum')
                    box = layout.box()
                    box.label(text=f"fabric: {fabric.name}")
                    box.prop(fabric, "thickness")
                    box.prop(fabric, "friction")
                    box.prop(fabric, "weight")
                    box.prop(fabric, "stretch")
                    box.prop(fabric, "shear")
                    box.prop(fabric, "bending")
                except Exception as e:
                    console.warning(f"{e}")
                    layout.operator("qmyi.simulation_refresh")
            else:
                layout.label(text=f"As Collider")
                layout.prop(props, "participate_in_simulation")
                layout.prop(props, "vertices_updated_every_frame")


class SimulationDataRefreshOperator(bpy.types.Operator):
    bl_idname = "qmyi.simulation_refresh"
    bl_label = "Refresh"

    def execute(self, context):
        qmyi = context.scene.qmyi
        scene_props = qmyi.simulation
        scene_props.enable_free_simulation = False
        projects = get_all_node_tree()
        for project in projects:
            project.get_default_fabric()
            for fabric in project.fabrics:
                fabric.get_temp_data()
            project.update_all(forced=True)
        return {'FINISHED'}
