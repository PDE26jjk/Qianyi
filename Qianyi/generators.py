"""Bridge between the Blender-free panel library and the add-on project.

Everything that has to touch Blender data lives here: creating a generator,
writing the library's panels into patterns, and rebuilding them when a
parameter changes. The geometry itself comes from :mod:`Qianyi.panellib`.
"""

from __future__ import annotations

import bpy
import numpy as np
from mathutils import Vector

from . import global_data
from .model.generator import (PatternGenerator, generator_of_pattern, instance_chain,
                              refresh_generators)
from .model.pattern import VALIDITY_INVALID
from .panellib import component, registry
from .panellib import hooks
from .panellib.land import LandedPanel, land_panel, topology_of
from .utilities.console import console


def create_generator(project, component_id: str, params: dict | None = None) -> PatternGenerator:
    """Add a generator for ``component_id`` to the project and build it."""
    info = registry.info(component_id)
    generator = project.generators.add()
    generator.component_id = component_id
    generator.version = info.version
    generator.name = _unique_name(project, info.label or component_id)
    generator.apply_schema({"params": info.params})
    if params:
        generator.set_values(params)
    refresh_generators(project)
    project.active_generator_index = len(project.generators) - 1
    apply_generator(project, generator)
    _create_internal_seams(project, generator)
    return generator


def _create_internal_seams(project, generator) -> int:
    """Create a generator's own seams, once, when the generator is created.

    They are not recreated on rebuilds: a rebuild only keeps them attached
    through the normal edge-label remap, or drops a seam whose edge no longer
    exists.
    """
    try:
        spec = component.build_component(generator.component_id, _clamped_values(generator))
    except Exception as error:
        console.warning(f"generator '{generator.name}': cannot resolve internal seams: {error}")
        return 0
    if not spec.seams:
        return 0
    panels = {}
    for output in generator.outputs:
        pattern = global_data.get_obj_by_uuid(output.pattern_uuid, check_uuid=False)
        if pattern is not None:
            panels[output.slot] = pattern
    created = 0
    # Deliberate loop: one sewing per declared seam pair.
    for seam in spec.seams:
        first = panels.get(seam.panel_a)
        second = panels.get(seam.panel_b)
        if first is None or second is None:
            continue
        edge_a = _edge_named(first, seam.edge_a)
        edge_b = _edge_named(second, seam.edge_b)
        if edge_a is None or edge_b is None:
            continue
        if project.add_sewing1to1(edge_a, edge_b, reverse=seam.reverse) is not None:
            created += 1
    if created:
        console.print(f"generator '{generator.name}': {created} internal seam(s)")
    return created


def _edge_named(pattern, name: str):
    """The first edge of a pattern carrying the given label."""
    for edge in pattern.edges:
        if edge.name == name:
            return edge
    return None


def _unique_name(project, base: str) -> str:
    existing = {generator.name for generator in project.generators}
    if base not in existing:
        return base
    suffix = 1
    while f"{base}.{suffix:03d}" in existing:
        suffix += 1
    return f"{base}.{suffix:03d}"


def apply_generator(project, generator) -> dict:
    """Rebuild every panel this generator owns.

    A panel whose edge list is unchanged is rewritten in place, so its edges
    (and every sewing pointing at them) keep their identity. Panels the
    component no longer produces are removed.
    """
    if generator.applying:
        return {"skipped": True}

    refresh_generators(project)
    generator.applying = True
    try:
        snapshots = _snapshot_outputs(project, generator)
        try:
            spec = component.build_component(generator.component_id,
                                             _clamped_values(generator))
        except Exception as error:
            console.error(f"generator '{generator.name}': cannot build "
                          f"'{generator.component_id}': {error}")
            return {"error": str(error)}

        landed_panels = []
        for panel_spec in spec.panels:
            landed = land_panel(panel_spec)
            landed_panels.append(landed)

        report = {"created": 0, "in_place": 0, "rebuilt": 0, "removed": 0}
        report["remapped"] = 0
        report["dropped_sewings"] = 0
        report["invalid_panels"] = 0
        report["hook"] = None
        keep: list[str] = []
        written = []
        for landed in landed_panels:
            pattern, created = _ensure_output(project, generator, landed.name)
            targets = instance_chain(pattern)
            in_place = (not created) and all(
                topology_of(landed) == _pattern_topology(target) for target in targets)
            # Copies follow their source: mirrors are the same panel, so they are
            # written and remeshed with it instead of drifting apart.
            for target in targets:
                target.generator_uuid = generator.global_uuid
                _write_pattern(target, landed, in_place)
                # A crossing outline is a legal state while editing, so the
                # geometry is written and the mesh stage decides: generate_mesh
                # runs the same outline test as the interactive tools and keeps
                # the previous mesh when the outline is invalid.
                # Vertices closer together than the mesh stage's own
                # de-duplication distance are a second hazard: the outline still
                # passes the crossing test and the sampler then walks a
                # zero-area sliver. Keep the previous mesh when that happens.
                degenerate = _too_close_vertices(target)
                if degenerate is not None:
                    report["degenerate_panels"] = report.get("degenerate_panels", 0) + 1
                    console.warning(f"generator '{generator.name}': panel "
                                    f"'{landed.name}' mesh kept, {degenerate}")
                else:
                    target.generate_mesh()
                if target.validate() == VALIDITY_INVALID:
                    report["invalid_panels"] += 1
                    console.warning(f"generator '{generator.name}': panel "
                                    f"'{landed.name}' outline is invalid, mesh kept")
                written.append((target, snapshots.get(target.global_uuid, [])))
            if created:
                report["created"] += 1
            elif in_place:
                report["in_place"] += 1
            else:
                report["rebuilt"] += 1
            keep.append(landed.name)
        override, state = _run_hook(generator, written)
        report["hook"] = state
        if state != hooks.HANDLED:
            index = _sewing_index(project)
            for target, snapshot in written:
                remapped, dropped = _remap_sewings(project, snapshot, target,
                                                   override=override, index=index)
                report["remapped"] += remapped
                report["dropped_sewings"] += dropped
        report["removed"] = _drop_stale_outputs(project, generator, keep)
        return report
    except Exception as error:
        console.error(f"generator '{generator.name}': rebuild failed: {error}")
        return {"error": str(error)}
    finally:
        generator.applying = False


