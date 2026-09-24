"""Check the pattern-outline validity state machine on a real scene.

    blender.exe -b --factory-startup <scene.blend> --python tools/probe_pattern_validity.py

Read-only for the file: it works on the loaded scene and never saves.

What it measures:

1. the outline test itself, on a bowtie, a square and a two-point "loop";
2. per pattern of the scene: the cached state and the cost of the check, so
   "checked on every mesh generation" is a number and not a guess;
3. the state machine: an edit marks the pattern unknown, the next consumer
   checks it once, and a second consumer reuses the cached answer;
4. the Check Self-Intersection switch: with it on an interactive edit that
   crosses is refused, with it off the edit passes and the next consumer still
   finds the crossing;
5. what an invalid outline does downstream: no mesh is generated for it, and a
   simulation start is refused before the engine is touched at all.
6. that a script or a generator that changes the outline needs no check code of
   its own: the shape change is marked by the same refresh the model already
   runs, and the test happens at the two consumers.
"""

import importlib.util
import os
import sys
import time

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")


def log(message):
    print(f"[validity] {message}", flush=True)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BOWTIE = np.array(((0.0, 0.0), (2.0, 2.0), (2.0, 0.0), (0.0, 2.0)), dtype=np.float32)
SQUARE = np.array(((0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)), dtype=np.float32)


def check_test_shapes(boundary_self_intersection):
    log("--- the outline test")
    for name, points, expected in (
            ("bowtie", BOWTIE, True),
            ("square", SQUARE, False),
            ("two points", SQUARE[:2], True)):
        intersected, crossing = boundary_self_intersection(points)
        detail = "crossing at (%s)" % ", ".join(f"{value:.4f}" for value in crossing) \
            if crossing is not None else "no crossing point"
        status = "ok" if intersected == expected else "UNEXPECTED"
        log(f"    {name:<10} intersected={intersected!s:<5} {detail}  [{status}]")
    # The bowtie crosses at (1, 1); a wrong index/weight mapping shows up here.
    _intersected, crossing = boundary_self_intersection(BOWTIE)
    if crossing is None or abs(crossing[0] - 1.0) > 1e-4 or abs(crossing[1] - 1.0) > 1e-4:
        log(f"    crossing point is {crossing}, expected (1.0, 1.0)")
    return not (crossing is not None and abs(crossing[0] - 1.0) < 1e-4
                and abs(crossing[1] - 1.0) < 1e-4)


def check_scene_patterns(project):
    log("--- per pattern")
    failures = 0
    for index, pattern in enumerate(project.patterns):
        points = pattern.get_boundary_points()
        size = 0 if points is None else len(points)
        start = time.time()
        state = pattern.validate(force=True)
        first = (time.time() - start) * 1000.0
        start = time.time()
        cached = pattern.validate()
        second = (time.time() - start) * 1000.0
        log(f"    pattern[{index}] {pattern.name or '(unnamed)':<20} points={size:<6} "
            f"state={state:<7} check={first:.2f} ms cached={second:.4f} ms")
        if cached != state:
            log("        cached answer differs from the fresh one")
            failures += 1
    return failures


def check_state_machine(pattern):
    log("--- state machine")
    failures = 0
    pattern.mark_shape_changed()
    unknown = pattern.validity_state
    before = pattern.validate(force=True)
    after_edit = pattern.validity_state
    pattern.mark_geometry_changed()
    marked = pattern.validity_state
    pattern.validate()
    checked = pattern.validity_state
    log(f"    mark_shape_changed -> {unknown}, checked -> {before}, "
        f"after an edit -> {after_edit} -> mark_geometry_changed -> {marked} -> validate -> {checked}")
    if unknown != "UNKNOWN" or marked != "UNKNOWN":
        log("        an edit did not mark the outline unknown")
        failures += 1
    if after_edit not in ("VALID", "INVALID") or checked != after_edit:
        log("        re-checking after an edit did not reproduce the state")
        failures += 1
    return failures


