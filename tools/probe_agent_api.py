"""Exercise the qyapi script surface in a background Blender session.

    blender.exe -b --factory-startup --python tools/probe_agent_api.py [-- --scene <file.blend>]

Registers the add-on first, then builds its own fixture through
``tools/make_probe_scene.build_fixture`` - a maintainer ``.blend`` is never the
default, because those files live in the gitignored ``extracted_files/`` tree
and carry whatever version they were saved with. With ``--scene`` it opens that
file instead (the node-tree type has to be registered when the file loads). It
walks the surface the way a client would:
import, help, state, prepare, step, read, reset, the live path, the error paths
and the undo granularity. It runs a short simulation (a few substeps) and prints
the results it got.

Exit code 0 means every check passed.
"""

import argparse
import importlib.util
import json
import os
import sys
import traceback

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")

results = {"ok": 0, "failed": 0}


def log(message):
    print(f"[api] {message}", flush=True)


def check(label, call):
    try:
        value = call()
    except Exception as error:
        results["failed"] += 1
        log(f"{label}: FAIL -> {error!r}")
        traceback.print_exc()
        return None
    results["ok"] += 1
    log(f"{label}: OK -> {value}")
    return value


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default=None,
                        help="explicit .blend for a one-off run; omit to build the fixture in-process")
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--blank", action="store_true",
                        help="start from an empty session: projects and the crossing policy")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    qmyi = import_addon(ADDON_PATH, "qmyi")
    from qmyi import global_data

    global_data.renderers_enabled = False
    qmyi.register()
    import qyapi

    if args.blank:
        log("blank session; no scene file")
        check("projects.list() on an empty scene", lambda: qyapi.projects.list())
        check("a panel call before any project", lambda: _no_project(qyapi))
        check("projects.create()", lambda: _project_create(qyapi))
        check("a panel works straight after a create", lambda: _panel_after_create(qyapi))
        check("projects.rename()", lambda: _project_rename(qyapi))
        check("a second project takes the work", lambda: _second_project(qyapi))
        check("projects.activate() switches back", lambda: _project_activate(qyapi))
        check("projects.remove()", lambda: _project_remove(qyapi))
        check("allow_crossing keeps an outline that crosses",
              lambda: _crossing_allowed(qyapi))
        check("the flag does not leak into the next call", lambda: _crossing_leak(qyapi))
        check("the interactive switch is untouched", lambda: _switch_untouched(qyapi))
        check("a generator rebuild is not gated by the flag",
              lambda: _rebuild_policy(qyapi))
        check("fixing the outline rebuilds the mesh", lambda: _crossing_fixed(qyapi))

        log(f"checks: {results['ok']} ok, {results['failed']} failed")
        return 0 if results["failed"] == 0 else 3

    if args.scene:
        log(f"add-on registered; opening {os.path.basename(args.scene)}")
        bpy.ops.wm.open_mainfile(filepath=args.scene)
    else:
        sys.path.insert(0, os.path.join(REPO, "tools"))
        import make_probe_scene

        log("add-on registered; building the fixture in-process (no scene file)")
        make_probe_scene.build_fixture()

    # 1. The surface is reachable under one stable name.
    check("import qyapi", lambda: f"{qyapi.__name__} v{qyapi.VERSION}")
    check("qyapi is the add-on module",
          lambda: sys.modules["qyapi"] is sys.modules["qmyi.qyapi"])
    check("import qyapi.sim reaches the same module",
          lambda: __import__("qyapi.sim", fromlist=["x"]) is sys.modules["qmyi.qyapi.sim"])
    check("qyapi.errors carries the same error class",
          lambda: __import__("qyapi.errors", fromlist=["x"]).QyapiError is qyapi.QyapiError)
    check("surface docstring documents the entry points",
          lambda: all(name in (qyapi.__doc__ or "")
                      for name in ("state()", "prepare(", "step(", "reset()")))

    # 2. Discovery.
    check("help()", lambda: f"{qyapi.help().count(chr(10))} lines")
    check("help() lists every entry point",
          lambda: [name for name, _purpose, _args in qyapi._ENTRY_POINTS
                   if name.split("(")[0] not in qyapi.help()])
    for topic in ("objects", "units", "undo", "not-offered"):
        check(f'help("{topic}")', lambda topic=topic: f"{len(qyapi.help(topic))} chars")
    check("help(unknown) raises",
          lambda: isinstance(_raise(lambda: qyapi.help("nope")), qyapi.QyapiError))

    before = snapshot_identity()
    state = check("state()", lambda: _state_summary(qyapi))
    check("state() is JSON-safe", lambda: f"{len(json.dumps(qyapi.state()))} bytes")
    check("state() did not change the scene", lambda: snapshot_identity() == before)
    check("state() reports the simulation", lambda: state["simulation"]["mode"])

    # 3. Error contract.
    error = _raise(lambda: qyapi.sim.step(1))
    check("step() before prepare refuses",
          lambda: (type(error).__name__, str(error), list(error.details)))
    error = _raise(lambda: qyapi.sim.read("no-such-pattern"))
    check("read(unknown pattern) refuses", lambda: (str(error), list(error.details)))

    # 4. Undo granularity, counted rather than observed (a background session has
    # no undo stack to observe).
    pushes = _count_pushes(qyapi)
    before_push = pushes["count"]
    qyapi.state()
    qyapi.help()
    qyapi.sim.status()
    qyapi.sim.read()
    check("read calls push no undo step", lambda: pushes["count"] - before_push)
    before_push = pushes["count"]
    with qyapi.transaction("probe batch"):
        qyapi.end_write("inner")
        inside = pushes["count"] - before_push
    check("a transaction collapses its writes",
          lambda: {"inside": inside, "after": pushes["count"] - before_push})

    # 5. Preparation.
    before_push = pushes["count"]
    summary = check("sim.prepare()", lambda: qyapi.sim.prepare())
    check("one write call pushes one undo step",
          lambda: {"pushes": pushes["count"] - before_push,
                   "undo_step": summary["undo_step"]})
    second = check("sim.prepare() again", lambda: qyapi.sim.prepare())
    check("prepare() is repeatable",
          lambda: all(second[key] == summary[key] for key in
                      ("solver", "objects", "vertices", "stitches", "step_h_s")))
    check("status() after prepare", lambda: qyapi.sim.status())

    # 6. Caller parameters win over the panel.
    caller = check("sim.prepare(solver=Explicit, parameters={...})",
                   lambda: qyapi.sim.prepare(solver="Explicit",
                                             parameters={"step_h": 0.003,
                                                         "gravity": -9.8}))
    check("caller parameters are the ones in effect",
          lambda: {key: caller[key] for key in
                   ("solver", "solver_source", "parameters_source",
                    "parameter_count", "step_h_s")})
    check("bad solver name is refused",
          lambda: str(_raise(lambda: qyapi.sim.prepare(solver="NoSuchSolver"))))
    check("prepare() back to the scene block", lambda: qyapi.sim.prepare() is not None)

    # 7. Stepping.
    metrics = check("sim.step(10)", lambda: qyapi.sim.step(args.frames))
    check("step() metrics", lambda: {key: metrics[key] for key in
                                     ("substeps", "frames", "wall_time_s",
                                      "substeps_per_second", "step_h_s", "mode")})
    check("step() passes the engine residuals through",
          lambda: metrics["engine_statistics"].get("residuals"))
    again = check("sim.step(10) again", lambda: qyapi.sim.step(args.frames))
    check("frame count advanced by the requested substeps",
          lambda: (again["frames"] == metrics["frames"] + args.frames, again["frames"]))
    check("engine statistics are omitted when the engine has none",
          lambda: qyapi.sim._engine_statistics(_NoStatisticsEngine()))

    # 8. Reading back.
    positions = check("sim.read()", lambda: _read_summary(qyapi))
    check("read() geometry", lambda: [
        (entry["name"], entry["vertices"], entry["non_finite"])
        for entry in positions["objects"]])
    check("read() moved nothing", lambda: _read_is_pure(qyapi))
    check("a non-finite vertex is counted, not raised", lambda: _non_finite_check(qyapi))

    # 9. Reset.
    reset = check("sim.reset()", lambda: qyapi.sim.reset())
    check("reset() put every object back on its rest pose",
          lambda: {"objects": reset["objects"], "mode": reset["mode"],
                   "not_rest": _rest_pose_unequal()})
    check("status() after reset", lambda: qyapi.sim.status())
    check("step() after reset refuses", lambda: str(_raise(lambda: qyapi.sim.step(1))))

    # 10. The live path, and the mutual exclusion.
    check("sim.start() in a background session", lambda: _start_stop(qyapi))
    check("step() during a live run is refused",
          lambda: _step_during_live(qyapi, args.frames))
    check("start() during a stepping session is refused",
          lambda: _start_during_stepping(qyapi))

    # 11. The panel toggles run through the same entry points.
    check("the free-simulation toggle drives the surface", lambda: _toggle_check(qyapi))

    # 12. An engine failure reaches the caller and leaves the stepping mode.
    check("an engine failure is reported", lambda: _induced_failure(qyapi))

    # 13. A crossing outline is refused before the engine is touched.
    check("crossing outline is refused", lambda: _refusal_check(qyapi))

    # 14. The shipped reference file and the text index agree.
    check("docs/agent-api.md lists every entry point", lambda: _doc_agrees(qyapi))

    # 15. The component library, without a scene in the way.
    check("components.list()", lambda: _component_list(qyapi))
    check("components.build() leaves the scene alone", lambda: _component_build(qyapi))
    check("components: unknown id and unknown parameter are refused",
          lambda: _component_refusals(qyapi))

    # 16. A generator, a collar and a seam between them.
    check("generators.create()", lambda: _generator_create(qyapi))
    check("patterns.get() reports the edges and the sewings",
          lambda: _panel_read(qyapi))
    check("patterns.create()", lambda: _panel_create(qyapi))
    check("a taken name is suffixed", lambda: _name_suffix(qyapi))
    check("sewings.sew() forwards the flags", lambda: _sew_checks(qyapi))
    check("sewings.of() agrees with sewings.list()", lambda: _sewing_agreement(qyapi))
    check("generators.set_params() keeps the seam and reports the simulation",
          lambda: _set_params(qyapi))
    check("the new shape settles with a few frames", lambda: _settle(qyapi))
    check("patterns.add_internal_line() / remove_internal_line()",
          lambda: _internal_line_check(qyapi))
    check("patterns.fabrics() / assign_fabric()", lambda: _fabric_check(qyapi))
    check("sewings.set_color() / remove()", lambda: _sewing_edit_check(qyapi))
    check("generators.detach() keeps the panels", lambda: _detach_check(qyapi))
    check("pattern edits", lambda: _panel_edits(qyapi))
    check("a crossing handle change is refused and put back",
          lambda: _handle_refusal(qyapi))
    check("patterns.copy() chains a copy", lambda: _panel_copy(qyapi))
    check("a generated panel is refused by patterns.remove()",
          lambda: _remove_refusal(qyapi))
    check("patterns.validate() and clean up", lambda: _panel_cleanup(qyapi))

    log(f"checks: {results['ok']} ok, {results['failed']} failed")
    return 0 if results["failed"] == 0 else 3