def _clamped_values(generator) -> dict:
    """Parameter values inside their schema range, written back to the panel.

    The write-back keeps the UI field in step with what was actually used, and
    runs with the rebuild suppressed because it happens inside a rebuild.
    """
    values = generator.values()
    clamped = component.clamp_to_schema(generator.component_id, values)
    if clamped != values:
        generator.suppress_rebuild = True
        try:
            generator.set_values(clamped)
        finally:
            generator.suppress_rebuild = False
    return clamped


def _too_close_vertices(pattern) -> str | None:
    """Whether two of a panel's vertices are closer than the mesh tolerance.

    The mesh stage de-duplicates boundary points within ``granularity * 0.02``,
    so a panel carrying vertices closer than that can become a zero-area sliver
    the sampler cannot walk. Reported instead of meshed.
    """
    if len(pattern.vertices) < 2:
        return None
    # Deliberate Python loop: one read per vertex object on a Blender collection.
    points = np.array([tuple(vertex.co) for vertex in pattern.vertices], dtype=np.float64)
    differences = points[:, None, :] - points[None, :, :]
    distances = np.sqrt((differences ** 2).sum(axis=2))
    np.fill_diagonal(distances, np.inf)
    closest = float(distances.min())
    limit = max(float(pattern.granularity) * 0.02, 1e-6)
    if closest < limit:
        return (f"two vertices are {closest:.3f} mm apart, "
                f"below the {limit:.3f} mm mesh tolerance")
    return None


def _run_hook(generator, written) -> tuple[dict | None, object | None]:
    """Let the component correct the rebuild, if it provides a hook.

    Returns ``(edge map or None, state)`` where the state is ``None`` when there
    is no hook, ``hooks.HANDLED`` when the component fixed the sewings itself,
    and the edge map (also returned first) when the component supplied one.
    """
    module = registry.get(generator.component_id)
    hook = getattr(module, "on_edges_rebuilt", None)
    if hook is None:
        return None, None
    old_edges, new_edges = [], []
    # Deliberate Python loop: one reference object per edge, built from the
    # snapshot and from the panels that were just written.
    for pattern, snapshot in written:
        for index, (uuid, name, points) in enumerate(snapshot):
            old_edges.append(hooks.EdgeRef(pattern.name, index, uuid, name or "", points))
        for index, edge in enumerate(pattern.edges):
            new_edges.append(hooks.EdgeRef(pattern.name, index, edge.global_uuid,
                                           edge.name or "",
                                           np.asarray(edge.render_points, dtype=np.float32)))
    context = hooks.RebuildContext(old_edges=old_edges, new_edges=new_edges,
                                   topology_changed=len(old_edges) != len(new_edges))
    result = hook(context)
    if result == hooks.HANDLED:
        return None, hooks.HANDLED
    if isinstance(result, hooks.EdgeMap):
        return result.pairs, result
    return None, None


