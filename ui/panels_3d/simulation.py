
from ... import declarations
from . import VIEW_3D_PT_qmyi_base
from ...utilities.node_tree import get_active_node_tree


class QY_PT_simulation(VIEW_3D_PT_qmyi_base):
    bl_category = "Qianyi"
    bl_label = "Simulation"
    bl_idname = declarations.Panels.Simulation

    def draw(self, context):
        layout = self.layout
        qmyi = context.scene.qmyi
        scene_props = qmyi.simulation

        layout.prop(scene_props, "enable_free_simulation", toggle=True)
        layout.label(text="frame cache: ")
        layout.prop(scene_props, "simulation_with_animation", toggle=True)
        layout.prop(scene_props, "record_frame_cache")
        layout.prop(scene_props, "play_frame_cache", toggle=True)
