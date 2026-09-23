"""Snapping a click on the pattern to a vertex of the panel."""

from __future__ import annotations

import numpy as np

from .node_tree import get_active_node_tree

# How close the pointer has to be to a vertex, in pixels on screen, for a click
# to land on it. Blender's own tools use the same kind of threshold, and
# measuring it on screen keeps it independent of the panel's scale and the zoom.
SNAP_PIXELS = 12.0


def vertex_near_cursor(context, pattern, cursor):
    """The outline vertex of `pattern` within the snap threshold of the cursor.

    `cursor` is a position in the region, the space the preselection gizmo and
    the tools already report. Returns ``(index, pixels)``, or None when no
    vertex is close enough.
    """
    region = getattr(context, "region", None)
    if region is None or cursor is None:
        return None
    pointer = np.asarray(cursor, dtype=np.float64)
    best = None
    for index, vertex in enumerate(pattern.vertices):  # loop: one vertex per check
        view = pattern.pattern_to_view_pos(vertex.co)
        pixel = region.view2d.view_to_region(float(view[0]), float(view[1]),
                                             clip=False)
        distance = float(np.hypot(pixel[0] - pointer[0], pixel[1] - pointer[1]))
        if best is None or distance < best[1]:
            best = (index, distance)
    if best is None or best[1] > SNAP_PIXELS:
        return None
    return best


def snapped_point(context, pattern, point, cursor):
    """A point on the outline, pulled onto a nearby vertex of the panel.

    Returns ``(point, index)``, where `index` is the vertex it snapped to or
    None when the point itself was used.
    """
    near = vertex_near_cursor(context, pattern, cursor)
    if near is None:
        return np.asarray(point, dtype=np.float64), None
    vertex = pattern.vertices[near[0]]
    return np.asarray(vertex.co, dtype=np.float64), near[0]


def hover_vertex(context, cursor):
    """The outline vertex under the pointer, in the panel that owns it.

    Returns ``(pattern, vertex)``, or ``(None, None)`` when the pointer is not
    on a vertex of any panel's outline.
    """
    project = get_active_node_tree(context)
    if project is None:
        return None, None
    best = None
    for pattern in project.patterns:  # loop: one panel's vertices per search
        near = vertex_near_cursor(context, pattern, cursor)
        if near is not None and (best is None or near[1] < best[1]):
            best = (near[0], near[1], pattern)
    if best is None:
        return None, None
    return best[2], best[2].vertices[best[0]]
