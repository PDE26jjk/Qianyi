"""Helpers the script surface's submodules share.

Separate from the package module so a submodule can import them while the
package is still initialising: this module needs Blender and the add-on's model
layer, and nothing from the surface itself.
"""

from __future__ import annotations

import bpy
import numpy as np

from .errors import QyapiError
from .. import global_data

from ..model.model_data import owner_pattern, refresh_all_uuids
from ..model.pattern import boundary_self_intersection
from ..utilities.node_tree import get_all_node_tree

# The mesh stage de-duplicates boundary points closer together than
# granularity * this, and a pattern carrying such a pair becomes a sliver the
# sampler cannot walk.
MESH_TOLERANCE_FACTOR = 0.02
# The property's own default, used when a caller does not give a granularity.
DEFAULT_GRANULARITY_MM = 20.0


def _names(collection):
    return [item.name for item in collection]


def refresh():
    """Rebuild the identity map every entry point starts from."""
    refresh_all_uuids()


def project_or_refuse(name=None):
    """The project to work on: the active one, or the named one."""
    refresh_all_uuids()
    projects = get_all_node_tree()
    if not projects:
        raise QyapiError("this scene has no project",
                         ("qyapi.projects.create() makes one",
                          "qyapi.state() lists what the scene holds"))
    if name is None:
        return active_project() or projects[0]
    for project in projects:
        if project.name == name:
            return project
    raise QyapiError(f"no project named {name!r}",
                     (f"projects: {', '.join(project.name for project in projects)}",))


def active_project():
    """The project the active index points at, or None when there is none.

    ``active_project_index`` indexes `bpy.data.node_groups`, which also holds
    node trees that are not projects, so the index is matched against the
    projects rather than used directly.
    """
    projects = get_all_node_tree()
    if not projects:
        return None
    scene = getattr(bpy.context, "scene", None)
    index = int(getattr(getattr(scene, "qmyi", None), "active_project_index", 0))
    groups = bpy.data.node_groups
    if 0 <= index < len(groups):
        for project in projects:
            if project == groups[index]:
                return project
    return projects[0]


def outline_report(pattern):
    """A pattern's cached validity, its crossing point, and whether its mesh is stale.

    A crossing outline is never handed to the mesh sampler, so a pattern that
    crosses keeps whatever mesh it had - which is what "stale" means here.
    """
    state = str(pattern.validity_state).lower()
    crossing = pattern.invalid_point
    return {
        "outline_validity": state,
        "crossing": None if crossing is None
        else [float(crossing[0]), float(crossing[1])],
        "mesh_stale": state == "invalid",
    }


def pattern_or_refuse(project, name):
    matches = [index for index, pattern in enumerate(project.patterns)
               if pattern.name == name]
    if len(matches) > 1:
        # A generator names its patterns after the component's slots, so a slot
        # can collide with a hand-made pattern. Addressing must not guess.
        raise QyapiError(f"{len(matches)} patterns are named {name!r}",
                         (f"indexes: {', '.join(str(index) for index in matches)}",
                          "rename one of them, or read them with qyapi.patterns.list()"))
    if matches:
        pattern = project.patterns[matches[0]]
        ensure_current(pattern)
        return pattern
    raise QyapiError(f"no pattern named {name!r}",
                     (f"patterns: {', '.join(_names(project.patterns))}",
                      "qyapi.patterns.list() has the same names with their counts"))


def fabric_or_refuse(project, name):
    """A fabric by name; no name means the project's default fabric."""
    if name is None:
        fabric = project.get_default_fabric()
        refresh_all_uuids()
        return fabric
    for fabric in project.fabrics:  # loop: one name comparison per fabric
        if fabric.name == name:
            return fabric
    raise QyapiError(f"no fabric named {name!r}",
                     (f"fabrics: {', '.join(_names(project.fabrics)) or '(none)'}",))


def fabric_name(pattern):
    """The fabric's name without triggering the property that writes.

    `Pattern.fabric` assigns the default fabric when the pattern has none, so a
    read must not call it.
    """
    uuid = int(pattern.fabric_uuid)
    if uuid == -1:
        return None
    try:
        fabric = global_data.get_obj_by_uuid(uuid)
    except Exception:
        return None
    return getattr(fabric, "name", None)


def unique_name(project, base):
    """The add-on's own naming rule for a collection that already uses `base`."""
    from ..model.qianyi_project import get_unique_name

    return get_unique_name(project.patterns, base)


def ensure_current(pattern):
    """Refresh a pattern's derived data without touching its outline."""
    pattern.ensure_sections()
    return pattern


def chain_of(pattern):
    """Every pattern that shares geometry with this one, this one included."""
    return pattern.sketch_members()


def edge_or_refuse(pattern, reference):
    """An edge by its index or by its label; returns (edge, index)."""
    if isinstance(reference, str):
        found = [entry for entry in enumerate(pattern.edges)
                 if entry[1].name == reference]
        if not found:
            labels = [edge.name for edge in pattern.edges if edge.name]
            raise QyapiError(
                f"pattern {pattern.name!r} has no edge labelled {reference!r}",
                (f"labels: {', '.join(labels) or '(none)'}",
                 "an edge index works for every pattern"))
        if len(found) > 1:
            raise QyapiError(f"pattern {pattern.name!r} has {len(found)} edges "
                             f"labelled {reference!r}",
                             ("name the edge by its index instead",))
        index, edge = found[0]
    else:
        index = int(reference)
        if not 0 <= index < len(pattern.edges):
            raise QyapiError(f"pattern {pattern.name!r} has no edge {index}",
                             (f"it has {len(pattern.edges)} edges",))
        edge = pattern.edges[index]
    return edge, index


