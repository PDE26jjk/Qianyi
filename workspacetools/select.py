import bpy
from bpy.types import WorkSpaceTool

from utilities.console import console
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

    def draw_settings(context, layout, tool):
        props = tool.operator_properties(Operators.Select)
        layout.prop(props, "mode", text="", expand=True, icon_only=True)

    def draw_cursor(context, tool, xy):
        if context.scene.qmyi.edit_sub_mode != "EDGE_VERTEX":
            context.scene.qmyi.edit_sub_mode = "EDGE_VERTEX"
            console.info('edit_sub_mode = EDGE_VERTEX')
            context.area.tag_redraw()