def _raise(call):
    try:
        call()
    except Exception as error:
        return error
    return None


def snapshot_identity():
    """What a read is not allowed to change: counts and the pattern fabric links."""
    groups = [group for group in bpy.data.node_groups
              if group.bl_idname == "QianyiNodeTree"]
    return {
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "groups": len(groups),
        "patterns": sum(len(group.patterns) for group in groups),
        "fabric_links": sorted(pattern.fabric_uuid
                               for group in groups for pattern in group.patterns),
    }


def _state_summary(qyapi):
    """state() without the raw positions: the probe prints what it checks."""
    snapshot = qyapi.state()
    return {
        "active_project": snapshot["active_project"],
        "scene": snapshot["scene"]["name"],
        "projects": [(project["name"], project["pattern_count"],
                      [(pattern["name"], pattern["granularity_mm"],
                        pattern["outline_validity"]) for pattern in project["patterns"]])
                     for project in snapshot["projects"]],
        "simulation": snapshot["simulation"],
    }


def _count_pushes(qyapi):
    """Wrap push_undo so the probe can count undo steps instead of observing them."""
    real = qyapi.push_undo
    counter = {"count": 0}

    def counting(message):
        counter["count"] += 1
        return real(message)

    qyapi.push_undo = counting
    return counter


def _read_summary(qyapi):
    """Call read() but report a summary: the positions themselves are megabytes."""
    positions = qyapi.sim.read()
    summaries = []
    for entry in positions["objects"]:
        world = np.asarray(entry["world"])
        summaries.append({
            "name": entry["name"],
            "vertices": entry["vertex_count"],
            "non_finite": entry["non_finite"],
            "world_min": [round(value, 4) for value in world.min(axis=0)],
            "world_max": [round(value, 4) for value in world.max(axis=0)],
        })
    return {"objects": summaries}


