import bpy

from . import global_data
from .utilities.register import module_register_factory

core_modules = [
    "preferences",
    "model",
    "operators",
    "gizmos",
    "ui",
    "draw_editor",
    "debug_draw_3d",
    "workspacetools",
    "vr",
    "m17n",
    "selection_sync",
    # Last: the script surface imports the model and the simulation manager.
    "qyapi"
]

_register_modules, unregister_full = module_register_factory(__package__, core_modules)


def register_full():
    if bpy.app.background:
        # A background session has no viewport, and Blender refuses to create
        # GPU shaders in it ("GPU functions for drawing are not available in
        # background mode"). Keep every renderer construction off the data path
        # so a script can load a scene and capture it headless.
        global_data.renderers_enabled = False
    _register_modules()
