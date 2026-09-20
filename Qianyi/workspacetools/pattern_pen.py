import bpy
from bpy.types import WorkSpaceTool

from ..keymaps import tool_generic
from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..model.qianyi_data import ensure_edit_mode


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

    def draw_cursor(context, tool, xy):
        # Picking the tool puts the editor into the mode this tool works in, so
        # the first click draws a panel instead of doing nothing.
        ensure_edit_mode(context, "PATTERN")