def edge_ref(pattern, index):
    """How an edge is reported: index and label, not a handle."""
    edge = pattern.edges[index]
    return {"pattern": pattern.name, "index": int(index),
            "label": edge.name or None, "kind": edge.kind}


def side_entry(sewing, side_number):
    """One side of a sewing, as plain data."""
    side = sewing.side1 if side_number == 1 else sewing.side2
    try:
        pattern = owner_pattern(side.line1)
        pattern_name = pattern.name
        label = side.line1.name or None
        index = side.line1.get_index()
    except Exception:
        pattern_name, label, index = None, None, None
    return {"side": side_number, "pattern": pattern_name, "edge_index": index,
            "edge_label": label, "pos1": float(side.pos1), "pos2": float(side.pos2),
            "reverse": bool(side.reverse)}


def sewing_entry(project, sewing, index, section_error=None):
    """One sewing, with both sides and its stitch count when that can be read."""
    entry = {
        "index": int(index),
        "sides": [side_entry(sewing, 1), side_entry(sewing, 2)],
        "color": [float(value) for value in sewing.color],
        "stitch_count": None,
        "stitch_error": section_error,
    }
    if section_error is not None:
        return entry
    try:
        stitches = sewing.get_stitch_data()["stitches"]
        entry["stitch_count"] = int(len(stitches))
    except Exception as error:
        # A seam on a pattern whose outline is invalid has no mesh to count
        # against; that is a fact about the scene, not a failure of the read.
        entry["stitch_error"] = f"{type(error).__name__}: {error}"
    return entry


def sewing_entries(project, pattern=None):
    """Every sewing, or the ones that touch `pattern` - one builder for both."""
    # Reading a sewing reads the walk it makes, and the linking run is what
    # builds the pieces a walk needs: it starts its own table, so linking here
    # is the whole "fresh sections, then link them" sequence without rebuilding
    # the stage and the samples of every pattern a sewing touches.
    section_error = None
    try:
        project.calc_sewings_sections(project.sewings)
    except Exception as error:
        section_error = f"{type(error).__name__}: {error}"
    entries = []
    for index, sewing in enumerate(project.sewings):  # loop: one dict per sewing
        entry = sewing_entry(project, sewing, index, section_error)
        if pattern is not None and pattern.name not in {side["pattern"]
                                                        for side in entry["sides"]}:
            continue
        entries.append(entry)
    return entries


def clean_point(value, what="point"):
    try:
        x, y = float(value[0]), float(value[1])
    except Exception as error:
        raise QyapiError(f"{what} must be a pair of numbers, got {value!r}") from error
    if not (np.isfinite(x) and np.isfinite(y)):
        raise QyapiError(f"{what} must be finite, got {value!r}")
    return (x, y)


def clean_points(values, what="points"):
    points = [clean_point(value, f"{what}[{index}]")
              for index, value in enumerate(values)]  # loop: one pair per point
    if len(points) < 3:
        raise QyapiError(f"a pattern outline needs at least 3 {what}, got {len(points)}")
    if len({point for point in points}) != len(points):
        raise QyapiError("a pattern outline cannot repeat a point")
    return points


def degenerate_pair(points, granularity_mm):
    """Distance and limit of the closest pair, or None when nothing is too close."""
    array = np.asarray(points, dtype=np.float64)
    if len(array) < 2:
        return None
    deltas = array[:, None, :] - array[None, :, :]
    distances = np.sqrt((deltas ** 2).sum(axis=2))
    np.fill_diagonal(distances, np.inf)
    closest = float(distances.min())
    limit = max(float(granularity_mm) * MESH_TOLERANCE_FACTOR, 1e-6)
    if closest < limit:
        return closest, limit
    return None


def check_outline(points, granularity_mm, what="this outline"):
    """Refuse a crossing or degenerate outline before anything is written."""
    close = degenerate_pair(points, granularity_mm)
    if close is not None:
        closest, limit = close
        raise QyapiError(
            f"{what} would put two points {closest:.3f} mm apart, below the "
            f"{limit:.3f} mm mesh tolerance",
            ("move the points apart, or use a coarser granularity",))
    intersected, crossing = boundary_self_intersection(np.asarray(points, dtype=np.float32))
    if intersected:
        where = "" if crossing is None else f" near ({crossing[0]:.3f}, {crossing[1]:.3f})"
        raise QyapiError(f"{what} would cross itself{where}",
                         ("a crossing outline is never meshed",
                          "move the points so the loop does not cross"))


def jsonify(value):
    """Out through the package's own converter, looked up at call time."""
    from . import _jsonify

    return _jsonify(value)


def write_done(message):
    """One undo step for one write call, through the package's own rule."""
    from . import end_write

    return end_write(message)
