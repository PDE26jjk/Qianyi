"""The many-to-many sewing tool: runs on the first side, return, runs on the second."""

from bpy.types import WorkSpaceTool

from .. import global_data
from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_generic
from ..model import sewing_geometry as sewing
from ..model.qianyi_data import ensure_edit_mode
from ..operators._2d_add_sewing_free import place_under, set_preview, snapped_place
from ..operators._2d_add_sewing_m2n import SUBMODE, held_sets
from ..utilities.console import console
from ..utilities.node_tree import get_active_node_tree


class NODE_T_qmyi_add_sewing_m2n(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.AddSewingMtoN.value
    bl_label = "draw a many-to-many sewing"
    bl_icon = "ops.curve.draw"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_generic,
                 (
                     Operators.SewingAddMtoN2D,
                     {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
                     {"properties": None},
                 ),
                 (
                     Operators.SewingAddMtoN2D,
                     {"type": "RET", "value": "PRESS"},
                     {"properties": [("finish", True)]},
                 ),
                 (
                     Operators.SewingAddMtoN2D,
                     {"type": "ESC", "value": "PRESS"},
                     {"properties": [("cancel", True)]},
                 ),
                 )

    @staticmethod
    def draw_cursor(context, tool, xy):
        """Draw what a press would take, and where the side being drawn ended.

        The runs already drawn for the side stay on screen with the last one's
        two ends marked, so the side being drawn can be read before the next run
        is added to it.
        """
        project = get_active_node_tree(context)
        if not project:
            return
        if ensure_edit_mode(context, "SEWING", SUBMODE):
            console.info('edit_mode = SEWING / ADD_SEWING_M2N')
        manager = global_data.temp_draw_manager
        region = context.region
        if manager is None or region is None:
            return
        if manager.preview_locked:
            # A drag draws its own preview.
            return
        region_co = (xy[0] - region.x, xy[1] - region.y)
        manager.clear_tool_preview()
        held = held_sets(project)
        waiting = None
        if held is not None and held["runs"][held["which"] - 1]:
            last = held["runs"][held["which"] - 1][-1]
            waiting = {"pattern": held["patterns"][held["which"] - 1],
                       "run": last["run"], "start": last["start"],
                       "travel": last["travel"]}
        place = place_under(context, project, region_co)
        if place is None:
            if waiting is not None:
                draw_waiting(context, project, waiting)
            context.area.tag_redraw()
            return
        pattern, run, distance, point = place
        snapped = snapped_place(context, project, pattern, run, region_co)
        if snapped is not None:
            distance, _kind = snapped
            _edge, _pos, point = sewing.run_place(run, distance)
        set_preview(context, project, pattern, run, distance, point, 0.0, waiting)
        context.area.tag_redraw()


def draw_waiting(context, project, waiting) -> None:
    """Show the last run drawn for the side being drawn."""
    pattern = global_data.get_obj_by_uuid(int(waiting["pattern"]), check_uuid=False)
    run = global_data.get_obj_by_uuid(int(waiting["run"]), check_uuid=False)
    manager = global_data.temp_draw_manager
    if pattern is None or run is None or manager is None:
        return
    try:
        walked = sewing.run_from(run, float(waiting["start"]), float(waiting["travel"]))
    except ValueError:
        return
    manager.set_tool_polyline(pattern.view_points(walked["polyline"]))
    manager.set_tool_points([(pattern, walked["polyline"][0], "pivot"),
                             (pattern, walked["end_point"], "target")])
