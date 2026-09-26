import bpy
import numpy as np
from bpy.types import WorkSpaceTool

from ..utilities.console import console
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree
from ..keymaps import tool_generic
from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..model.qianyi_data import ensure_edit_mode


class NODE_T_qmyi_add_vertex(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.AddVertex.value
    bl_label = "add_vertex"
    # bl_operator = Operators.AddVertex2D
    bl_icon = "ops.paint.eyedropper_add"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_generic,
                 (
                     Operators.AddVertex2D,
                     {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
                     {"properties": None},
                 ),
                 )

    # def draw_settings(context, layout, tool):
    #     console.info('context' ,context)
    #
    def draw_cursor(context, tool, xy):
        # console.info('co = ', co)
        node_tree = get_active_node_tree(context)
        if not node_tree:
            return
        # Picking the tool puts the editor into the mode this tool works in, so
        # there is no "the tool does nothing until you change the mode" step.
        if ensure_edit_mode(context, "EDGE", "ADD_VERTEX"):
            console.info('edit_mode = EDGE / ADD_VERTEX')
        # The finder is what the tool reads and what the preview point is drawn
        # from, so it is kept current on every frame rather than when the mode
        # changes: an undo, a reload or another tool's edit leaves the snapshot
        # describing geometry that is no longer there, and a stale or dropped
        # snapshot is exactly what makes this tool look dead.
        if not node_tree.edge_finder_is_current():
            node_tree.update_edge_finder()
        region = context.region
        if not region:
            return
        region_co = (xy[0] - region.x, xy[1] - region.y)

        co = region2view_coord(context, region_co)
        node_tree.find_nearest_point_on_edge(co)
        # pattern, edge, add_point_pos, t = node_tree.get_nearest_point_data()
        # console.warning("t:", t)
        context.area.tag_redraw()
