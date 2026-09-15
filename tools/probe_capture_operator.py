"""Run the capture operator in a background session and check what it wrote.

    blender.exe -b --factory-startup <scene.blend> --python tools/probe_capture_operator.py -- --out <dir>

This exercises the interactive code path (full addon registration, the
operator, the solver panel data) without a UI.
"""

import importlib.util
import json
import os
import sys
import traceback

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")


def log(message):
    print(f"[op] {message}", flush=True)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = None
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    if not out:
        log("--out DIR is required")
        return 2

    addon = import_addon(ADDON_PATH, "qmyi")
    addon.register()
    from qmyi import global_data

    log(f"renderers_enabled={global_data.renderers_enabled} (background={bpy.app.background})")

    scene = bpy.context.scene
    solver = scene.qmyi.solver
    solver.solver_name = "PDNewton"
    solver.pd_iters = 10
    solver.linear_iters = 5
    solver.pd_hessian_every = 2
    solver.step_h = 0.0045
    log(f"solver panel: {solver.solver_name} pd_iters={solver.pd_iters} "
        f"step_h={solver.step_h} params={len(solver.as_dict())}")

    result = bpy.ops.qmyi.capture_scene(directory=out, use_scene_name=False)
    log(f"operator result: {result}")
    # A second capture in the same session: if the capture mutated the scene,
    # this one would differ.
    second = out.rstrip("\\/") + "_again"
    bpy.ops.qmyi.capture_scene(directory=second, use_scene_name=False)
    from qmyi.simulation import scene_package

    differences = scene_package.compare(scene_package.read(out), scene_package.read(second))
    log(f"same-session recapture differences: {differences if differences else 'none'}")

    json_path = os.path.join(out, "scene.json")
    if not os.path.exists(json_path):
        log("FAIL: scene.json was not written")
        return 3
    with open(json_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    summary = payload["summary"]
    log(f"captured: objects={summary['object_count']} vertices={summary['vertex_count']} "
        f"stitches={summary['stitch_count']}")
    log(f"recorded solver={payload['solver']} pd_iters={payload['parameters'].get('pd_iters')} "
        f"pd_hessian_every={payload['parameters'].get('pd_hessian_every')}")
    log(f"arrays: {len(os.listdir(out))} files in {out}")
    return 0


if __name__ == "__main__":
    status = 1
    try:
        status = main()
    except Exception:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
