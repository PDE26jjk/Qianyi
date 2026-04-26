from bpy.app.handlers import persistent
import bpy

from utilities.console import console_print, console
from ..utilities.node_tree import get_active_node_tree, redraw_node_editors
from .. import global_data


@persistent
def on_undo_redo(dummy1, dummy2=None):  # TODO incremental invalid in depsgraph_update
    """当撤销或重做发生时，之前的内存指针全部失效，必须清空缓存"""
    # try:
    #     for model in global_data.uuid2obj.values():  # still easy to crash, try to fix it.
    #         if model and model.global_uuid != -1:
    #             model.clear_temp_data()
    # except:
    #     pass
    global_data.uuid2obj.clear()
    global_data.temp_data.clear()
    # console.warning("Undo redo clear")
    # console_print(global_data.temp_data)
    # for ng in bpy.data.node_groups:
    #     if hasattr(ng, "patterns"):
    #         for p in ng.patterns:
    #             if hasattr(p, "need_render_update"):
    #                 p.need_render_update = True
    #                 p.initialized = False
    # else:
    #     console_print('has no need_render_update')
    # console_print("on_undo_redo")
    # console_print(global_data.uuid2obj)
    # redraw_node_editors()


@persistent
def after_undo_redo(scene, dummy2=None):
    project = get_active_node_tree(bpy.context)
    if project is not None:
        project.refresh_patterns()
    # console.info("Undo redo",global_data.uuid2obj.keys())
    if hasattr(scene, "qmyi"):
        scene.qmyi.clear_temp_data()
    redraw_node_editors()


def register():
    bpy.app.handlers.undo_pre.append(on_undo_redo)
    bpy.app.handlers.redo_pre.append(on_undo_redo)
    bpy.app.handlers.undo_post.append(after_undo_redo)
    bpy.app.handlers.redo_post.append(after_undo_redo)


def unregister():
    bpy.app.handlers.undo_pre.remove(on_undo_redo)
    bpy.app.handlers.redo_pre.remove(on_undo_redo)
    bpy.app.handlers.undo_post.remove(after_undo_redo)
    bpy.app.handlers.redo_post.remove(after_undo_redo)
