"""The fan tool: pick it, click the pivot, click the target, click to open."""

import numpy as np
from bpy.types import WorkSpaceTool

from .. import global_data
from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_generic
from ..model import pattern_geometry as geometry
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.console import console
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree
from ..utilities.snap import snapped_point, vertex_near_cursor


class NODE_T_qmyi_fan(WorkSpaceTool):
    bl_space_type = "NODE_EDITOR"
    bl_context_mode = None
    bl_idname = WorkSpaceTools.Fan.value
    bl_label = "pivot fan"
    bl_icon = "ops.transform.rotate"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = (*tool_generic,
                 (
                     Operators.Fan2D,
                     {"type": "LEFTMOUSE", "value": "PRESS", "any": True},
                     {"properties": None},
                 ),
                 (
                     Operators.Fan2D,
                     {"type": "ESC", "value": "PRESS"},
                     {"properties": [("cancel", True)]},
                 ),
                 )

    @staticmethod
    def draw_cursor(context, tool, xy):
        """Draw the gesture so far: the points taken, the radius, the fan.

        Every move redraws it from the project's own record of the gesture, so
        the preview is right while the two points are being chosen. The angle is
        a modal drag and draws its own preview, which is why this stops while
        one is running.
        """
        node_tree = get_active_node_tree(context)
        if not node_tree:
            return
        if ensure_edit_mode(context, "EDGE", "EDGE_VERTEX"):
            console.info('edit_mode = EDGE / EDGE_VERTEX')
            node_tree.update_edge_finder()
        manager = global_data.temp_draw_manager
        region = context.region
        if manager is None or region is None:
            return
        if manager.preview_locked:
            # A running gesture draws the whole preview itself.
            return
        region_co = (xy[0] - region.x, xy[1] - region.y)
        manager.clear_tool_preview()
        pattern, point, vertex = hover_point(context, node_tree, region_co)
        if pattern is None:
            context.area.tag_redraw()
            return
        points = []
        pivot = node_tree.fan_pivot
        target = node_tree.fan_target
        if pivot is not None:
            pattern = pattern_named(node_tree, pivot[0])
            if pattern is None:
                node_tree.fan_pivot = None
                context.area.tag_redraw()
                return
            points.append((pattern, pivot[1], "pivot"))
        if target is not None:
            pattern = pattern_named(node_tree, target[0])
            if pattern is not None:
                points.append((pattern, target[1], "target"))
        if vertex is not None:
            # A vertex under the pointer is what a click will take, so show
            # that instead of the raw position on the edge.
            point, _vertex = vertex.co, vertex
        if pivot is None:
            points.append((pattern, point, "hover"))
            manager.set_tool_points(points)
            context.area.tag_redraw()
            return
        if target is None:
            points.append((pattern, point, "hover"))
            manager.set_tool_points(points)
            draw_arm(manager, pattern, pivot[1], point)
            context.area.tag_redraw()
            return
        # Both points are known: the angle is a modal drag from here on, and it
        # draws the fan itself.
        manager.set_tool_points(points)
        context.area.tag_redraw()


def pattern_named(project, name):
    for pattern in project.patterns:  # loop: one pattern per name check
        if pattern.name == name:
            return pattern
    return None


def hover_point(context, project, cursor):
    """The point a click would take: a vertex if there is one, else the edge."""
    pattern, vertex = _vertex_under(context, project, cursor)
    if vertex is not None:
        return pattern, np.asarray(vertex.co, dtype=np.float64), vertex
    project.find_nearest_point_on_edge(region2view_coord(context, cursor))
    if project.nearest_point is None or project.nearest_pattern is None:
        return None, None, None
    pattern = project.patterns[project.nearest_pattern]
    return pattern, np.asarray(project.nearest_point, dtype=np.float64), None


def _vertex_under(context, project, cursor):
    best = None
    for pattern in project.patterns:  # loop: one pattern's vertices per search
        near = vertex_near_cursor(context, pattern, cursor)
        if near is not None and (best is None or near[1] < best[1]):
            best = (near[0], near[1], pattern)
    if best is None:
        return None, None
    return best[2], best[2].vertices[best[0]]


def draw_arm(manager, pattern, start, end, head=0.08) -> None:
    """One radius, drawn with an arrowhead where it ends."""
    first = pattern.pattern_to_view_pos(start)
    second = pattern.pattern_to_view_pos(end)
    manager.add_tool_line(first, second)
    length = float(np.hypot(second[0] - first[0], second[1] - first[1]))
    if length <= 1e-6:
        return
    direction = np.array(((second[0] - first[0]) / length,
                          (second[1] - first[1]) / length))
    normal = np.array((-direction[1], direction[0]))
    size = max(length * head, 1e-6)
    tip = np.asarray(second, dtype=np.float64)
    for side in (1.0, -1.0):  # loop: the two barbs of the arrowhead
        barb = tip - direction * size + normal * size * 0.45 * side
        manager.add_tool_line(tuple(tip), tuple(barb))
