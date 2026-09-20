import bpy
from bpy.types import WorkSpaceTool

from ..keymaps import tool_generic
from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..model.qianyi_data import ensure_edit_mode


class NODE_T_qmyi_internal_line_pen(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.InternalLinePen.value
    bl_label = "internal line pen"
    bl_icon = "ops.gpencil.draw.poly"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_generic,
                 (
                     Operators.InternalLinePen,
                     {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
                     {"properties": None},
                 ),
                 )

    def draw_cursor(context, tool, xy):
        # Picking the tool puts the editor into the mode this tool works in.
        ensure_edit_mode(context, "PATTERN", "INTERNAL_POINT")

