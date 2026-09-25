"""Patterns: create, read, edit, place, copy and remove them.

A pattern's own 2D space is millimetres. Every write checks its arguments first,
then the outline it produced, and puts the changed value back when the outline
is refused, so a call never leaves a pattern in the state it was refused for.
"""

from __future__ import annotations

import numpy as np

from . import _address as address
from .errors import QyapiError
from ..model.pattern import VALIDITY_INVALID


def list(project=None):  # noqa: A001 - the surface's name for this call
    """Every pattern of the project, with its counts and whether it is generated."""
    project = address.project_or_refuse(project)
    patterns = []
    for position, pattern in enumerate(project.patterns):  # loop: one dict per pattern
        patterns.append(_summary(pattern, position))
    return address.jsonify({"project": project.name, "patterns": patterns})


def get(name, project=None):
    """One pattern: its summary, its edge table and the sewings that touch it."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    entry = _summary(pattern, None)
    entry.update({
        "anchor": [float(pattern.anchor[0]), float(pattern.anchor[1])],
        "rotation_rad": float(pattern.rotation),
        "grain_dir_rad": float(pattern.grain_dir),
        "mirror": bool(pattern.is_mirror),
        "edges": _edge_table(pattern),
        "sewings": address.sewing_entries(project, pattern),
    })
    return address.jsonify(entry)


def points(name, project=None):
    """The pattern's outline vertices, in millimetres, in vertex order."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    values = [[float(vertex.co[0]), float(vertex.co[1])] for vertex in pattern.vertices]
    return address.jsonify({"pattern": pattern.name, "count": len(values), "points": values})


def create(points, name=None, granularity_mm=None, fabric=None, allow_crossing=False,
           project=None):
    """Create a closed, counter-clockwise pattern from points in millimetres.

    The loop is closed here: there is no open-pattern form. ``granularity_mm`` is
    the sampling ceiling, and ``fabric`` is a fabric name or None for the
    project's default. A name that is taken gets the add-on's suffix.
    ``allow_crossing`` lets this one call store an outline that crosses itself;
    such a pattern gets no mesh until the outline is fixed.
    """
    project = address.project_or_refuse(project)
    outline = address.clean_points(points)
    granularity = (float(granularity_mm) if granularity_mm is not None
                   else float(address.DEFAULT_GRANULARITY_MM))
    if not granularity > 0:
        raise QyapiError(f"granularity must be positive, got {granularity}")
    if not allow_crossing:
        address.check_outline(outline, granularity, "that outline")
    fabric_object = address.fabric_or_refuse(project, fabric)

    pattern = project.add_pattern()
    requested = pattern.name if name is None else str(name)
    pattern.name = address.unique_name(project, requested)
    for index, point in enumerate(outline):  # loop: one vertex object per point
        pattern.add_vertex(point)
    for index in range(len(outline)):  # loop: one edge object per segment
        pattern.add_edge(index, (index + 1) % len(outline), update=False)
    pattern.granularity = granularity
    pattern.fabric = fabric_object
    pattern.ensure_edge_ccw()
    pattern.generate_mesh()
    if pattern.mesh_object is None:
        if not allow_crossing:
            # The mesh stage refused what the quick check accepted: leave
            # nothing behind rather than a pattern without a mesh.
            project.remove_patterns([pattern], expand_groups=False)
            raise QyapiError("the mesh stage refused that outline",
                             ("a crossing or degenerate outline is never meshed",))
        # Allowed: the pattern stays without a mesh until its outline is fixed.

    address.write_done(f"create pattern {pattern.name}")
    entry = _summary(pattern, len(project.patterns) - 1)
    entry["requested_name"] = requested
    return address.jsonify(entry)


