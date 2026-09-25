"""Keep the 3D selection and the pattern editor's selection in step.

Off by default; the header carries one toggle for it, the way the UV editor and
the outliner do. With it on:

* selecting a pattern's mesh in the 3D viewport selects that pattern in the pattern
  editor, and deselects the patterns that are no longer selected;
* selecting a pattern in the pattern editor (or a row of them) selects their
  meshes in the 3D viewport;
* clearing either side clears the other.

Exactly the patterns that are selected are mirrored, one for one: an instance copy
is a convenience for editing the same pattern twice, not a selection unit, so
selecting one member of an instance chain leaves the others alone.

Only pattern meshes take part: a collider or any other object is left exactly as
it was, and a pattern with no mesh yet has nothing to select in 3D.

The two sides are polled from one timer rather than hooked to a depsgraph
handler, because a pure selection change does not reliably run a handler and the
poll only reads the selected objects. What each side looked like after the last
apply is remembered on the scene's Qianyi settings, so a mirror cannot loop back
on itself, and turning the toggle on adopts the state that is already there
instead of changing it.
"""

from __future__ import annotations

import bpy

from .declarations import Panels
from .utilities.console import console
from .utilities.node_tree import get_active_node_tree

POLL_INTERVAL = 0.1

_KEY_3D = "selection_sync_3d"
_KEY_2D = "selection_sync_2d"
_KEY_BUSY = "selection_sync_busy"


def active_project(context=None, qmyi=None):
    """The project the pattern editor is showing, or the scene's active one.

    The timer runs whether or not a node editor is on screen, so the project has
    to be reachable from the scene as well: a session sitting in the 3D viewport
    still syncs its 2D selection through the project index.
    """
    context = context or bpy.context
    project = get_active_node_tree(context)
    if project is not None:
        return project
    if qmyi is None:
        scene = getattr(context, "scene", None)
        qmyi = getattr(scene, "qmyi", None)
    if qmyi is None:
        return None
    index = qmyi.active_project_index
    if 0 <= index < len(bpy.data.node_groups):
        tree = bpy.data.node_groups[index]
        if tree.bl_idname == Panels.QianyiNodeTree:
            return tree
    return None


def selected_3d_uuids(context) -> frozenset:
    """Every selected pattern mesh, as a set of pattern uuids."""
    uuids = set()
    for obj in context.selected_objects:
        props = getattr(obj, "qmyi_simulation_props", None)
        if obj.type != 'MESH' or props is None or not props.is_pattern_mesh:
            continue
        # The uuid comes straight off the mesh: a mesh whose pattern was removed
        # cannot be synced, and asking for the pattern object would raise.
        uuids.add(props.pattern_uuid)
    return frozenset(uuids)


def selected_2d_uuids(project) -> frozenset:
    """Every pattern selected in the pattern editor."""
    return frozenset(pattern.global_uuid for pattern in project.patterns
                     if pattern.is_selected)


def apply_to_patterns(project, uuids) -> int:
    """Select exactly these patterns in the pattern editor; returns how many."""
    # The operators read the uuid cache, so it has to be filled before it is
    # used - a session that just loaded a file has an empty identity map.
    project.refresh_collection_uuid(project.patterns)
    selected = 0
    for pattern in project.patterns:
        pattern.is_selected = pattern.global_uuid in uuids
        if pattern.is_selected:
            selected += 1
    project.selected_patterns.clear()
    for pattern in project.patterns:
        if pattern.is_selected:
            project.selected_patterns.add().uuid = pattern.global_uuid
    return selected


def apply_to_objects(context, project, uuids) -> int:
    """Select the meshes of exactly these patterns in the 3D viewport."""
    view_layer = context.view_layer
    wanted = set()
    active = None
    for pattern in project.patterns:
        if pattern.global_uuid in uuids and pattern.mesh_object is not None:
            wanted.add(pattern.mesh_object.name)
            active = pattern.mesh_object

    selected = 0
    for obj in view_layer.objects:
        props = getattr(obj, "qmyi_simulation_props", None)
        if obj.type != 'MESH' or props is None or not props.is_pattern_mesh:
            # Colliders, the body and every other object keep their selection.
            continue
        should_select = obj.name in wanted
        if obj.select_get() != should_select:
            obj.select_set(should_select)
        if should_select:
            selected += 1
    if active is not None:
        view_layer.objects.active = active
    return selected


def sync_once(context=None) -> bool:
    """One poll iteration; returns whether a side was applied to the other."""
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    qmyi = getattr(scene, "qmyi", None)
    if qmyi is None:
        return False
    if not qmyi.sync_selection:
        # Turning the toggle back on adopts the state that is then current.
        qmyi.set_temp_data_item(_KEY_3D, None)
        qmyi.set_temp_data_item(_KEY_2D, None)
        return False
    if qmyi.get_temp_data_item(_KEY_BUSY, False):
        return False

    project = active_project(context, qmyi)
    from_3d = selected_3d_uuids(context)
    from_2d = selected_2d_uuids(project) if project is not None else frozenset()
    last_3d = qmyi.get_temp_data_item(_KEY_3D, None)
    last_2d = qmyi.get_temp_data_item(_KEY_2D, None)
    qmyi.set_temp_data_item(_KEY_3D, from_3d)

    if last_3d is None:
        # First poll after the toggle went on: take note, change nothing.
        qmyi.set_temp_data_item(_KEY_2D, from_2d)
        return False

    if from_3d != last_3d and project is not None:
        qmyi.set_temp_data_item(_KEY_BUSY, True)
        try:
            apply_to_patterns(project, from_3d)
            qmyi.set_temp_data_item(_KEY_2D, selected_2d_uuids(project))
        finally:
            qmyi.set_temp_data_item(_KEY_BUSY, False)
        return True

    if from_2d != last_2d:
        qmyi.set_temp_data_item(_KEY_BUSY, True)
        try:
            apply_to_objects(context, project, from_2d)
            qmyi.set_temp_data_item(_KEY_3D, selected_3d_uuids(context))
        finally:
            qmyi.set_temp_data_item(_KEY_BUSY, False)
        qmyi.set_temp_data_item(_KEY_2D, from_2d)
        return True
    return False


def _timer() -> float:
    try:
        sync_once()
    except Exception as error:      # a bad scene must not kill the timer
        console.warning(f"selection sync: {type(error).__name__}: {error}")
    return POLL_INTERVAL


def register() -> None:
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, persistent=True)


def unregister() -> None:
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
