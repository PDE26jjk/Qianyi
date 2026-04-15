import bpy
import numpy as np
from bpy.types import WorkSpaceTool

from utilities.console import console
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree
from ..keymaps import tool_generic
from ..declarations import GizmoGroups, Operators, WorkSpaceTools


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
        if context.scene.qmyi.edit_sub_mode != "ADD_VERTEX":
            context.scene.qmyi.edit_sub_mode = "ADD_VERTEX"
            console.info('edit_sub_mode = ADD_VERTEX')
            node_tree.update_edge_finder()
        region = context.region
        if not region:
            return
        region_co = (xy[0] - region.x, xy[1] - region.y)

        co = region2view_coord(context, region_co)
        node_tree.find_nearest_point_on_edge(co)
        context.area.tag_redraw()
        # console.warning("query_point  ", co)
