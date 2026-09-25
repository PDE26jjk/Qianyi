"""The curve-drag tool: pick it, then press an edge and drag it into shape."""

from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_generic
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.console import console
from ..utilities.node_tree import get_active_node_tree


class NODE_T_qmyi_curve_fit(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.CurveFit.value
    bl_label = "drag a curve"
    bl_icon = "ops.curve.draw"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_generic,
                 (
                     Operators.CurveFit2D,
                     {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
                     {"properties": None},
                 ),
                 )

    @staticmethod
    def draw_cursor(context, tool, xy):
        """The tool works on the edge the hover highlight already draws.

        There is nothing to preview under the pointer - what the drag would do
        depends on where the press lands and how far it is then moved - so this
        only puts the editor into the mode the edit belongs to.
        """
        if not get_active_node_tree(context):
            return
        if ensure_edit_mode(context, "EDGE", "EDGE_VERTEX"):
            console.info('edit_mode = EDGE / EDGE_VERTEX')