def _read_is_pure(qyapi):
    """Reading must not move a vertex: compare the shape keys around a read."""
    before = {}
    for obj in _pattern_objects():
        vertices = obj.qmyi_simulation_props.get_simulation_vertices()
        if vertices is not None:
            before[obj.name] = np.array(vertices, copy=True)
    qyapi.sim.read()
    moved = []
    for obj in _pattern_objects():
        if obj.name not in before:
            continue
        vertices = obj.qmyi_simulation_props.get_simulation_vertices()
        if vertices is None or not np.array_equal(before[obj.name], vertices):
            moved.append(obj.name)
    return {"objects_compared": len(before), "moved": moved}


def _non_finite_check(qyapi):
    """One bad coordinate must come back as a count, not as an exception."""
    obj = _pattern_objects()[0]
    props = obj.qmyi_simulation_props
    key = obj.data.shape_keys.key_blocks[props.simulation_key_name]
    count = len(obj.data.vertices) * 3
    coords = np.empty(count, dtype=np.float32)
    key.data.foreach_get("co", coords)
    original = float(coords[0])
    coords[0] = float("nan")
    key.data.foreach_set("co", coords)
    try:
        report = qyapi.sim.read([props.pattern.name])
    finally:
        coords[0] = original
        key.data.foreach_set("co", coords)
    return {"objects": [(entry["name"], entry["non_finite"])
                        for entry in report["objects"]]}


def _rest_pose_unequal():
    """Objects whose simulated shape key is still away from its rest key."""
    unequal = []
    for obj in _pattern_objects():
        keys = obj.data.shape_keys.key_blocks
        count = len(obj.data.vertices) * 3
        simulated = np.empty(count, dtype=np.float32)
        rest = np.empty(count, dtype=np.float32)
        keys["QYSim"].data.foreach_get("co", simulated)
        keys["QYBasis"].data.foreach_get("co", rest)
        if not np.array_equal(simulated, rest):
            unequal.append(obj.name)
    return unequal


def _pattern_objects():
    objects = []
    for obj in bpy.data.objects:
        props = getattr(obj, "qmyi_simulation_props", None)
        if props is not None and props.is_pattern_mesh:
            objects.append(obj)
    return objects


def _start_stop(qyapi):
    """The live run needs a window; a background session must not crash."""
    started = _raise(lambda: qyapi.sim.start())
    live = qyapi.sim.status()
    stopped = _raise(lambda: qyapi.sim.stop())
    return {"start_error": None if started is None else str(started),
            "live_reported": live["mode"] == qyapi.sim.MODE_LIVE,
            "stop_error": None if stopped is None else str(stopped),
            "mode_after_stop": qyapi.sim.status()["mode"]}


def _step_during_live(qyapi, frames):
    qyapi.sim.start()
    error = _raise(lambda: qyapi.sim.step(frames))
    after = qyapi.sim.status()
    qyapi.sim.stop()
    return {"refused": isinstance(error, qyapi.QyapiError),
            "message": str(error), "still_live": after["live_running"]}