def _snapshot_outputs(project, generator) -> dict:
    """Every edge of every produced panel (copies included) before a rebuild.

    Keyed by panel uuid: ``[(edge uuid, edge label, sampled points)]``. Taken
    before anything is written so a rebuild can recognise its own edges.
    """
    snapshots = {}
    for pattern in panels_of(project, generator):
        for member in instance_chain(pattern):
            entries = []
            # Deliberate Python loop: one entry per edge object.
            for edge in member.edges:
                points = getattr(edge, "render_points", None)
                entries.append((edge.global_uuid, edge.name,
                                None if points is None else np.asarray(points, dtype=np.float32)))
            snapshots[member.global_uuid] = entries
    return snapshots


def _sewing_index(project) -> dict:
    """``edge uuid -> sewing indexes``, built once per rebuild.

    Rebuilds used to walk every sewing for every panel of the generator; on a
    project with many panels and seams that is the same list scanned over and
    over. One index per rebuild makes the remap proportional to the seams that
    actually touch the rebuilt panels.
    """
    index: dict[int, list[int]] = {}
    # Deliberate Python loop: one index entry per sewing side.
    for sewing in project.sewings:
        for side in sewing.sides:
            index.setdefault(side.line1_uuid, []).append(sewing.get_index())
            index.setdefault(side.line2_uuid, []).append(sewing.get_index())
    return index


def _remap_sewings(project, snapshot, pattern, override: dict | None = None,
                   index: dict | None = None) -> tuple[int, int]:
    """Keep sewings pointing at the right edges of a rebuilt panel.

    Edges that kept their label are matched by label; the rest are matched by
    geometry (the previous edge's samples against the new edges). A sewing whose
    edge has no match is removed, so no invalid sewing state is left behind.
    """
    if not snapshot:
        return 0, 0

    new_edges = list(pattern.edges)
    by_name = {}
    for edge in new_edges:
        if edge.name:
            by_name.setdefault(edge.name, edge)
    new_points = [np.asarray(edge.render_points, dtype=np.float32)
                  for edge in new_edges]

    match = {} if override is None else {uuid: edge_uuid
                                         for uuid, edge_uuid in override.items()}
    # Deliberate Python loop: one match per previous edge, and each candidate is
    # a separate edge object with its own sampled polyline.
    for uuid, name, points in snapshot:
        if override is not None:
            continue
        edge = by_name.get(name) if name else None
        if edge is None and points is not None and points.size:
            edge = _nearest_edge(points, new_edges, new_points)
        # A previous edge that has no counterpart is recorded as unmatched, so
        # the sewings that used it are dropped rather than left pointing at
        # something that no longer exists.
        match[uuid] = None if edge is None else edge.global_uuid

    remapped = 0
    dropped = []
    candidates = (sorted({entry for uuid in match for entry in index.get(uuid, [])})
                  if index is not None else range(len(project.sewings)))
    # Deliberate Python loop: one pass over the sewings that touch this panel.
    for position in candidates:
        sewing = project.sewings[position]
        for side in sewing.sides:
            first = match.get(side.line1_uuid, None)
            second = match.get(side.line2_uuid, None)
            if side.line1_uuid in match and first is None:
                dropped.append(sewing.get_index())
                break
            if side.line2_uuid in match and second is None:
                dropped.append(sewing.get_index())
                break
            changed = False
            if first is not None and first != side.line1_uuid:
                side.line1_uuid = first
                changed = True
            if second is not None and second != side.line2_uuid:
                side.line2_uuid = second
                changed = True
            remapped += 1 if changed else 0

    for index in sorted(set(dropped), reverse=True):
        project.sewings.remove(index)
    if dropped:
        project.refresh_collection_uuid(project.sewings)
        project.selected_sewings.clear()
    return remapped, len(set(dropped))