def set_point(name, index, xy, allow_crossing=False, project=None):
    """Move one of the pattern's vertices, in millimetres."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    index = _vertex_index(pattern, index)
    point = address.clean_point(xy, "the new position")
    previous = _vertex_co(pattern, index)
    members = _chain_members(pattern)
    if not allow_crossing:
        address.check_outline(_proposed_vertices(pattern, index, point),
                              pattern.granularity, "moving that point")
    _write_all(members, lambda member: _set_vertex(member, index, point))
    error = _finish(project, pattern, members,
                    restore=lambda member: _set_vertex(member, index, previous),
                    allow_crossing=allow_crossing)
    address.write_done(f"move a point of {pattern.name}")
    return address.jsonify(_edit_result(pattern, "set_point", error))


def add_point(name, edge, xy, allow_crossing=False, project=None):
    """Split one straight edge with a new vertex, in millimetres."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    edge_object, edge_index = address.edge_or_refuse(pattern, edge)
    if edge_object.kind != "straight":
        raise QyapiError(f"edge {edge_index} of {pattern.name!r} is a {edge_object.kind} edge",
                         ("only a straight edge can take a new point",
                          "make it straight first, or move one of its ends"))
    point = address.clean_point(xy, "the new point")
    members = _chain_members(pattern)
    boundary = _boundary_points(pattern)
    boundary.insert(edge_index + 1, point)
    if not allow_crossing:
        address.check_outline(boundary, pattern.granularity, "splitting that edge")
    _write_all(members, lambda member: _split_edge(member, edge_index, point))
    error = _finish(project, pattern, members, allow_crossing=allow_crossing)
    address.write_done(f"add a point to {pattern.name}")
    return address.jsonify(_edit_result(pattern, "add_point", error))


def remove_point(name, index, allow_crossing=False, project=None):
    """Remove one vertex and merge the two edges that met there.

    The surviving edge keeps its identity, so a sewing on it stays; a sewing on
    the edge that goes away is dropped and counted in the result.
    """
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    index = _vertex_index(pattern, index)
    if len(pattern.edges) - 1 < 3:
        raise QyapiError(f"{pattern.name!r} would be left with fewer than three edges")
    previous_edge, next_edge, previous_index, next_index = _edges_at_vertex(pattern, index)
    for line in pattern.internal_lines:  # loop: internal lines have their own indices
        for edge in line.edges:
            if index in (int(edge.vertex_index[0]), int(edge.vertex_index[1])):
                raise QyapiError("an internal line uses that point",
                                 ("remove the internal line first",))
    boundary = _boundary_points(pattern)
    del boundary[next_index if next_index < len(boundary) else previous_index]
    if not allow_crossing:
        address.check_outline(boundary, pattern.granularity, "merging those edges")

    dropped = _mark_impacted_sewings(project, pattern.edges[next_index].global_uuid)
    project.remove_impacted_sewings()
    members = _chain_members(pattern)
    _write_all(members, lambda member: _merge_vertex(member, index))
    error = _finish(project, pattern, members, allow_crossing=allow_crossing)
    address.write_done(f"remove a point of {pattern.name}")
    entry = _edit_result(pattern, "remove_point", error)
    entry["dropped_sewings"] = dropped
    return address.jsonify(entry)


def set_handle(name, edge, which, xy=None, type=None, allow_crossing=False,
               project=None):
    """Set one handle of one edge: its position in millimetres and/or its type."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    edge_object, edge_index = address.edge_or_refuse(pattern, edge)
    which = int(which)
    if which not in (1, 2):
        raise QyapiError(f"a handle is 1 or 2, got {which}")
    handle = edge_object.handle1 if which == 1 else edge_object.handle2
    previous = {"co": (float(handle.co[0]), float(handle.co[1])),
                "type": (edge_object.handle1_type if which == 1
                         else edge_object.handle2_type)}
    point = None if xy is None else address.clean_point(xy, "the handle")
    if type is not None and type not in ("VECTOR", "FREE", "ALIGNED"):
        raise QyapiError(f"unknown handle type {type!r}",
                         ("types: VECTOR (straight), FREE, ALIGNED",))
    members = _chain_members(pattern)

    def write(member):
        target = member.edges[edge_index]
        handle_of = target.handle1 if which == 1 else target.handle2
        if point is not None:
            handle_of.co = point
        if type is not None:
            if which == 1:
                target.handle1_type = type
            else:
                target.handle2_type = type
        target.need_update_points = True

    def restore(member):
        target = member.edges[edge_index]
        handle_of = target.handle1 if which == 1 else target.handle2
        handle_of.co = previous["co"]
        if which == 1:
            target.handle1_type = previous["type"]
        else:
            target.handle2_type = previous["type"]
        target.need_update_points = True

    _write_all(members, write)
    error = _finish(project, pattern, members, restore=restore,
                    allow_crossing=allow_crossing)
    address.write_done(f"set a handle of {pattern.name}")
    return address.jsonify(_edit_result(pattern, "set_handle", error))


def add_spline_point(name, edge, xy, allow_crossing=False, project=None):
    """Add an interpolating control point to an edge, in millimetres."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    edge_object, edge_index = address.edge_or_refuse(pattern, edge)
    point = address.clean_point(xy, "the control point")
    members = _chain_members(pattern)
    _write_all(members, lambda member: _add_spline_point(member, edge_index, point))
    error = _finish(project, pattern, members,
                    restore=lambda member: _drop_spline_point(member, edge_index, None),
                    allow_crossing=allow_crossing)
    address.write_done(f"add a spline point to {pattern.name}")
    return address.jsonify(_edit_result(pattern, "add_spline_point", error))