def _start_during_stepping(qyapi):
    """The stepping mode is transient, so set it the way a nested call would."""
    import qyapi.sim as sim_module

    previous = sim_module._session.mode
    sim_module._session.mode = sim_module.MODE_STEPPING
    try:
        error = _raise(lambda: qyapi.sim.start())
    finally:
        sim_module._session.mode = previous
    return {"refused": isinstance(error, qyapi.QyapiError), "message": str(error)}


def _toggle_check(qyapi):
    """The scene toggle has to go through the surface, or status() would lie."""
    simulation = bpy.context.scene.qmyi.simulation
    simulation.enable_free_simulation = True
    started = qyapi.sim.status()
    simulation.enable_free_simulation = False
    stopped = qyapi.sim.status()
    return {"on": started["mode"], "off": stopped["mode"],
            "toggle_value": simulation.enable_free_simulation}


def _induced_failure(qyapi):
    """An engine exception must reach the caller and leave the stepping mode."""
    import qyapi.sim as sim_module

    qyapi.sim.prepare()
    real = sim_module._substep

    def failing(manager, engine, step_h):
        raise RuntimeError("induced failure")

    sim_module._substep = failing
    try:
        error = _raise(lambda: qyapi.sim.step(2))
        after = qyapi.sim.status()
    finally:
        sim_module._substep = real
    return {"error_type": type(error).__name__, "message": str(error),
            "details": list(getattr(error, "details", ())),
            "mode": after["mode"], "prepared": after["prepared"],
            "last_error": after["last_error"]}


def _refusal_check(qyapi):
    """Drag a meshed panel into a crossing and ask the surface to prepare.

    The square is meshed while it is valid, then its outline is reshaped into a
    bowtie without regenerating the mesh - the case where a stale mesh would
    otherwise reach the engine.
    """
    from qmyi.utilities.node_tree import get_all_node_tree

    qyapi.sim.reset()
    project = get_all_node_tree()[0]
    square = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    bowtie = ((0.0, 0.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0))
    pattern = project.add_pattern()
    for co in square:
        pattern.add_vertex(co)
    for index in range(len(square)):
        pattern.add_edge(index, (index + 1) % len(square), update=False)
    pattern.granularity = 20.0
    pattern.ensure_edge_ccw()
    pattern.generate_mesh()
    engine_before = qyapi.sim.simulation_manager.simulator
    try:
        for vertex, co in zip(pattern.vertices, bowtie):
            vertex.co[0] = co[0]
            vertex.co[1] = co[1]
        pattern.mark_geometry_changed()
        error = _raise(lambda: qyapi.sim.prepare())
        return {
            "pattern": pattern.name,
            "refused": isinstance(error, qyapi.QyapiError),
            "message": str(error),
            "details": list(getattr(error, "details", ())),
            "engine_untouched": qyapi.sim.simulation_manager.simulator is engine_before,
            "mode_after": qyapi.sim.status()["mode"],
        }
    finally:
        project.remove_patterns([pattern])


def _doc_agrees(qyapi):
    """Every entry point of the index appears in the shipped reference file."""
    path = os.path.join(REPO, "docs", "agent-api.md")
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    missing = [name.split("(")[0] for name, _purpose, _args in qyapi._ENTRY_POINTS
               if name.split("(")[0] not in text]
    return {"file": os.path.basename(path), "bytes": len(text), "missing": missing}


class _NoStatisticsEngine:
    """An engine object that reports nothing, for the pass-through rule."""


def _no_project(qyapi):
    error = _raise(lambda: qyapi.patterns.create([[0.0, 0.0], [50.0, 0.0], [50.0, 30.0]]))
    return {"refused": isinstance(error, qyapi.QyapiError), "message": str(error),
            "details": list(getattr(error, "details", ()))}


def _project_create(qyapi):
    """A create must leave a project a panel call can use, and the tree alone must not."""
    from qmyi.declarations import Panels

    created = qyapi.projects.create("probe project")
    listing = qyapi.projects.list()
    scene = bpy.context.scene
    plain = bpy.data.node_groups.new("half built", Panels.QianyiNodeTree.value)
    scene.qmyi.active_project_index = [index for index, group
                                       in enumerate(bpy.data.node_groups)
                                       if group == plain][0]
    raw_error = _raise(lambda: qyapi.patterns.create([[0.0, 0.0], [40.0, 0.0],
                                                      [40.0, 20.0]], name="raw"))
    bpy.data.node_groups.remove(plain)
    qyapi.projects.activate("probe project")
    return {"created": {key: created[key] for key in
                        ("name", "datablock", "active", "patterns", "fabrics")},
            "requested_name": created["requested_name"],
            "listing": [(entry["name"], entry["active"]) for entry in listing["projects"]],
            "active": listing["active"],
            "node_tree_alone_error": type(raw_error).__name__}


def _panel_after_create(qyapi):
    made = qyapi.patterns.create([[0.0, 0.0], [100.0, 0.0], [100.0, 80.0], [0.0, 80.0]],
                                 name="probe square", granularity_mm=10.0)
    projects = qyapi.projects.list()
    return {"panel": made["name"], "mesh_vertices": made["mesh_vertices"],
            "fabric": made["fabric"], "validity": made["outline_validity"],
            "mesh_stale": made["mesh_stale"],
            "project_patterns": [entry["patterns"] for entry in projects["projects"]]}


