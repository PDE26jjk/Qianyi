import bpy
from bpy.props import IntProperty, BoolProperty, PointerProperty, IntVectorProperty, EnumProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory
import atexit

from utilities.console import console_print
from ..simulation.simulation_manager import simulation_manager


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

def cleanup_physics_engine():
    import Qianyi_DP as qydp
    # console_print("qydp.simulation_reset")
    qydp.simulation_reset()

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    atexit.register(cleanup_physics_engine)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    atexit.unregister(cleanup_physics_engine)
