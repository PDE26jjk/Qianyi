import bpy
from bpy.app.handlers import persistent

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

_register_modules, _unregister_modules = module_register_factory(__package__, core_modules)


@persistent
def refresh_identities_on_load(_dummy=None):
    """Commit the session identities right after a file is loaded.

    The temp-data cache assigns ``global_idx`` and ``global_uuid`` lazily, and
    Blender refuses that write inside a panel draw or an operator poll. Doing it
    at the first legal moment after the file is open keeps the panels from
    attempting it, which is what crashed a session that drew before anything
    else had touched the project.
    """
    from .model.model_data import refresh_all_uuids

    refresh_all_uuids()
    for tree in bpy.data.node_groups:
        if tree.bl_idname != "QianyiNodeTree":
            continue
        # Only objects that already carry an identity are touched: a
        # ``global_uuid`` of -1 is data that should not exist, and it is left
        # alone rather than handed one here.
        if tree.global_uuid != -1:
            tree.get_temp_data()
        for pattern in tree.patterns:
            if pattern.global_uuid != -1:
                pattern.get_temp_data()


def register_full():
    if bpy.app.background:
        # A background session has no viewport, and Blender refuses to create
        # GPU shaders in it ("GPU functions for drawing are not available in
        # background mode"). Keep every renderer construction off the data path
        # so a script can load a scene and capture it headless.
        global_data.renderers_enabled = False
    _register_modules()
    if refresh_identities_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(refresh_identities_on_load)


def unregister_full():
    if refresh_identities_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(refresh_identities_on_load)
    _unregister_modules()