def remove_spline_point(name, edge, index, allow_crossing=False, project=None):
    """Remove one interpolating control point from an edge."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    edge_object, edge_index = address.edge_or_refuse(pattern, edge)
    index = int(index)
    if not 0 <= index < len(edge_object.spline_points):
        raise QyapiError(f"that edge has {len(edge_object.spline_points)} control points",
                         (f"index {index} is out of range",))
    previous = (float(edge_object.spline_points[index].co[0]),
                float(edge_object.spline_points[index].co[1]))
    members = _chain_members(pattern)
    _write_all(members, lambda member: _drop_spline_point(member, edge_index, index))
    error = _finish(project, pattern, members,
                    restore=lambda member: _add_spline_point(member, edge_index,
                                                             previous, at=index),
                    allow_crossing=allow_crossing)
    address.write_done(f"remove a spline point of {pattern.name}")
    return address.jsonify(_edit_result(pattern, "remove_spline_point", error))


def add_internal_line(name, points, is_hole=False, closed=False, project=None):
    """Add an internal line (a cut) from a polyline inside the outline, in millimetres."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    values = [address.clean_point(value, f"points[{index}]")
              for index, value in enumerate(points)]  # loop: one pair per point
    if len(values) < 2:
        raise QyapiError("an internal line needs at least two points")
    segments = []
    # Built by hand: this module's own `list` shadows the builtin one, so the
    # builtin is not available here.
    for index, start in enumerate(values):  # loop: one curve piece per segment
        if index + 1 < len(values):
            end = values[index + 1]
        elif closed:
            end = values[0]
        else:
            break
        segments.append({"p0": start, "p1": end, "h1": (0.0, 0.0), "h2": (0.0, 0.0),
                         "h1_type": "VECTOR", "h2_type": "VECTOR"})
    if address.degenerate_pair(values, pattern.granularity) is not None:
        raise QyapiError("that internal line has two points on top of each other",
                         ("move them apart",))
    members = _chain_members(pattern)

    def write(member):
        line = member.add_internal_line(segments, is_loop=bool(closed))
        line.is_hole = bool(is_hole)
        # The line lives in the pattern's Sketch, so one call wrote it for the
        # whole instance chain; the Sketch builds each member's mesh.
        member.require_sketch().rebuild_meshes()

    _write_all(members, write)
    address.write_done(f"add an internal line to {pattern.name}")
    entry = _edit_result(pattern, "add_internal_line")
    entry["internal_lines"] = len(pattern.internal_lines)
    return address.jsonify(entry)


def remove_internal_line(name, index, project=None):
    """Remove one internal line and the control points it owned."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    index = int(index)
    if not 0 <= index < len(pattern.internal_lines):
        raise QyapiError(f"pattern {pattern.name!r} has {len(pattern.internal_lines)} "
                         f"internal lines",
                         (f"index {index} is out of range",))
    members = _chain_members(pattern)
    _write_all(members, lambda member: _drop_internal_line(member, index))
    address.write_done(f"remove an internal line of {pattern.name}")
    entry = _edit_result(pattern, "remove_internal_line")
    entry["internal_lines"] = len(pattern.internal_lines)
    return address.jsonify(entry)


def transform(name, anchor=None, rotation=None, grain_dir=None, collision_layer=None,
              mirror=None, project=None):
    """Place the pattern: anchor (millimetres), angles (radians), layer and mirror."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    if anchor is not None:
        pattern.anchor = address.clean_point(anchor, "the anchor")
    if rotation is not None:
        pattern.rotation = float(rotation)
    if grain_dir is not None:
        pattern.grain_dir = float(grain_dir)
    if collision_layer is not None:
        pattern.collision_layer = int(collision_layer)
    if mirror is not None:
        pattern.is_mirror = bool(mirror)
        pattern.generate_mesh()
    address.write_done(f"place pattern {pattern.name}")
    return address.jsonify(_edit_result(pattern, "transform"))


