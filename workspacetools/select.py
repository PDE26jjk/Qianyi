import bpy
from bpy.types import WorkSpaceTool

from ..keymaps import tool_select
from ..declarations import GizmoGroups, Operators, WorkSpaceTools


class NODE_T_qmyi_select(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.Select.value
    bl_label = ""
    bl_description = "Select Entities"
    bl_icon = "ops.generic.select"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_select,)

    @classmethod
    def draw_settings(cls, context, layout, tool):
        props = tool.operator_properties(Operators.Select)
        layout.prop(props, "mode", text="", expand=True, icon_only=True)
