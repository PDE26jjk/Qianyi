"""Which cheap call can tell a live cached struct from a deleted one?

    blender.exe -b --factory-startup <scene.blend> --python tools/probe_struct_validity.py

`path_from_id()` is the current staleness check. It is safe but costs between
0.003 ms and 1.1 ms depending on the object, which is what makes the pattern
editor slow. This probe measures the alternatives.

Every case runs in its own Blender process: a check that touches a deleted
struct can take Blender down, and the parent has to see which one did it. The
child prints each check before running it and flushes, so the last printed line
of a crashed child names the check that crashed.
"""

import importlib.util
import os
import subprocess
import sys

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")

# Candidate *predicates*: what a lookup could evaluate to decide "still usable".
# They are printed, not asserted, because the point is which one survives a
# deleted struct and which one notices it.
PREDICATES = (
    ("cached_uuid", lambda item, stored: item.global_uuid == stored["uuid"]),
    ("uuid_not_negative", lambda item, stored: item.global_uuid != -1),
    ("id_data_alive", lambda item, stored: item.id_data is not None and item.id_data.name != ""),
    ("owner_in_bpy_data", lambda item, stored: stored["owner_lookup"]()),
    ("pointer_same", lambda item, stored: item.as_pointer() == stored["pointer"]),
    ("index_pointer_same", lambda item, stored: stored["index_lookup"]() == stored["pointer"]),
    ("path_from_id", lambda item, stored: bool(item.path_from_id())),
    ("lookup_via_api", lambda item, stored: stored["lookup"]() is not None),
)

# Accesses that are expected to be dangerous once the data is gone.
DANGEROUS = (
    ("read_prop(global_uuid)", lambda item: item.global_uuid),
    ("read_prop(name)", lambda item: item.name),
    ("len(item.edges)", lambda item: len(item.edges)),
    ("item.mesh_object", lambda item: item.mesh_object.name),
    ("item.id_data.name", lambda item: item.id_data.name),
    ("item.as_pointer()", lambda item: item.as_pointer()),
    ("item.bl_rna.identifier", lambda item: item.bl_rna.identifier),
)

CASES = (
    ("control", "edge", "nothing removed"),
    ("remove_pattern", "edge", "QianyiProject.patterns.remove(0)"),
    ("remove_edge", "edge", "Pattern.edges.remove(0)"),
    ("remove_nodegroup", "pattern", "bpy.data.node_groups.remove(project)"),
    ("remove_nodegroup", "sewing", "bpy.data.node_groups.remove(project)"),
    ("remove_object", "mesh_object", "bpy.data.objects.remove(pattern.mesh_object)"),
    ("remove_object", "pattern", "bpy.data.objects.remove(pattern.mesh_object)"),
)


def cost_mode():
    """Per-call cost of the candidate checks, on live objects."""
    import time

    import_addon(ADDON_PATH, "qmyi")
    from qmyi import global_data
    from qmyi import model
    from qmyi.model import model_data
    from qmyi.utilities.node_tree import get_all_node_tree

    global_data.renderers_enabled = False
    model.register()
    model_data.refresh_all_uuids()
    project = get_all_node_tree()[0]
    targets = [
        ("pattern[0].edge[0]", project.patterns[0].edges[0]),
        ("pattern[1].edge[0]", project.patterns[1].edges[0]),
        ("sewing[0]", project.sewings[0]),
    ]
    repeats = 300
    log(f"{'target':<20} {'global_uuid':>12} {'as_pointer':>11} {'id_data.name':>13} "
        f"{'owner_recheck':>14} {'path_from_id':>13}")
    for label, item in targets:
        owner = project
        owner_name = owner.name

        def time_it(function):
            started = time.perf_counter()
            for _ in range(repeats):
                function()
            return (time.perf_counter() - started) * 1000.0 / repeats

        uuid_ms = time_it(lambda: item.global_uuid)
        pointer_ms = time_it(lambda: item.as_pointer())
        id_data_ms = time_it(lambda: item.id_data.name)
        owner_ms = time_it(lambda: bpy.data.node_groups.get(owner_name) is owner)
        path_ms = time_it(lambda: item.path_from_id())
        log(f"{label:<20} {uuid_ms:>10.4f}ms {pointer_ms:>9.4f}ms {id_data_ms:>11.4f}ms "
            f"{owner_ms:>12.4f}ms {path_ms:>11.4f}ms")
    return 0