def copy(name, mirror=False, anchor=None, project=None):
    """Copy the pattern as an instance (or a mirror) at an anchor, in millimetres."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    if anchor is not None:
        anchor = address.clean_point(anchor, "the anchor")
    new_pattern = pattern.copy_pattern(as_instance=True, mirror=bool(mirror),
                                       project=project, anchor=anchor)
    address.write_done(f"copy pattern {pattern.name}")
    entry = _summary(new_pattern, len(project.patterns) - 1)
    entry["source"] = pattern.name
    return address.jsonify(entry)


def remove(names, project=None):
    """Remove patterns and report what went with them."""
    project = address.project_or_refuse(project)
    if isinstance(names, str):
        names = [names]
    targets = [address.pattern_or_refuse(project, name) for name in names]
    for pattern in targets:  # loop: one generator check per pattern
        if int(pattern.generator_uuid) != -1:
            raise QyapiError(
                f"{pattern.name!r} comes from a generator, and removing it would "
                f"take its whole group",
                ("qyapi.generators.detach() turns the group into ordinary patterns",
                 "qyapi.generators.remove() removes the group"))
    before = len(project.sewings)
    removed = [pattern.name for pattern in targets]
    project.remove_patterns(targets, expand_groups=False)
    after = len(project.sewings)
    address.write_done(f"remove pattern(s) {', '.join(removed) or '(none)'}")
    return address.jsonify({"removed": removed, "dropped_sewings": before - after,
                            "patterns_left": len(project.patterns)})


def detach(name, project=None):
    """Give one pattern a Sketch of its own, leaving the other members together.

    A chain reads one Sketch, so its members cannot hold different geometry; a
    pattern that is to be edited on its own is detached first. The pattern keeps the
    shape the chain has now, and the members that stayed linked keep reading the
    Sketch they had.
    """
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    report = pattern.detach()
    address.write_done(f"detach pattern {pattern.name}")
    return address.jsonify(report)


def validate(names=None, project=None):
    """Test the outlines now and report the ones that cross themselves."""
    project = address.project_or_refuse(project)
    if names is None:
        targets = [pattern for pattern in project.patterns]
    elif isinstance(names, str):
        targets = [address.pattern_or_refuse(project, names)]
    else:
        targets = [address.pattern_or_refuse(project, name) for name in names]
    result = []
    for pattern in targets:  # loop: one outline test per pattern
        state = pattern.validate(force=True)
        crossing = pattern.invalid_point
        result.append({
            "pattern": pattern.name,
            "valid": state != VALIDITY_INVALID,
            "crossing": None if crossing is None
            else [float(crossing[0]), float(crossing[1])],
        })
    return address.jsonify({"patterns": result})


def fabrics(project=None):
    """The project's fabrics, by name."""
    project = address.project_or_refuse(project)
    names = [fabric.name for fabric in project.fabrics]
    return address.jsonify({"project": project.name, "fabrics": names})


def assign_fabric(name, fabric, project=None):
    """Give a pattern a fabric by name."""
    project = address.project_or_refuse(project)
    pattern = address.pattern_or_refuse(project, name)
    pattern.fabric = address.fabric_or_refuse(project, fabric)
    address.write_done(f"assign a fabric to {pattern.name}")
    entry = _edit_result(pattern, "assign_fabric")
    entry["fabric"] = address.fabric_name(pattern)
    return address.jsonify(entry)


# --- internals -------------------------------------------------------------

def _summary(pattern, position):
    mesh = pattern.mesh_object
    sketch = pattern.sketch
    entry = {
        "name": pattern.name,
        "index": position,
        # The two layers: the Sketch a pattern reads its geometry from, and this
        # pattern's own derived state. A chain reports one Sketch and one entry
        # per member.
        "sketch": sketch.name if sketch is not None else None,
        "vertices": len(pattern.vertices),
        "edges": len(pattern.edges),
        "internal_lines": len(pattern.internal_lines),
        "granularity_mm": float(pattern.granularity),
        "collision_layer": int(pattern.collision_layer),
        "fabric": address.fabric_name(pattern),
        "mesh_object": mesh.name if mesh is not None else None,
        "mesh_vertices": len(mesh.data.vertices) if mesh is not None else 0,
        "generated": int(pattern.generator_uuid) != -1,
        "chain": [member.name for member in address.chain_of(pattern)],
    }
    entry.update(address.outline_report(pattern))
    return entry