def _nearest_edge(points: np.ndarray, new_edges: list, new_points: list):
    """The new edge closest to a previous edge's sampled points, or None."""
    probes = points[::max(1, len(points) // 8)]
    best = None
    best_distance = float("inf")
    # Deliberate Python loop: one distance per candidate edge; the work inside
    # each candidate is a numpy distance matrix.
    for edge, candidate in zip(new_edges, new_points):
        if candidate is None or candidate.size == 0:
            continue
        delta = probes[:, None, :] - candidate[None, :, :]
        distance = float(np.sqrt((delta ** 2).sum(axis=2)).min())
        if distance < best_distance:
            best_distance = distance
            best = edge
    return best


def panels_of(project, generator) -> list:
    """The panels this generator currently owns, in slot order."""
    patterns = []
    live = _live_patterns(project)
    for output in generator.outputs:
        pattern = live.get(output.pattern_uuid)
        if pattern is not None:
            patterns.append(pattern)
    return patterns


def _live_patterns(project) -> dict:
    """Panels by uuid, with every uuid assigned before it is used."""
    live = {}
    for pattern in project.patterns:
        pattern.get_temp_data()
        live[pattern.global_uuid] = pattern
    return live


def detach_generator(project, generator) -> list:
    """Turn a generator's panels into ordinary panels and drop the generator."""
    patterns = panels_of(project, generator)
    for pattern in patterns:
        pattern.generator_uuid = -1
    _remove_generator(project, generator)
    return patterns


def delete_group(project, generator) -> None:
    """Remove a generator together with every panel it produced."""
    patterns = panels_of(project, generator)
    if patterns:
        project.remove_patterns(patterns, expand_groups=False)
    _remove_generator(project, generator)


def _remove_generator(project, generator) -> None:
    index = generator.get_index()
    if index is None or index < 0 or index >= len(project.generators):
        return
    project.generators.remove(index)
    refresh_generators(project)
    project.active_generator_index = max(0, min(project.active_generator_index,
                                                len(project.generators) - 1))


def _ensure_output(project, generator, slot: str):
    """The panel for a slot, created if the generator does not have one yet."""
    live = _live_patterns(project)
    output = generator.output_for(slot)
    if output is not None:
        pattern = live.get(output.pattern_uuid)
        if pattern is not None:
            return pattern, False

    pattern = project.add_pattern()
    pattern.name = slot
    pattern.get_temp_data()
    pattern.generator_uuid = generator.global_uuid
    generator.set_output(slot, pattern.global_uuid)
    return pattern, True


def _drop_stale_outputs(project, generator, keep: list[str]) -> int:
    """Remove panels whose slot the component stopped producing."""
    removed = 0
    live = _live_patterns(project)
    for index in reversed(range(len(generator.outputs))):
        output = generator.outputs[index]
        if output.slot in keep:
            continue
        pattern = live.get(output.pattern_uuid)
        if pattern is not None:
            project.remove_patterns(instance_chain(pattern), expand_groups=False)
            removed += 1
        generator.outputs.remove(index)
    return removed


def _edge_kind(edge) -> str:
    if len(edge.spline_points) > 0:
        return "spline"
    if edge.handle1_type == "VECTOR" and edge.handle2_type == "VECTOR":
        return "straight"
    return "bezier"


def _pattern_topology(pattern) -> tuple:
    """The structure an in-place rewrite has to match."""
    return (
        len(pattern.vertices),
        tuple((edge.vertex_index[0], edge.vertex_index[1], _edge_kind(edge))
              for edge in pattern.edges),
    )


def _write_pattern(pattern, landed: LandedPanel, in_place: bool) -> None:
    """Write a landed panel into a pattern, then rebuild its outline state."""
    if not in_place:
        while len(pattern.edges) > 0:
            pattern.edges.remove(len(pattern.edges) - 1)
        while len(pattern.vertices) > 0:
            pattern.vertices.remove(len(pattern.vertices) - 1)
    _write_vertices(pattern, landed)
    _write_edges(pattern, landed)
    pattern.recreate_sections()
    pattern.forced_update()


def _write_vertices(pattern, landed: LandedPanel) -> None:
    while len(pattern.vertices) > len(landed.vertices):
        pattern.vertices.remove(len(pattern.vertices) - 1)
    for index, point in enumerate(landed.vertices):
        if index < len(pattern.vertices):
            vertex = pattern.vertices[index]
        else:
            vertex = pattern.vertices.add()
        vertex.pattern = pattern
        vertex.co = Vector((float(point[0]), float(point[1])))


def _write_edges(pattern, landed: LandedPanel) -> None:
    while len(pattern.edges) > len(landed.edges):
        pattern.edges.remove(len(pattern.edges) - 1)
    for index, spec in enumerate(landed.edges):
        if index < len(pattern.edges):
            edge = pattern.edges[index]
            edge.vertex_index[0] = spec.v0
            edge.vertex_index[1] = spec.v1
            while len(edge.spline_points) > 0:
                edge.spline_points.remove(len(edge.spline_points) - 1)
        else:
            edge = pattern.add_edge(spec.v0, spec.v1, update=False)
        edge.pattern = pattern
        if spec.kind == "bezier":
            edge.handle1.co = Vector((float(spec.points[1][0]), float(spec.points[1][1])))
            edge.handle2.co = Vector((float(spec.points[2][0]), float(spec.points[2][1])))
            edge.handle1_type = "FREE"
            edge.handle2_type = "FREE"
        else:
            edge.handle1.co = Vector((0.0, 0.0))
            edge.handle2.co = Vector((0.0, 0.0))
            edge.handle1_type = "VECTOR"
            edge.handle2_type = "VECTOR"
        edge.name = spec.name
        edge.need_update_points = True
    pattern.refresh_collection_uuid(pattern.edges)