def _project_rename(qyapi):
    renamed = qyapi.projects.rename("probe project", "renamed project")
    listing = qyapi.projects.list()
    old = _raise(lambda: qyapi.projects.activate("probe project"))
    taken = _raise(lambda: qyapi.projects.rename("renamed project",
                                                 "renamed project"))
    return {"renamed": renamed["name"], "active": renamed["active"],
            "names": [entry["name"] for entry in listing["projects"]],
            "old_name": str(old)}


def _second_project(qyapi):
    second = qyapi.projects.create("second")
    made = qyapi.patterns.create([[0.0, 0.0], [30.0, 0.0], [30.0, 20.0]],
                                 name="in second")
    first = qyapi.projects.activate("renamed project")
    listing = qyapi.projects.list()
    return {"second": second["name"], "made_in": made["name"],
            "counts": [(entry["name"], entry["patterns"]) for entry in listing["projects"]],
            "active": first["name"],
            "first_project_panels": [panel["name"]
                                     for panel in qyapi.patterns.list()["panels"]]}


def _project_activate(qyapi):
    activated = qyapi.projects.activate("second")
    return {"active": activated["name"],
            "panels": [panel["name"] for panel in qyapi.patterns.list()["panels"]],
            "active_from_list": qyapi.projects.list()["active"]}


def _project_remove(qyapi):
    removed = qyapi.projects.remove("second")
    listing = qyapi.projects.list()
    return {"removed": removed["removed"], "panels": removed["patterns"],
            "projects_left": removed["projects_left"],
            "names": [entry["name"] for entry in listing["projects"]],
            "active": listing["active"]}


def _crossing_allowed(qyapi):
    before = qyapi.patterns.get("probe square")
    crossed = qyapi.patterns.set_point("probe square", 2, [-20.0, 40.0],
                                       allow_crossing=True)
    refusal = str(_raise(lambda: qyapi.sim.prepare()))
    bowtie = qyapi.patterns.create([[0.0, 0.0], [60.0, 60.0], [60.0, 0.0], [0.0, 60.0]],
                                   name="bowtie", allow_crossing=True)
    # A handle edit that only crosses after sampling, with the flag on.
    qyapi.patterns.create([[0.0, 0.0], [80.0, 0.0], [80.0, 60.0]],
                          name="probe triangle", granularity_mm=10.0)
    qyapi.patterns.set_handle("probe triangle", 0, 2, [60.0, 10.0], "FREE")
    handle = qyapi.patterns.set_handle("probe triangle", 0, 1, [20.0, 30.0], "FREE",
                                       allow_crossing=True)
    return {"validity_before": before["outline_validity"],
            "mesh_before": before["mesh_vertices"],
            "validity_after": crossed["outline_validity"],
            "mesh_after": crossed["mesh_vertices"],
            "mesh_stale": crossed["mesh_stale"],
            "crossing": crossed["crossing"],
            "allowed_crossing": crossed.get("allowed_crossing"),
            "simulation_refused": refusal,
            "new_crossing_panel": (bowtie["mesh_object"], bowtie["mesh_stale"]),
            "handle_allowed": (handle["outline_validity"], handle["mesh_stale"],
                               handle.get("allowed_crossing"))}


def _crossing_leak(qyapi):
    # Back to a valid outline, then the same crossing move with the flag off.
    qyapi.patterns.set_point("probe square", 2, [100.0, 80.0])
    error = _raise(lambda: qyapi.patterns.set_point("probe square", 2, [-20.0, 40.0]))
    return {"refused": str(error), "refused_type": type(error).__name__,
            "validity": qyapi.patterns.get("probe square")["outline_validity"]}


def _switch_untouched(qyapi):
    scene = bpy.context.scene
    before = bool(scene.qmyi.interactive_self_intersection_check)
    qyapi.patterns.set_point("probe square", 2, [100.0, 80.0])
    qyapi.patterns.set_point("probe square", 2, [-20.0, 40.0], allow_crossing=True)
    after = bool(scene.qmyi.interactive_self_intersection_check)
    qyapi.patterns.set_point("probe square", 2, [100.0, 80.0])
    return {"switch_before": before, "switch_after": after, "unchanged": before == after}


def _rebuild_policy(qyapi):
    """A parameter change that crosses is applied and named, with no flag."""
    import inspect

    created = qyapi.generators.create("notched_panel",
                                      {"width": 300.0, "height": 100.0, "notch_depth": 10.0},
                                      name="probe bow")
    # A notch deeper than the panel folds past its bottom edge.
    changed = qyapi.generators.set_params("probe bow", {"notch_depth": 200.0})
    report = changed["report"]
    return {"panels": [panel["name"] for panel in created["panels"]],
            "valid_before": created["panels"][0]["outline_validity"],
            "invalid_panels": report.get("invalid_panels"),
            "invalid_panel_names": report.get("invalid_panel_names"),
            "stale_meshes": report.get("stale_meshes"),
            "first_panel_stale": changed["panels"][0]["mesh_stale"],
            "takes_flag": "allow_crossing" in
            inspect.signature(qyapi.generators.set_params).parameters}


