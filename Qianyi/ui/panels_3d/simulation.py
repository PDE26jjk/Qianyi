
from ... import declarations
from . import VIEW_3D_PT_qmyi_base
from ...utilities.node_tree import get_active_node_tree, get_all_node_tree
import bpy

class QY_PT_simulation(VIEW_3D_PT_qmyi_base):
    bl_category = "Qianyi"
    bl_label = "Simulation"
    bl_idname = declarations.Panels.Simulation

    def draw(self, context):
        layout = self.layout
        qmyi = context.scene.qmyi
        scene_props = qmyi.simulation

        # Only the cached state is read here, so drawing never runs a test.
        invalid = [pattern.name or "(unnamed pattern)"
                   for project in get_all_node_tree()
                   for pattern in project.patterns if pattern.is_invalid]
        if invalid:
            box = layout.box()
            box.label(text=f"{len(invalid)} pattern outline(s) intersect", icon="ERROR")
            for name in invalid:
                box.label(text=name)
            box.label(text="fix them before starting a simulation")

        layout.prop(scene_props, "enable_free_simulation", toggle=True)
        row = layout.row()
        row.prop(scene_props, "next_n_frames")
        row.operator("qmyi.simulation_debug_next_n_frames")
        row = layout.row()
        row.prop(scene_props, "to_n_frames")
        row.operator("qmyi.simulation_debug_to_n_frames")
        layout.label(text="frame cache: ")
        layout.prop(scene_props, "simulation_with_animation", toggle=True)
        layout.prop(scene_props, "record_frame_cache")
        layout.prop(scene_props, "play_frame_cache", toggle=True)

from ...simulation.simulation_manager import simulation_manager
class SimulationNextNframesOperator(bpy.types.Operator):
    bl_idname = "qmyi.simulation_debug_next_n_frames"
    bl_label = "update"

    def execute(self, context):
        qmyi = context.scene.qmyi
        scene_props = qmyi.simulation
        n = scene_props.next_n_frames
        simulation_manager.update_N_frames_debug(n)
        return {'FINISHED'}

class SimulationToNframesOperator(bpy.types.Operator):
    bl_idname = "qmyi.simulation_debug_to_n_frames"
    bl_label = "update"

    def execute(self, context):
        qmyi = context.scene.qmyi
        scene_props = qmyi.simulation
        n = scene_props.to_n_frames
        simulation_manager.update_to_frames_debug(n)
        return {'FINISHED'}