def check_global_switch(scene, interactive_edit_allowed):
    log("--- Check Self-Intersection")
    failures = 0
    scene.qmyi.interactive_self_intersection_check = True
    checked = not interactive_edit_allowed(bpy.context, BOWTIE)
    scene.qmyi.interactive_self_intersection_check = False
    allowed = interactive_edit_allowed(bpy.context, BOWTIE)
    scene.qmyi.interactive_self_intersection_check = True
    log(f"    check on: bowtie refused={checked}; check off: bowtie allowed={allowed}")
    if not checked or not allowed:
        log("        the switch did not gate the interactive check")
        failures += 1
    return failures


def make_pattern(project, corners, mesh=True):
    """A pattern built through the model API, optionally meshed."""
    pattern = project.add_pattern()
    for co in corners:
        pattern.add_vertex((float(co[0]), float(co[1])))
    for index in range(len(corners)):
        pattern.add_edge(index, (index + 1) % len(corners), update=False)
    pattern.granularity = 20.0
    pattern.ensure_edge_ccw()
    if mesh:
        pattern.generate_mesh()
    return pattern


def reshape(pattern, corners):
    """Move the pattern's control vertices, no operator involved."""
    for vertex, co in zip(pattern.vertices, corners):
        vertex.co[0] = float(co[0])
        vertex.co[1] = float(co[1])
    pattern.mark_geometry_changed()


def check_simulation_gate(manager, project):
    log("--- simulation gate")
    failures = 0
    before = manager.simulated_patterns()
    log(f"    patterns a start would send: {[p.name or '(unnamed)' for p in before]}")

    # The realistic case: a panel that has a mesh, then gets dragged into a
    # crossing. Its mesh object still names the pattern, so a start that only
    # looked at meshes would happily hand the engine the stale one.
    target = make_pattern(project, SQUARE)
    try:
        reshape(target, BOWTIE)
        simulated = manager.simulated_patterns()
        meshed = target in simulated
        log(f"    crossed pattern meshed={meshed} state={target.validity_state} "
            f"invalid={[p.name for p in manager.invalid_simulated_patterns()]}")
        if not meshed:
            log("        the crossed pattern is not part of the simulation input")
            failures += 1

        target.mark_shape_changed()  # the gate must not depend on the cache
        refused = manager.start_simulation()
        untouched = manager.simulator is None and not manager.running
        log(f"    with the crossed pattern: start_simulation returned {refused}, "
            f"engine untouched={untouched}")
        if refused or not untouched:
            log("        an invalid pattern did not stop the start")
            failures += 1
    finally:
        project.remove_patterns([target])
    log(f"    after removing it: invalid={[p.name for p in manager.invalid_simulated_patterns()]}")
    return failures


def check_real_pattern(project):
    """Build a bowtie through the model API and let the state machine see it."""
    log("--- a real pattern object")
    failures = 0
    pattern = make_pattern(project, BOWTIE)
    try:
        state = pattern.validate(force=True)
        crossing = pattern.invalid_point
        drawn = "red" if pattern.is_invalid else "normal"
        pattern.generate_mesh()
        meshed = pattern.mesh_object is not None
        log(f"    bowtie pattern: state={state} crossing={crossing} drawn={drawn} "
            f"mesh generated={meshed}")
        if state != "INVALID" or crossing is None:
            log("        a crossing outline was not detected")
            failures += 1
        elif abs(crossing[0] - 1.0) > 1e-3 or abs(crossing[1] - 1.0) > 1e-3:
            log(f"        crossing {crossing} is not the bowtie centre (1.0, 1.0)")
            failures += 1
        if meshed:
            log("        a mesh was generated for a crossing outline")
            failures += 1

        # Straighten it into a simple quad: the next consumer must agree.
        reshape(pattern, SQUARE)
        unknown = pattern.validity_state
        state = pattern.validate()
        pattern.generate_mesh()
        square_faces = len(pattern.mesh_object.data.polygons) if pattern.mesh_object else 0
        log(f"    after the fix: edit left it {unknown} -> {state}, "
            f"is_invalid={pattern.is_invalid}, mesh faces={square_faces}")
        if state != "VALID" or pattern.is_invalid or square_faces == 0:
            log("        a fixed outline is still reported as crossing")
            failures += 1
    finally:
        project.remove_patterns([pattern])
    log(f"    patterns left in the project: {len(project.patterns)}")
    return failures


