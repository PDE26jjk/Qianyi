import bpy
from bpy.props import IntProperty, BoolProperty, PointerProperty, IntVectorProperty, EnumProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory
import atexit

from utilities.console import console_print, console
from ..simulation.simulation_manager import simulation_manager


# from ..simulation.frame_timer import frame_changed_post


class SimulationProps(PropertyGroup):
    enable_free_simulation: BoolProperty(
        name="enable free simulation",
        description="enable free simulation",
        default=False,
        options={"SKIP_SAVE"},
        update=lambda _self, context: _self._on_global_simulation_toggle(context)
    )

    def _on_global_simulation_toggle(self, context):
        if self.enable_free_simulation:
            self.simulation_with_animation = False
            self.play_frame_cache = False
            simulation_manager.start_simulation()
        else:
            simulation_manager.stop_simulation()

    simulation_with_animation: BoolProperty(
        name="simulation with animation",
        description="simulation_with_animation",
        default=False,
        options={"SKIP_SAVE"},
        update=lambda _self, context: _self._on_simulation_with_animation_toggle(context)
    )

    def _on_simulation_with_animation_toggle(self, context):
        if self.simulation_with_animation:
            self.enable_free_simulation = False
            self.play_frame_cache = False
            simulation_manager.start_simulation_with_animation()
        else:
            simulation_manager.stop_simulation_with_animation()

    record_frame_cache: BoolProperty(
        name="record frame cache",
        description="record frame cache",
        default=False,
    )
    play_frame_cache: BoolProperty(
        name="play frame cache",
        description="play frame cache",
        default=False,
        options={"SKIP_SAVE"},
        update=lambda _self, context: _self._on_play_frame_cache_toggle(context)
    )

    def _on_play_frame_cache_toggle(self, context):
        if self.play_frame_cache:
            self.simulation_with_animation = False
            self.enable_free_simulation = False
            simulation_manager.start_play_cache()
        else:
            simulation_manager.stop_play_cache()


classes = (
    SimulationProps,
)


# def cleanup_physics_engine(scene):
#     import Qianyi_DP as qydp
#     console.info("qydp.simulation_reset")
#     qydp.simulator.on_exit()
#

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # atexit.register(cleanup_physics_engine)
    # bpy.app.handlers.frame_change_post.append(frame_changed_post)
    # bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_post)
    # bpy.app.handlers.render_pre.append(render_pre)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    # atexit.unregister(cleanup_physics_engine)
    # if frame_changed_post in bpy.app.handlers.frame_change_post:
    #     bpy.app.handlers.frame_change_post.remove(frame_changed_post)
    # if depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
    #     bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_post)

    # if render_pre in bpy.app.handlers.render_pre:
    #     bpy.app.handlers.render_pre.remove(render_pre)