def _edge_table(pattern):
    table = []
    for index, edge in enumerate(pattern.edges):  # loop: one dict per edge
        handles = len(edge.handles)
        table.append({
            "index": index,
            "label": edge.name or None,
            "kind": edge.kind,
            "v0": int(edge.vertex_index[0]),
            "v1": int(edge.vertex_index[1]),
            "p0": [float(edge.vertex0.co[0]), float(edge.vertex0.co[1])],
            "p1": [float(edge.vertex1.co[0]), float(edge.vertex1.co[1])],
            "handle1": None if handles < 1 else [float(edge.handle1.co[0]),
                                                 float(edge.handle1.co[1])],
            "handle2": None if handles < 2 else [float(edge.handle2.co[0]),
                                                 float(edge.handle2.co[1])],
            "handle1_type": edge.handle1_type,
            "handle2_type": edge.handle2_type,
            "spline_points": len(edge.spline_points),
            "length_mm": float(edge.length),
        })
    return table


def _vertex_index(pattern, index):
    index = int(index)
    if not 0 <= index < len(pattern.vertices):
        raise QyapiError(f"pattern {pattern.name!r} has {len(pattern.vertices)} vertices",
                         (f"index {index} is out of range",))
    return index


def _vertex_co(pattern, index):
    vertex = pattern.vertices[index]
    return (float(vertex.co[0]), float(vertex.co[1]))


def _boundary_points(pattern):
    """The outline as the edge list walks it: each edge's start point."""
    return [_vertex_co(pattern, int(edge.vertex_index[0])) for edge in pattern.edges]


def _proposed_vertices(pattern, index, point):
    values = [_vertex_co(pattern, position)
              for position in range(len(pattern.vertices))]  # loop: one pair per vertex
    values[index] = point
    return values


def _chain_members(pattern):
    """The pattern and the copies that share its Sketch.

    There is nothing to compare: a chain holds one Sketch, so its members cannot
    hold different geometry. `members` is still the list every caller needs, for
    the derived work each member does for itself.
    """
    return address.chain_of(pattern)


def _write_all(members, write):
    """Write one chain's edit - once.

    Every member reads the same Sketch, so one write reaches all of them. The
    name is kept because the callers read as "this edit reaches the whole
    chain", which is what it does; the members rebuild their own samples and
    meshes afterwards, in `_finish`.
    """
    write(members[0])


def _refresh(pattern):
    pattern.mark_geometry_changed()


def _outline_error(pattern):
    """Why the pattern's outline is unusable now, or None."""
    if pattern.validate(force=True) == VALIDITY_INVALID:
        crossing = pattern.invalid_point
        where = "" if crossing is None else f" near ({crossing[0]:.3f}, {crossing[1]:.3f})"
        return QyapiError(f"the outline would cross itself{where}",
                          ("the edit was put back",))
    close = address.degenerate_pair(_boundary_points(pattern), pattern.granularity)
    if close is not None:
        closest, limit = close
        return QyapiError(
            f"the outline would put two points {closest:.3f} mm apart, below the "
            f"{limit:.3f} mm mesh tolerance",
            ("the edit was put back",))
    return None


def _finish(project, pattern, members, restore=None, allow_crossing=False):
    """Test what was written, then build the meshes - or report and keep it.

    With ``allow_crossing`` the outline test still runs, but a crossing outline
    is kept and reported instead of put back, and the meshes are not built: the
    mesh stage refuses a crossing outline anyway, so the patterns keep theirs.
    """
    for member in members:  # loop: the derived data of every copy
        _refresh(member)
    error = _outline_error(pattern)
    if error is not None:
        if allow_crossing:
            return error
        if restore is not None:
            _write_all(members, restore)
            for member in members:
                _refresh(member)
        raise error
    for member in members:
        member.generate_mesh()
    return None


def _edit_result(pattern, action, error=None):
    entry = _summary(pattern, None)
    entry["action"] = action
    if error is not None:
        entry["allowed_crossing"] = True
        entry["warning"] = str(error)
    return entry


def _set_vertex(pattern, index, point):
    pattern.vertices[index].co = point


def _split_edge(pattern, edge_index, point):
    edge = pattern.edges[edge_index]
    end_index = int(edge.vertex_index[1])
    new_index = pattern.add_vertex(point)
    edge.vertex_index[1] = new_index
    new_edge = pattern.edges.add()
    new_edge.get_temp_data()
    new_edge.vertex_index[0] = new_index
    new_edge.vertex_index[1] = end_index
    new_edge.set_curve("straight")
    # Append then move: removing and rewriting the list would give every edge a
    # new identity and break the sewings that point at them.
    pattern.edges.move(len(pattern.edges) - 1, edge_index + 1)
    pattern.refresh_collection_uuid(pattern.edges)


