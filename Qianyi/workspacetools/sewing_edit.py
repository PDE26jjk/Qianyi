"""The sewing-edit tool: press a half of a seam, then move it."""

from bpy.types import WorkSpaceTool

from .. import global_data
from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_generic
from ..model import sewing_geometry as sewing
from ..model.qianyi_data import ensure_edit_mode
from ..operators._2d_sewing_edit import SUBMODE, picked_target
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
        over a half, and the one the pointer is on is drawn as the point under
        it: that is what a press takes. A press between the two takes the half.
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
        target = picked_target(manager)
        if target is None:
            context.area.tag_redraw()
            return
        side, grab = target
        pattern = side.pattern
        if pattern is None:
            context.area.tag_redraw()
            return
        try:
            run, start, travel = sewing.side_run(side)
        except ValueError:
            context.area.tag_redraw()
            return
        _edge, _pos, first = sewing.run_place(run, start)
        _edge, _pos, second = sewing.run_place(run, start + travel)
        manager.set_tool_polyline(pattern.view_points(sewing.run_from(
            run, start, travel)["polyline"]))
        # The end a press would take is drawn as the point under the pointer; the
        # other end shows where the half reaches to, and a press anywhere on the
        # half between them slides both.
        if grab == "start":
            kinds = ("hover", "target")
        elif grab == "end":
            kinds = ("target", "hover")
        else:
            kinds = ("pivot", "target")
        manager.set_tool_points([(pattern, first, kinds[0]), (pattern, second, kinds[1])])
        context.area.tag_redraw()
