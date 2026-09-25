import bpy
from bpy.props import IntProperty, BoolProperty, PointerProperty, IntVectorProperty, EnumProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory
import atexit

from ..utilities.console import console_print, console
from ..utilities.report import report_error
from ..simulation.simulation_manager import simulation_manager


# from ..simulation.frame_timer import frame_changed_post

# Set while the toggle is being put back after a refused start, so writing the
# property from inside its own update callback does not recurse.
_reset_in_progress = False


class SimulationProps(PropertyGroup):
    enable_free_simulation: BoolProperty(
        name="enable free simulation",
        description="enable free simulation",
        default=False,
        options={"SKIP_SAVE"},
        update=lambda _self, context: _self._on_global_simulation_toggle(context)
    )

    def _on_global_simulation_toggle(self, context):
        global _reset_in_progress
        if _reset_in_progress:
            return
        # The pattern runs through the same entry points the script surface
        # exposes, so the mode a script reads cannot disagree with the code that
        # is actually running. Imported here: the surface loads after this
        # module, and importing it at module level would be a cycle.
        from ..qyapi import sim as qmyi_sim
        from ..qyapi.errors import QyapiError
        if self.enable_free_simulation:
            self.simulation_with_animation = False
            self.play_frame_cache = False
            try:
                qmyi_sim.start()
            except QyapiError as error:
                # The manager refused (an invalid pattern); put the switch back
                # so the UI does not claim a run that never started.
                report_error(str(error), error.details)
                _reset_in_progress = True
                try:
                    self.enable_free_simulation = False
                finally:
                    _reset_in_progress = False
        else:
            qmyi_sim.stop()

    next_n_frames: IntProperty(
        name="next_n_frames",
        description="next_n_frames debug",
        default=1,
        options={"SKIP_SAVE"},
    )
    to_n_frames: IntProperty(
        name="to_n_frames",
        description="to_n_frames debug",
        default=1,
        options={"SKIP_SAVE"},
    )

    simulation_with_animation: BoolProperty(
        name="simulation with animation",
        description="simulation_with_animation",
        default=False,
        options={"SKIP_SAVE"},
        update=lambda _self, context: _self._on_simulation_with_animation_toggle(context)
    )

    def _on_simulation_with_animation_toggle(self, context):
        global _reset_in_progress
        if self.simulation_with_animation:
            if _reset_in_progress:
                return
            self.enable_free_simulation = False
            self.play_frame_cache = False
            if not simulation_manager.start_simulation_with_animation():
                _reset_in_progress = True
                try:
                    self.simulation_with_animation = False
                finally:
                    _reset_in_progress = False
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