def log(message):
    print(f"[validity] {message}", flush=True)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def resolve_target(project, target):
    pattern = project.patterns[0]
    if target == "pattern":
        return project.patterns[1] if len(project.patterns) > 1 else pattern
    if target == "edge":
        return pattern.edges[0]
    if target == "vertex":
        return pattern.vertices[0]
    if target == "sewing":
        return project.sewings[0]
    if target == "mesh_object":
        return pattern.mesh_object
    raise ValueError(target)


def child(case, target):
    import_addon(ADDON_PATH, "qmyi")
    from qmyi import global_data
    from qmyi import model
    from qmyi.model import model_data
    from qmyi.utilities.node_tree import get_all_node_tree

    global_data.renderers_enabled = False
    model.register()
    model_data.refresh_all_uuids()
    projects = get_all_node_tree()
    if not projects:
        log("no project")
        return 2
    project = projects[0]
    item = resolve_target(project, target)
    stored = {
        "uuid": getattr(item, "global_uuid", None),
        "pointer": item.as_pointer(),
        "owner_name": project.name,
        "owner_lookup": lambda: bpy.data.node_groups.get(project.name) is not None,
        "index_lookup": (lambda: project.patterns[0].edges[0].as_pointer())
        if case in ("control", "remove_edge") else (lambda: None),
        "lookup": lambda: global_data.get_obj_by_uuid(stored["uuid"], False),
    }
    try:
        log(f"case={case} target={target} type={item.bl_rna.identifier} "
            f"uuid={stored['uuid']} pointer={stored['pointer']}")
    except Exception as error:
        log(f"case={case} target={target} header failed: {type(error).__name__}: {error}")

    if case == "remove_pattern":
        project.patterns.remove(0)
    elif case == "remove_edge":
        project.patterns[0].edges.remove(0)
    elif case == "remove_nodegroup":
        bpy.data.node_groups.remove(project)
    elif case == "remove_object":
        bpy.data.objects.remove(project.patterns[0].mesh_object)
    elif case != "control":
        log(f"unknown case {case}")
        return 2

    for name, check in PREDICATES:
        log(f"case={case} target={target} predicate {name}")
        try:
            value = check(item, stored)
            log(f"case={case} target={target} predicate {name} -> {value!r}")
        except Exception as error:
            log(f"case={case} target={target} predicate {name} -> EXC {type(error).__name__}")
    for name, access in DANGEROUS:
        log(f"case={case} target={target} access {name}")
        try:
            value = access(item)
            log(f"case={case} target={target} access {name} -> OK {value!r}")
        except Exception as error:
            log(f"case={case} target={target} access {name} -> EXC {type(error).__name__}: {error}")
    return 0


def parent(blend):
    blender = bpy.app.binary_path
    script = os.path.abspath(__file__)
    log(f"blender={blender}")
    summary = []
    for case, target, description in CASES:
        command = [blender, "-b", "--factory-startup", blend, "--python", script,
                   "--", "--case", case, "--target", target]
        completed = subprocess.run(command, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=300)
        lines = [line for line in (completed.stdout or "").splitlines()
                 if "[validity]" in line]
        results = {}
        last_line = ""
        for line in lines:
            payload = line.split("[validity]", 1)[1].strip()
            last_line = payload
            if " predicate " in payload or " access " in payload:
                label = payload.split(" predicate ", 1)[1] if " predicate " in payload \
                    else payload.split(" access ", 1)[1]
                if " -> " in label:
                    name, value = label.split(" -> ", 1)
                    results[name] = value
                else:
                    results[label] = "RUNNING"
        log(f"=== case={case} ({description}) exit={completed.returncode}")
        if completed.returncode != 0:
            log(f"    CRASHED at: {last_line}")
        for name, _ in PREDICATES:
            log(f"    predicate {name:<20} {results.get(name, 'not reached')}")
        for name, _ in DANGEROUS:
            log(f"    access    {name:<20} {results.get(name, 'not reached')}")
        summary.append((case, target, completed.returncode, results))
    log("summary (exit code per case):")
    for case, target, code, _ in summary:
        log(f"    {case}:{target} exit={code}")
    return 0


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--cost" in argv:
        sys.stdout.flush()
        os._exit(cost_mode())
    elif "--case" in argv:
        case = argv[argv.index("--case") + 1]
        target = argv[argv.index("--target") + 1] if "--target" in argv else "edge"
        status = 1
        try:
            status = child(case, target)
        except Exception:
            import traceback

            traceback.print_exc()
        sys.stdout.flush()
        os._exit(status)
    else:
        blend = bpy.data.filepath
        if not blend:
            blend = sys.argv[sys.argv.index("-b") + 1] if "-b" in sys.argv else ""
        sys.exit(parent(blend))
