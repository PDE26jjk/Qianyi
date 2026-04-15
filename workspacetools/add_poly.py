import bpy
from bpy.types import WorkSpaceTool

from ..keymaps import tool_generic
from ..declarations import GizmoGroups, Operators, WorkSpaceTools


class NODE_T_qmyi_add_poly(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.AddPoly.value
    bl_label = "Offset Entities"
    bl_operator = Operators.AddPoly
    bl_icon = "ops.gpencil.primitive_arc"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_generic,
                 (
                     Operators.AddPoly,
                     {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
                     {"properties": None},
                 ),
                 )

    def draw_settings(context, layout, tool):
        # 工具设置
        layout.label(text="连接设置:")
        layout.label(text="?????")
