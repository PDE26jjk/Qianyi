import bpy
from bpy.types import WorkSpaceTool

from ..keymaps import tool_generic
from ..declarations import GizmoGroups, Operators, WorkSpaceTools


class NODE_T_qmyi_pattern_pen(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.PatternPen.value
    bl_label = "pattern pen"
    bl_icon = "ops.curve.pen"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_generic,
                 (
                     Operators.PatternPen,
                     {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
                     {"properties": None},
                 ),
                 )

    # def draw_settings(context, layout, tool):
    #     # 工具设置
    #     layout.label(text="连接设置:")
    #     layout.label(text="?????")
