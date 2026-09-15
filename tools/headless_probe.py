"""Probe the Qianyi addon data path in a background Blender session.

Read-only diagnostic: it loads the addon the same way the study notebooks do,
registers each core module separately (so a failing module names itself instead
of being swallowed by the registration factory), and then builds the payload
that ``SimulationManager.setup_data`` would send to the engine.

    blender.exe -b --factory-startup <scene.blend> --python tools/headless_probe.py
"""

import importlib
import importlib.util
import os
import sys
import traceback

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ADDON = os.path.join(REPO, "Qianyi")


def log(message):
    print(f"[probe] {message}", flush=True)


def probe_import(module_name):
    try:
        __import__(module_name)
        log(f"import {module_name}: OK")
        return True
    except Exception:
        log(f"import {module_name}: FAIL")
        traceback.print_exc()
        return False


def import_addon(path, module_name):
    init_path = os.path.join(path, "__init__.py")
    if not os.path.exists(init_path):
        raise RuntimeError(f"no addon package at {init_path}")
    spec = importlib.util.spec_from_file_location(module_name, init_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main():
    log(f"blender {bpy.app.version_string} background={bpy.app.background}")
    log(f"repo={REPO}")
    log(f"scene={bpy.context.scene.name if bpy.context.scene else None} "
        f"objects={len(bpy.data.objects)}")

    for name in ("gpu", "gpu_extras", "gpu_extras.batch"):
        probe_import(name)

    try:
        qmyi = import_addon(REPO_ADDON, "qmyi")
    except Exception:
        log("addon package import: FAIL")
        traceback.print_exc()
        return 1
    log("addon package import: OK")

    # Mirrors the capture entry point: no GPU context in a background session.
    from qmyi import global_data

    global_data.renderers_enabled = False

    # Register module by module so the failing module is identifiable.
    from qmyi.registration import core_modules

    for name in core_modules:
        try:
            module = importlib.import_module(f"qmyi.{name}")
        except Exception:
            log(f"module {name}: import FAIL")
            traceback.print_exc()
            continue
        try:
            module.register()
            log(f"module {name}: register OK")
        except Exception:
            log(f"module {name}: register FAIL")
            traceback.print_exc()

    try:
        from qmyi.simulation.simulation_manager import simulation_manager

        simulation_manager.setup_data()
        mesh_list = simulation_manager.simulated_objects
        sewings = simulation_manager.sewings
        log(f"setup_data: OK objects={len(mesh_list)} sewings={len(sewings)}")
        for index, item in enumerate(mesh_list):
            log(f"  [{index}] {item['obj'].name} type={item['object_type']} "
                f"verts={len(item['vertices']) // 3} "
                f"edges={len(item['edges']) // 2} "
                f"tris={len(item['triangles']) // 3} "
                f"keys={sorted(k for k in item if k != 'obj')}")
        for index, sewing in enumerate(sewings):
            log(f"  sewing[{index}] patterns={tuple(sewing['patterns'])} "
                f"stitches={len(sewing['stitches'])}")
    except Exception:
        log("setup_data: FAIL")
        traceback.print_exc()
        return 2

    return 0


if __name__ == "__main__":
    status = 1
    try:
        status = main()
    except Exception:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    # The task-manager thread and an interactive-session server would otherwise
    # keep the process alive after the script returns.
    os._exit(status)
