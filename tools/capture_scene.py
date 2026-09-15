"""Capture a scene's simulation inputs from a background Blender session.

    blender.exe -b --factory-startup <scene.blend> --python tools/capture_scene.py -- --out <dir> [--solver NAME]

The package contract lives in ``Qianyi/simulation/scene_capture.py``; this
script only bootstraps the addon the same way the study notebooks do and then
runs the capture with the renderers disabled, so no GPU context is needed.
"""

import importlib.util
import os
import sys
import traceback

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")


def import_addon(path, module_name):
    init_path = os.path.join(path, "__init__.py")
    spec = importlib.util.spec_from_file_location(module_name, init_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main():
    if not bpy.data.filepath:
        print("[capture] no .blend is loaded; run: blender -b <file.blend> --python tools/capture_scene.py -- --out DIR")
        return 2

    import_addon(ADDON_PATH, "qmyi")
    from qmyi import global_data

    # A background session cannot create GPU shaders ("GPU functions for
    # drawing are not available in background mode"), so the data path must not
    # build any renderer.
    global_data.renderers_enabled = False

    # Data modules only: the UI, gizmo and editor modules register draw
    # handlers a background session has no use for.
    from qmyi import model

    model.register()

    from qmyi.simulation import scene_capture

    return scene_capture.main()


if __name__ == "__main__":
    status = 1
    try:
        status = main()
    except Exception:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    # The task-manager thread would otherwise keep the process alive.
    os._exit(status)