def _crossing_fixed(qyapi):
    import inspect

    fixed = qyapi.patterns.set_point("probe square", 2, [100.0, 80.0])
    # The earlier checks left a crossing panel and a crossing generator behind:
    # fix or clear them, then a simulation can start.
    qyapi.patterns.remove("bowtie")
    qyapi.patterns.remove("probe triangle")
    cleaned = qyapi.generators.remove("probe bow")
    validated = qyapi.patterns.validate()
    prepared = qyapi.sim.prepare()
    return {"validity": fixed["outline_validity"], "mesh_stale": fixed["mesh_stale"],
            "mesh_vertices": fixed["mesh_vertices"],
            "validated": [(entry["panel"], entry["valid"])
                          for entry in validated["panels"]],
            "simulation_prepared": prepared["objects"],
            "cleaned": cleaned["removed"],
            "set_point_takes_flag": "allow_crossing" in
            inspect.signature(qyapi.patterns.set_point).parameters}


def _component_list(qyapi):
    entries = qyapi.components.list()["components"]
    sample = next(item for item in entries if item["id"] == "gc_tee_torso")
    described = qyapi.components.info("gc_tee_torso")
    reloaded = qyapi.components.reload()
    return {"count": len(entries),
            "ids": [item["id"] for item in entries],
            "sample_params": sorted(sample["params"]),
            "sample_category": sample["category"],
            "info_matches": described["id"] == sample["id"],
            "reload": (reloaded["loaded"], reloaded["errors"])}


def _component_build(qyapi):
    before = snapshot_identity()
    built = qyapi.components.build("gc_tee_torso", {"bust": 92.0, "shirt_length": 1.3})
    unchanged = snapshot_identity() == before
    return {"unchanged": unchanged,
            "params_used": {key: built["params"][key] for key in ("bust", "shirt_length")},
            "panels": [(panel["name"], len(panel["edges"]), panel["valid"])
                       for panel in built["panels"]],
            "labels": [edge["label"] for edge in built["panels"][0]["edges"]],
            "outline_points": len(built["panels"][0]["outline"])}


def _component_refusals(qyapi):
    unknown_id = str(_raise(lambda: qyapi.components.build("nope")))
    unknown_param = str(_raise(lambda: qyapi.components.build("gc_tee_torso",
                                                              {"nope": 1.0})))
    crossing = qyapi.components.build("square", {"width": 300.0, "height": 400.0,
                                                 "top_bow": 1.0})
    return {"unknown_id": unknown_id, "unknown_param": unknown_param,
            "bow_valid": crossing["panels"][0]["valid"]}


def _generator_create(qyapi):
    created = qyapi.generators.create("gc_tee_torso",
                                      {"bust": 92.0, "shirt_length": 1.3},
                                      name="probe torso")
    return {"name": created["name"], "component": created["component"],
            "slots": created["slots"],
            "panels": [(panel["name"], panel["vertices"], panel["edges"],
                        panel["mesh_vertices"]) for panel in created["panels"]],
            "bust": created["parameters"]["bust"],
            "shirt_length": created["parameters"]["shirt_length"]}


def _panel_read(qyapi):
    panel = qyapi.generators.get("probe torso")["panels"][0]["name"]
    entry = qyapi.patterns.get(panel)
    points = qyapi.patterns.points(panel)
    return {"panel": entry["name"],
            "edges": [(edge["index"], edge["label"], edge["kind"],
                       round(edge["length_mm"], 1)) for edge in entry["edges"]],
            "points_match": points["count"] == entry["vertices"],
            "chain": entry["chain"],
            "sewings": len(entry["sewings"]),
            "generated": entry["generated"]}


def _panel_create(qyapi):
    created = qyapi.patterns.create([[0.0, 0.0], [250.0, 0.0], [260.0, 45.0],
                                     [-50.0, 45.0]],
                                    name="collar", granularity_mm=10.0)
    return {"name": created["name"], "requested": created["requested_name"],
            "vertices": created["vertices"], "edges": created["edges"],
            "mesh_vertices": created["mesh_vertices"],
            "granularity_mm": created["granularity_mm"],
            "fabric": created["fabric"],
            "validity": created["outline_validity"]}


def _name_suffix(qyapi):
    created = qyapi.patterns.create([[0.0, 0.0], [40.0, 0.0], [40.0, 30.0]],
                                    name="collar", granularity_mm=10.0)
    return {"requested": created["requested_name"], "name": created["name"]}


def _sew_checks(qyapi):
    torso = qyapi.generators.get("probe torso")["panels"][0]["name"]
    plain = qyapi.sewings.sew(("collar", 2), (torso, 0))
    flipped = qyapi.sewings.sew(("collar", 0), (torso, 2), flip=True)
    from_points = qyapi.sewings.sew_at("collar", 1, 0.1, torso, 1, 0.9)
    unknown = str(_raise(lambda: qyapi.sewings.sew(("collar", "neckline"),
                                                   (torso, 0))))
    return {"plain_sides": _sides(plain), "flipped_sides": _sides(flipped),
            "plain_color": [round(value, 3) for value in plain["color"]],
            "plain_stitches": plain["stitch_count"],
            "from_positions": from_points["stitch_count"],
            "from_positions_sides": _sides(from_points),
            "unknown_label": unknown}


def _sides(entry):
    """What the add-on's own sewing recorded, reported, not interpreted."""
    return [(side["side"], side["panel"], side["edge_index"], side["pos1"],
             side["pos2"], side["reverse"]) for side in entry["sides"]]


