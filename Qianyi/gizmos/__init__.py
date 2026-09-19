import bpy
from .. import global_data
from .temp_draw_manager import TempDrawManager
from . import view3d_overlay

from .preselection import (
    NODE_GGT_qmyi_preselection,
    NODE_GT_qmyi_preselection,
)

classes = (
    NODE_GGT_qmyi_preselection,
    NODE_GT_qmyi_preselection,
)


def register():
    if global_data.temp_draw_manager is None:
        global_data.temp_draw_manager = TempDrawManager()
    for cls in classes:
        bpy.utils.register_class(cls)
    view3d_overlay.register()


def unregister():
    view3d_overlay.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
