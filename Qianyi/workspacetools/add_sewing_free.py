"""The free-sewing tool: draw a half on one pattern, then a half on the other."""

from bpy.types import WorkSpaceTool

from .. import global_data
from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_generic
from ..model import sewing_geometry as sewing
from ..model.qianyi_data import ensure_edit_mode
from ..operators._2d_add_sewing_free import (armed_half, half_pattern, place_under,
                                             second_half_target, set_preview,
                                             snapped_place, SUBMODE)
from ..utilities.console import console
from ..utilities.node_tree import get_active_node_tree


class NODE_T_qmyi_add_sewing_free(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.AddSewingFree.value
    bl_label = "draw a sewing"
    bl_icon = "ops.curve.draw"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_generic,
                 (
                     Operators.SewingAddFree2D,
                     {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
                     {"properties": None},
                 ),
                 (
                     Operators.SewingAddFree2D,
                     {"type": "ESC", "value": "PRESS"},
                     {"properties": [("cancel", True)]},
                 ),
                 )

    @staticmethod
    def draw_cursor(context, tool, xy):
        """Draw what the tool is holding, and what a press would take.

        The first half stays on screen while the second is drawn, with the place
        that would match its length marked, so the seam being drawn can be read
        before the button goes down.
        """
        project = get_active_node_tree(context)
        if not project:
            return
        if ensure_edit_mode(context, "SEWING", SUBMODE):
            console.info('edit_mode = SEWING / ADD_SEWING_FREE')
        manager = global_data.temp_draw_manager
        region = context.region
        if manager is None or region is None:
            return
        if manager.preview_locked:
            # A drag draws its own preview.
            return
        region_co = (xy[0] - region.x, xy[1] - region.y)
        manager.clear_tool_preview()
        first = armed_half(project)
        place = place_under(context, project, region_co)
        if place is None:
            if first is not None:
                draw_waiting(context, project, first, None)
            context.area.tag_redraw()
            return
        pattern, distance, point = place
        snapped = snapped_place(context, project, pattern, region_co)
        if snapped is not None:
            distance, _kind = snapped
            _edge, _pos, point = sewing.outline_place(pattern, distance)
        # With a half waiting, the preview is the second half this press would
        # draw: the place it takes, and the place that matches the first.
        travel = 0.0
        equal = second_half_target(context, project, pattern, distance, travel, first,
                                   region_co)
        if equal is None:
            set_preview(context, project, pattern, distance, point, travel, first)
        else:
            set_preview(context, project, pattern, distance, point,
                        equal[0] - distance, first, equal)
        context.area.tag_redraw()


def draw_waiting(context, project, first, pointer) -> None:
    """Show the first half on its own pattern while nothing is under the pointer."""
    pattern = half_pattern(project, first)
    manager = global_data.temp_draw_manager
    if pattern is None or manager is None:
        return
    try:
        run = sewing.run_from(pattern, float(first["start"]), float(first["travel"]))
    except ValueError:
        return
    manager.set_tool_polyline(pattern.view_points(run["polyline"]))
    manager.set_tool_points([(pattern, run["polyline"][0], "pivot"),
                             (pattern, run["end_point"], "target")])