def _sewing_agreement(qyapi):
    everywhere = qyapi.sewings.list()["sewings"]
    on_collar = qyapi.sewings.of("collar")["sewings"]
    expected = [entry for entry in everywhere
                if any(side["panel"] == "collar" for side in entry["sides"])]
    return {"all": len(everywhere), "on_collar": len(on_collar),
            "agree": [entry["index"] for entry in on_collar]
            == [entry["index"] for entry in expected],
            "stitches": [entry["stitch_count"] for entry in on_collar],
            "stitch_errors": [entry["stitch_error"] for entry in on_collar]}


def _set_params(qyapi):
    before = qyapi.patterns.get("collar")["sewings"]
    changed = qyapi.generators.set_params("probe torso", {"bust": 108.0,
                                                          "shirt_length": 1.5})
    after = qyapi.patterns.get("collar")["sewings"]
    clamped = qyapi.generators.set_params("probe torso", {"shirt_length": 99.0})
    return {"report": {key: changed["report"][key] for key in
                       ("in_place", "rebuilt", "created", "removed", "remapped",
                        "dropped_sewings", "invalid_panels")},
            "simulation_before": changed["simulation_before"],
            "simulation_carried": changed["simulation_carried"],
            "sewings_before": len(before), "sewings_after": len(after),
            "bust": changed["parameters"]["bust"],
            "clamped_shirt_length": clamped["parameters"]["shirt_length"]}


def _panel_edits(qyapi):
    kinds_before = [edge["kind"]
                    for edge in qyapi.patterns.get("collar")["edges"]]
    moved = qyapi.patterns.set_point("collar", 0, [-5.0, -5.0])
    split = qyapi.patterns.add_point("collar", 0, [120.0, -2.5])
    merged = qyapi.patterns.remove_point("collar", 1)
    handle = qyapi.patterns.set_handle("collar", 1, 1, [140.0, 20.0], "FREE")
    spline = qyapi.patterns.add_spline_point("collar", 1, [150.0, 25.0])
    kinds_after_spline = [edge["kind"]
                          for edge in qyapi.patterns.get("collar")["edges"]]
    plain = qyapi.patterns.remove_spline_point("collar", 1, 0)
    kinds_after_plain = [edge["kind"]
                         for edge in qyapi.patterns.get("collar")["edges"]]
    straight = qyapi.patterns.set_handle("collar", 1, 1, type="VECTOR")
    placed = qyapi.patterns.transform("collar", anchor=[10.0, 5.0], rotation=0.25,
                                      collision_layer=1)
    return {"vertices_after_move": moved["vertices"],
            "kinds_before": kinds_before,
            "after_split": (split["vertices"], split["edges"]),
            "after_merge": (merged["vertices"], merged["edges"],
                            merged["dropped_sewings"]),
            "valid_after_handle": handle["outline_validity"],
            "kinds_after_spline": kinds_after_spline,
            "kinds_after_plain_again": kinds_after_plain,
            "vertices_after_straight": straight["vertices"],
            "placement": {"anchor": [10.0, 5.0], "layer": placed["collision_layer"],
                          "rotation": 0.25}}


def _settle(qyapi):
    """The acceptance ending: the rebuilt panels settle over a few frames."""
    prepared = qyapi.sim.prepare()
    before = qyapi.sim.read("collar")["objects"][0]["local"]
    stepped = qyapi.sim.step(4)
    after = qyapi.sim.read("collar")["objects"][0]["local"]
    delta = np.asarray(after, dtype=np.float64) - np.asarray(before, dtype=np.float64)
    distance = np.sqrt((delta ** 2).sum(axis=1))
    # The panels have run now, so a parameter change has positions to carry.
    rebuilt = qyapi.generators.set_params("probe torso", {"bust": 104.0})
    return {"objects": prepared["objects"], "substeps": stepped["substeps"],
            "max_move_mm": round(float(distance.max()) * 1000.0, 3),
            "residual_newton_relative": stepped["engine_statistics"]
            .get("residuals", {}).get("newton_relative"),
            "simulation_before_rebuild": rebuilt["simulation_before"],
            "simulation_carried": rebuilt["simulation_carried"],
            "dropped_sewings": rebuilt["report"]["dropped_sewings"],
            "sewings_on_collar": len(qyapi.patterns.get("collar")["sewings"])}


def _internal_line_check(qyapi):
    added = qyapi.patterns.add_internal_line("collar",
                                             [[20.0, 10.0], [120.0, 10.0]])
    after_add = qyapi.patterns.get("collar")
    removed = qyapi.patterns.remove_internal_line("collar", 0)
    after_remove = qyapi.patterns.get("collar")
    return {"internal_lines_after_add": added["internal_lines"],
            "vertices_after_add": after_add["vertices"],
            "mesh_after_add": after_add["mesh_vertices"],
            "internal_lines_after_remove": removed["internal_lines"],
            "vertices_after_remove": after_remove["vertices"],
            "mesh_after_remove": after_remove["mesh_vertices"]}


def _fabric_check(qyapi):
    names = qyapi.patterns.fabrics()["fabrics"]
    assigned = qyapi.patterns.assign_fabric("collar", names[0])
    unknown = str(_raise(lambda: qyapi.patterns.assign_fabric("collar", "silk")))
    return {"fabrics": names, "assigned": assigned["fabric"], "unknown": unknown}


