import bpy
import numpy as np
from bpy.types import WorkSpaceTool

from ..utilities.console import console
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree
from ..keymaps import tool_generic
from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..model.qianyi_data import ensure_edit_mode


class NODE_T_qmyi_add_sewing1(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.AddSewing1.value
    bl_label = "add_sewing1"
    # bl_operator = Operators.AddVertex2D
    bl_icon = "ops.mesh.primitive_grid_add_gizmo"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (
                 (
                     Operators.SewingAdd1to12D,
                     {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
                     {"properties": [('mode', 'SELECT_EDGE')]},
                 ),
                 (
                     Operators.SewingAdd1to12D,
                     {"type": "ESC", "value": "PRESS", "any": True},
                     {"properties": [('mode', 'CANCEL')]},
                 ),
                 )

    # def draw_settings(context, layout, tool):
    #     console.info('context' ,context)
    #
    def draw_cursor(context, tool, xy):
        # console.info('co = ', co)
        project = get_active_node_tree(context)
        if not project:
            return
        # Picking the tool puts the editor into the mode this tool works in.
        if ensure_edit_mode(context, "SEWING", "ADD_SEWING1"):
            console.info('edit_mode = SEWING / ADD_SEWING1')
            project.selected_sewing_edge1 = None
            context.area.tag_redraw()
