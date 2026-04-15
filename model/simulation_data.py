import bpy
from bpy.props import IntProperty, BoolProperty, PointerProperty, IntVectorProperty, EnumProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory
import atexit

from utilities.console import console_print, console
from ..simulation.simulation_manager import simulation_manager
from ..simulation.frame_timer import frame_changed_post


class SimulationProps(PropertyGroup):
    enable_simulation: BoolProperty(
        name="enable simulation",
        description="enable simulation",
        default=False,
        options={"SKIP_SAVE"},
        update=lambda _self, context: _self._on_global_simulation_toggle(context)
    )

    def _on_global_simulation_toggle(self, context):
        if self.enable_simulation:
            simulation_manager.start_simulation()
        else:
            simulation_manager.stop_simulation()


classes = (
    SimulationProps,
)

def cleanup_physics_engine(scene):
    import Qianyi_DP as qydp
    console.info("qydp.simulation_reset")
    qydp.simulator.on_exit()



def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    atexit.register(cleanup_physics_engine)
    bpy.app.handlers.frame_change_post.append(frame_changed_post)
    # bpy.app.handlers.render_pre.append(render_pre)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    atexit.unregister(cleanup_physics_engine) # TODO ?
    if frame_changed_post in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(frame_changed_post)

    # if render_pre in bpy.app.handlers.render_pre:
    #     bpy.app.handlers.render_pre.remove(render_pre)
