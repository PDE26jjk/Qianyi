"""The corner tool: pick it, then click the corner of an outline to treat it."""

from bpy.types import WorkSpaceTool

from .. import global_data
from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_generic
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.console import console
from ..utilities.node_tree import get_active_node_tree
from ..utilities.snap import hover_vertex


class NODE_T_qmyi_corner(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.Corner.value
    bl_label = "corner"
    bl_icon = "ops.mesh.bevel"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_generic,
                 (
                     Operators.Corner2D,
                     {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
                     {"properties": [("from_tool", True)]},
                 ),
                 )

    @staticmethod
    def draw_settings(context, layout, tool):
        """The tool's own settings: which corner treatment a click applies."""
        qmyi = getattr(context.scene, "qmyi", None)
        if qmyi is not None:
            layout.prop(qmyi, "corner_mode", text="")

    @staticmethod
    def draw_cursor(context, tool, xy):
        """Show the vertex a click would treat, under the pointer."""
        node_tree = get_active_node_tree(context)
        if not node_tree:
            return
        # Picking the tool puts the editor into the mode this tool works in, so
        # there is no "the tool does nothing until you change the mode" step.
        if ensure_edit_mode(context, "EDGE", "EDGE_VERTEX"):
            console.info('edit_mode = EDGE / EDGE_VERTEX')
        manager = global_data.temp_draw_manager
        region = context.region
        if manager is None or region is None:
            return
        if manager.preview_locked:
            # A running gesture draws the whole preview itself.
            return
        region_co = (xy[0] - region.x, xy[1] - region.y)
        pattern, vertex = hover_vertex(context, region_co)
        if vertex is None:
            manager.clear_tool_preview()
        else:
            manager.set_tool_point(pattern, vertex.co)
        context.area.tag_redraw()