def _sewing_edit_check(qyapi):
    seams = qyapi.sewings.of("collar")["sewings"]
    recoloured = qyapi.sewings.set_color(seams[-1]["index"], [1.0, 0.0, 0.0])
    removed = qyapi.sewings.remove(seams[-1]["index"])
    left = qyapi.sewings.of("collar")["sewings"]
    return {"colour": [round(value, 3) for value in recoloured["color"]],
            "removed": removed["removed"], "sewings_left": removed["sewings_left"],
            "on_collar_after": len(left)}


def _detach_check(qyapi):
    created = qyapi.generators.create("square", {"width": 200.0, "height": 150.0},
                                      name="probe square")
    untouched = qyapi.generators.set_params("probe square", {"height": 120.0})
    detached = qyapi.generators.detach("probe square")
    panels = qyapi.patterns.list()["panels"]
    names = detached["detached"]
    still_there = [entry for entry in panels if entry["name"] in names]
    cleanup = qyapi.patterns.remove(names)
    return {"detached": names, "kept": len(still_there),
            "generated_flag_after": [entry["generated"] for entry in still_there],
            "generators_left": detached["generators_left"],
            "cleaned": cleanup["removed"], "created": created["name"],
            "simulation_before_rebuild": untouched["simulation_before"],
            "simulation_carried": untouched["simulation_carried"]}


def _panel_copy(qyapi):
    curly = qyapi.patterns.create([[0.0, 0.0], [80.0, 0.0], [80.0, 60.0], [0.0, 60.0]],
                                  name="probe curvy", granularity_mm=10.0)
    qyapi.patterns.set_handle("probe curvy", 0, 1, [20.0, -30.0], "FREE")
    qyapi.patterns.set_handle("probe curvy", 0, 2, [60.0, -30.0], "FREE")
    source_kinds = [edge["kind"]
                    for edge in qyapi.patterns.get("probe curvy")["edges"]]
    curly_copy = qyapi.patterns.copy("probe curvy")
    copy_kinds = [edge["kind"]
                  for edge in qyapi.patterns.get(curly_copy["name"])["edges"]]
    # An edit reaches the whole chain: the copy is written with the source.
    qyapi.patterns.set_point("probe curvy", 0, [-5.0, -5.0])
    edited = (qyapi.patterns.get("probe curvy")["edges"][0]["p0"],
              qyapi.patterns.get(curly_copy["name"])["edges"][0]["p0"])
    copied = qyapi.patterns.copy("collar", mirror=True, anchor=[400.0, 0.0])
    chain = qyapi.patterns.get("collar")["chain"]
    back = qyapi.patterns.get(copied["name"])["chain"]
    removed = qyapi.patterns.remove(copied["name"])
    cleanup = qyapi.patterns.remove([curly_copy["name"], curly["name"]])
    return {"copy": copied["name"],
            "chain": sorted(chain), "chain_from_copy": sorted(back),
            "removed": removed["removed"], "left": removed["panels_left"],
            "source_kinds": source_kinds, "copy_kinds": copy_kinds,
            "kinds_match": source_kinds == copy_kinds,
            "chain_edit": {"source_p0": edited[0], "copy_p0": edited[1],
                           "same": edited[0] == edited[1]},
            "cleaned": cleanup["removed"]}


def _handle_refusal(qyapi):
    """A handle change the quick check cannot see: the outline is tested and restored."""
    panel = qyapi.patterns.create([[0.0, 0.0], [80.0, 0.0], [80.0, 60.0]],
                                  name="probe crossing", granularity_mm=10.0)
    accepted = qyapi.patterns.set_handle("probe crossing", 0, 2, [60.0, 10.0], "FREE")
    before = qyapi.patterns.get("probe crossing")["edges"][0]["handle1"]
    error = _raise(lambda: qyapi.patterns.set_handle("probe crossing", 0, 1,
                                                     [20.0, 30.0], "FREE"))
    after = qyapi.patterns.get("probe crossing")["edges"][0]["handle1"]
    kinds = [edge["kind"] for edge in qyapi.patterns.get("probe crossing")["edges"]]
    qyapi.patterns.remove("probe crossing")
    return {"accepted_handle2": accepted["action"],
            "refused": isinstance(error, qyapi.QyapiError), "message": str(error),
            "handle_restored": before == after, "handle_before": before,
            "handle_after": after, "kinds_after": kinds}


def _remove_refusal(qyapi):
    torso = qyapi.generators.get("probe torso")["panels"][0]["name"]
    return {"refused": str(_raise(lambda: qyapi.patterns.remove(torso)))}


def _panel_cleanup(qyapi):
    validation = qyapi.patterns.validate()
    all_valid = all(entry["valid"] for entry in validation["panels"])
    alias = qyapi.patterns.remove("collar.001")
    generator = qyapi.generators.remove("probe torso")
    collar = qyapi.patterns.remove(["collar"])
    return {"all_valid": all_valid,
            "panels_checked": len(validation["panels"]),
            "removed_alias": alias["removed"],
            "removed_generator": generator["removed"],
            "generator_dropped_sewings": generator["dropped_sewings"],
            "removed_collar": collar["removed"],
            "dropped_sewings": collar["dropped_sewings"],
            "projects_panels": len(qyapi.state()["projects"][0]["patterns"])}


if __name__ == "__main__":
    status = 1
    try:
        status = main()
    except Exception:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
