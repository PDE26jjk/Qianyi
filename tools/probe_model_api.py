"""Call the model API the viewport selection path uses, headless.

    blender.exe -b --factory-startup <scene.blend> --python tools/probe_model_api.py

Read-only: no solver, no GPU, no scene write. It reproduces the calls the draw
and selection path makes (``hover_object.get_index()``,
``edge.get_parent()``), so a broken model class is caught without a UI.
"""

import importlib.util
import os
import sys
import traceback

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")


def log(message):
    print(f"[model] {message}", flush=True)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def check(label, call):
    try:
        log(f"{label}: OK -> {call()}")
        return True
    except Exception as error:
        log(f"{label}: FAIL -> {error!r}")
        traceback.print_exc()
        return False


def main():
    import_addon(ADDON_PATH, "qmyi")
    from qmyi import global_data
    from qmyi.model import model_data
    from qmyi.model import register as register_model

    global_data.renderers_enabled = False
    register_model()
    log(f"registered {model_data.refresh_all_uuids()} model objects")

    from qmyi.utilities.node_tree import get_all_node_tree

    projects = get_all_node_tree()
    if not projects:
        log("no Qianyi project in this scene")
        return 2
    project = projects[0]
    pattern = project.patterns[0]
    edge = pattern.edges[0]
    vertex = pattern.vertices[0]

    ok = True
    # Known limitation, not a regression: path_from_id() does not support path
    # creation for a NodeTree, so the project itself has no index. Nothing in
    # the selection path calls it.
    try:
        project.get_index()
        log("project.get_index(): OK")
    except ValueError as error:
        log(f"project.get_index(): known limitation ({error})")
    ok &= check("pattern.get_index()", pattern.get_index)
    ok &= check("pattern.get_parent()", lambda: pattern.get_parent().name)
    ok &= check("edge.get_index()", edge.get_index)
    ok &= check("edge.get_parent()", lambda: edge.get_parent().name)
    ok &= check("vertex.get_index()", vertex.get_index)
    ok &= check("pattern.fabric", lambda: pattern.fabric.name)
    ok &= check("mesh.pattern lookup", lambda: pattern.mesh_object.qmyi_simulation_props.pattern.name)
    if len(project.sewings) > 0:
        sewing = project.sewings[0]
        side = sewing.side1
        ok &= check("sewing.side1.line1", lambda: side.line1.name)

    from qmyi.gizmos import temp_draw_manager  # imported for its module level only

    # The exact expression the draw path wraps in try/except.
    scene_qmyi = bpy.context.scene.qmyi
    scene_qmyi.set_hover_object(pattern)
    ok &= check("hover_object.get_index()", lambda: scene_qmyi.hover_object.get_index())
    scene_qmyi.set_hover_object(None)
    log(f"model api check: {'OK' if ok else 'FAIL'}")
    return 0 if ok else 3


if __name__ == "__main__":
    status = 1
    try:
        status = main()
    except Exception:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
