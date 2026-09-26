import bpy
import numpy as np
from bpy.types import WorkSpaceTool

from ..utilities.console import console
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree
from ..keymaps import tool_generic
from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..model.qianyi_data import ensure_edit_mode


class NODE_T_qmyi_add_spline_point(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.AddSplinePoint.value
    bl_label = "add_spline_point"
    bl_icon = "brush.particle.add"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_generic,
                 (
                     Operators.AddSplinePoint2D,
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
        # Picking the tool puts the editor into the mode this tool works in.
        if ensure_edit_mode(context, "EDGE", "ADD_SPLINE_POINT"):
            console.info('edit_mode = EDGE / ADD_SPLINE_POINT')
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