def _edges_at_vertex(pattern, index):
    """The edge ending at `index` and the one starting there."""
    previous = next_edge = None
    previous_index = next_index = None
    for position, edge in enumerate(pattern.edges):  # loop: one look per edge
        if int(edge.vertex_index[1]) == index and previous is None:
            previous, previous_index = edge, position
        if int(edge.vertex_index[0]) == index and next_edge is None:
            next_edge, next_index = edge, position
    if previous is None or next_edge is None:
        raise QyapiError(f"the point is not on the outline of {pattern.name!r}",
                         ("a point joins exactly two edges in a closed outline",))
    if previous is next_edge:
        raise QyapiError("that pattern is too small to lose a point")
    return previous, next_edge, previous_index, next_index


def _merge_vertex(pattern, index):
    previous, next_edge, previous_index, next_index = _edges_at_vertex(pattern, index)
    new_end = int(next_edge.vertex_index[1])
    previous.vertex_index[1] = new_end
    previous.set_curve("straight")
    pattern.edges.remove(next_index)
    pattern.vertices.remove(index)
    for edge in pattern.edges:  # loop: one index fix per edge
        _shift_index(edge, index)
    for line in pattern.internal_lines:  # loop: internal lines carry indices too
        for edge in line.edges:
            _shift_index(edge, index)
    pattern.refresh_collection_uuid(pattern.edges)
    pattern.refresh_collection_uuid(pattern.vertices)


def _shift_index(edge, removed_index):
    for slot in (0, 1):  # loop: the two ends of one edge
        if int(edge.vertex_index[slot]) > removed_index:
            edge.vertex_index[slot] = int(edge.vertex_index[slot]) - 1


def _add_spline_point(pattern, edge_index, point, at=None):
    edge = pattern.edges[edge_index]
    if at is None:
        control = edge.spline_points.add()
    else:
        control = edge.spline_points.add()
        position = len(edge.spline_points) - 1
        edge.spline_points.move(position, int(at))
    control.get_temp_data()
    control.co = point
    edge.need_update_points = True
    # Adding retires the wrappers the collection handed out before, so the map
    # has to name the ones it holds now: a pick reads a control point back by
    # its identity.
    edge.refresh_collection_uuid(edge.spline_points)


def _drop_spline_point(pattern, edge_index, index):
    edge = pattern.edges[edge_index]
    if index is None:
        index = len(edge.spline_points) - 1
    if 0 <= index < len(edge.spline_points):
        edge.spline_points.remove(index)
    edge.need_update_points = True
    edge.refresh_collection_uuid(edge.spline_points)


def _drop_internal_line(pattern, index):
    line = pattern.internal_lines[index]
    used = set()
    for edge in line.edges:  # loop: one pair of indices per internal edge
        used.add(int(edge.vertex_index[0]))
        used.add(int(edge.vertex_index[1]))
    pattern.internal_lines.remove(index)
    removable = sorted((position for position in used
                        if _vertex_is_orphan(pattern, position)), reverse=True)
    for position in removable:  # loop: RNA removal is per item and descending
        pattern.vertices.remove(position)
        for edge in pattern.edges:
            _shift_index(edge, position)
        for other in pattern.internal_lines:
            for edge in other.edges:
                _shift_index(edge, position)
    pattern.refresh_collection_uuid(pattern.vertices)
    pattern.refresh_collection_uuid(pattern.edges)
    pattern.mark_geometry_changed()
    # The line lived in the pattern's Sketch, so its removal is one edit for the
    # whole instance chain: the Sketch builds each member's mesh.
    pattern.require_sketch().rebuild_meshes()


def _vertex_is_orphan(pattern, index):
    """Whether only an internal line used this vertex."""
    for edge in pattern.edges:  # loop: one look per boundary edge
        if index in (int(edge.vertex_index[0]), int(edge.vertex_index[1])):
            return False
    return True


def _mark_impacted_sewings(project, uuid):
    """Flag the sewings that will lose this edge; returns how many there are."""
    count = 0
    for sewing in project.sewings:  # loop: one look per sewing
        keys = (sewing.side1.line1_uuid, sewing.side1.line2_uuid,
                sewing.side2.line1_uuid, sewing.side2.line2_uuid)
        if uuid in keys:
            sewing.impacted = True
            count += 1
    return count
