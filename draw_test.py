import logging

import bpy
import gpu
from bpy.types import Context, Operator
from bpy.utils import register_class, unregister_class

from . import global_data
from .declarations import Operators, Panels

logger = logging.getLogger(__name__)

draw_handle = None


def draw_callback():
    """绘制回调函数"""

    if not global_data.temp_draw_manager:
        return
    context = bpy.context

    space = context.space_data

    if space and space.node_tree :
        # context.workspace.status_text_set(f"{space.node_tree.bl_idname}")
        if space.node_tree.bl_idname != Panels.QianyiNodeTree:
            return
    else:
        return

    global_data.temp_draw_manager.draw(context)
    #     return True
    # 检查是否有点集合
    # if not hasattr(context.scene, "point_collection"):
    #     return
    #
    # collection = context.scene.point_collection
    # # 绘制所有点
    # # context.workspace.status_text_set(f"${collection}")
    # for point in collection.points:
    #     point.update()
    #     # if point.is_dirty:
    #     #     point.update()
    #     point.draw(context)
    #     context.workspace.status_text_set(f"${point}")



class DrawPointsOperator(Operator):
    bl_idname = "view3d.register_draw_cb"
    bl_label = "Register Draw Callback"

    def execute(self, context: Context):
        global draw_handle
        draw_handle = bpy.types.SpaceNodeEditor.draw_handler_add(
            draw_callback, (), "WINDOW", "POST_VIEW"
        )

        return {"FINISHED"}


def end():
    global draw_handle
    if draw_handle:
        bpy.types.SpaceNodeEditor.draw_handler_remove(draw_handle, 'WINDOW')
        draw_handle = None

def startup_cb(*args):
    bpy.ops.view3d.register_draw_cb()
    return None


def register():
    register_class(DrawPointsOperator)
    bpy.app.timers.register(startup_cb, first_interval=1, persistent=True)


def unregister():
    end()
    unregister_class(DrawPointsOperator)