def mesh_signature(pattern):
    """Enough of a pattern mesh to tell whether it was rebuilt."""
    mesh = pattern.mesh_object.data if pattern.mesh_object is not None else None
    if mesh is None:
        return None
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    return (len(mesh.vertices), round(float(co.sum()), 6))


def check_code_path(project):
    """A generator or a script does not have to test anything itself."""
    log("--- a code path that changes the outline")
    failures = 0
    pattern = make_pattern(project, SQUARE)
    try:
        before = mesh_signature(pattern)

        # What an importer or a generator does: move the vertices, then refresh
        # the pattern the way every existing path does.
        reshape(pattern, BOWTIE)
        marked = pattern.validity_state
        pattern.generate_mesh()
        after = mesh_signature(pattern)
        log(f"    script edit + refresh: marked {marked}, state {pattern.validate()}, "
            f"mesh {before} -> {after}")
        if marked != "UNKNOWN" or pattern.validate() != "INVALID" or after != before:
            log("        the script edit was not caught, or the mesh was rebuilt anyway")
            failures += 1

        # Sound again, but a different size, so a rebuilt mesh is visible.
        bigger = ((0.0, 0.0), (3.0, 0.0), (3.0, 3.0), (0.0, 3.0))
        reshape(pattern, bigger)
        pattern.generate_mesh()
        fixed = mesh_signature(pattern)
        log(f"    fixing it the same way: state {pattern.validate()}, mesh {after} -> {fixed}")
        if pattern.validate() != "VALID" or fixed == after:
            log("        the mesh was not rebuilt once the outline was sound again")
            failures += 1

        # A path that changes the vertices but never refreshes changes neither
        # the geometry the check sees nor the mesh, so the two stay consistent.
        for vertex, co in zip(pattern.vertices, BOWTIE):
            vertex.co[0] = float(co[0])
            vertex.co[1] = float(co[1])
        pattern.generate_mesh()
        unrefreshed = mesh_signature(pattern)
        log(f"    edit without refresh: state {pattern.validate()}, mesh {fixed} -> {unrefreshed}")
        if unrefreshed != fixed:
            log("        a stale edit reached the mesh")
            failures += 1
    finally:
        project.remove_patterns([pattern])
    return failures


def main():
    import_addon(ADDON_PATH, "qmyi")
    from qmyi import global_data
    from qmyi import model
    from qmyi.model import model_data
    from qmyi.model.pattern import boundary_self_intersection, interactive_edit_allowed
    from qmyi.simulation.simulation_manager import simulation_manager
    from qmyi.utilities.node_tree import get_all_node_tree

    global_data.renderers_enabled = False
    model.register()
    model_data.refresh_all_uuids()

    projects = get_all_node_tree()
    if not projects:
        log("no project in this scene")
        return 1
    project = projects[0]
    log(f"scene={bpy.context.scene.name} objects={len(bpy.data.objects)} "
        f"patterns={len(project.patterns)} background={bpy.app.background}")

    failures = check_test_shapes(boundary_self_intersection)
    failures += check_scene_patterns(project)
    if len(project.patterns) == 0:
        log("no pattern to exercise the state machine")
        return failures
    failures += check_state_machine(project.patterns[0])
    failures += check_global_switch(bpy.context.scene, interactive_edit_allowed)
    failures += check_simulation_gate(simulation_manager, project)
    failures += check_real_pattern(project)
    failures += check_code_path(project)

    log(f"done, {failures} unexpected result(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
