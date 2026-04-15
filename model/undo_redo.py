from bpy.app.handlers import persistent
import bpy

from utilities.console import console_print
from ..utilities.node_tree import redraw_node_editors
from .. import global_data


@persistent
def on_undo_redo(dummy1, dummy2=None):  # TODO incremental invalid in depsgraph_update
    """当撤销或重做发生时，之前的内存指针全部失效，必须清空缓存"""
    for model in global_data.uuid2obj.values():
        if model.global_uuid != -1:
            model.clear_temp_data()
    global_data.uuid2obj.clear()
    global_data.temp_data.clear()
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
def after_undo_redo(dummy1, dummy2=None):
    redraw_node_editors()


def register():
    # undo_pre 在撤销前触发，undo_post 在撤销后触发
    # 建议两个都挂上，或者至少挂 post
    bpy.app.handlers.undo_pre.append(on_undo_redo)
    bpy.app.handlers.redo_pre.append(on_undo_redo)
    bpy.app.handlers.undo_post.append(after_undo_redo)
    bpy.app.handlers.redo_post.append(after_undo_redo)


def unregister():
    bpy.app.handlers.undo_pre.remove(on_undo_redo)
    bpy.app.handlers.redo_pre.remove(on_undo_redo)
    bpy.app.handlers.undo_post.remove(after_undo_redo)
    bpy.app.handlers.redo_post.remove(after_undo_redo)
