"""The sewing-edit tool: press a half of a seam, then move it."""

from bpy.types import WorkSpaceTool

from .. import global_data
from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_generic
from ..model import sewing_geometry as sewing
from ..model.qianyi_data import ensure_edit_mode
from ..operators._2d_sewing_edit import SUBMODE, picked_side
from ..utilities.console import console
from ..utilities.node_tree import get_active_node_tree


class NODE_T_qmyi_sewing_edit(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.SewingEdit.value
    bl_label = "edit a sewing"
    bl_icon = "ops.transform.translate"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_generic,
                 (
                     Operators.SewingEdit2D,
                     {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
                     {"properties": None},
                 ),
                 )

    @staticmethod
    def draw_cursor(context, tool, xy):
        """Mark the ends of the half a press would take hold of.

        The ends are what a drag moves, so they are drawn while the pointer is
        over a half - together with the place that would make the half as long as
        the one it is sewn to, when the pointer is close to it.
        """
        project = get_active_node_tree(context)
        if not project:
            return
        if ensure_edit_mode(context, "SEWING", SUBMODE):
            console.info('edit_mode = SEWING / EDIT_SEWING')
        manager = global_data.temp_draw_manager
        region = context.region
        if manager is None or region is None:
            return
        if manager.preview_locked:
            # A drag draws its own preview.
            return
        manager.clear_tool_preview()
        side = picked_side(manager)
        pattern = side.pattern if side is not None else None
        if side is None or pattern is None:
            context.area.tag_redraw()
            return
        try:
            start, travel = sewing.side_places(pattern, side)
        except ValueError:
            context.area.tag_redraw()
            return
        _edge, _pos, first = sewing.outline_place(pattern, start)
        _edge, _pos, second = sewing.outline_place(pattern, start + travel)
        manager.set_tool_polyline(pattern.view_points(sewing.run_from(
            pattern, start, travel)["polyline"]))
        manager.set_tool_points([(pattern, first, "pivot"), (pattern, second, "target")])
        context.area.tag_redraw()
