"""Check the Solver panel data and drive the engine from it, headless.

    blender.exe -b --factory-startup <scene.blend> --python tools/probe_solver_panel.py -- --frames 30 [--gravity 0]

The parameter block is applied only through the panel
(``scene.qmyi.solver.apply_to_engine()``), never by calling the engine API
directly, so the printed cloth height is evidence that the UI reaches the
simulation.

WARNING: this runs the solver on the GPU. Do not run it while another session
or agent is using the engine - it is a functional check, not a read-only probe.
"""

import importlib.util
import os
import sys
import traceback

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")


def log(message):
    print(f"[panel] {message}", flush=True)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    frames = 30
    gravity = -9.8
    max_vel = 10.0
    if "--frames" in argv:
        frames = int(argv[argv.index("--frames") + 1])
    if "--gravity" in argv:
        gravity = float(argv[argv.index("--gravity") + 1])
    if "--max_vel" in argv:
        max_vel = float(argv[argv.index("--max_vel") + 1])

    import_addon(ADDON_PATH, "qmyi")
    import qmyi

    qmyi.register()

    scene = bpy.context.scene
    solver = scene.qmyi.solver

    # 1. Property kinds: the panel must show a number field, a checkbox or a
    # dropdown, not a float for everything.
    for name in ("pd_iters", "linear_iters", "pd_hessian_every", "step_h",
                 "ground", "velocity_damping", "bending_model", "linear_solver_type"):
        prop = solver.bl_rna.properties[name]
        log(f"{name}: type={prop.type}")

    # 2. Collapsible groups.
    from qmyi.ui.panels_3d import simulation_params

    for cls in simulation_params.GROUP_PANELS:
        log(f"group panel {cls.__name__}: parent={cls.bl_parent_id} options={sorted(cls.bl_options)}")

    # 3. Developer gating.
    solver.developer_mode = False
    debug_cls = next(cls for cls in simulation_params.GROUP_PANELS if cls.bl_label == "Debug")
    log(f"debug group visible without developer mode: {bool(debug_cls.poll(bpy.context))}")
    solver.developer_mode = True
    log(f"debug group visible with developer mode: {bool(debug_cls.poll(bpy.context))}")

    # 4. Custom key/value parameters.
    solver.add_custom("max_force_scale", 0.25)
    known, custom = solver.load_values({"pd_iters": 7, "some_future_knob": 1.5})
    values = solver.as_dict()
    log(f"custom entries={len(solver.custom)} known={known} custom={custom} "
        f"pd_iters={values['pd_iters']} max_force_scale={values['max_force_scale']} "
        f"some_future_knob={values['some_future_knob']}")

    # 5. Drive the engine from the panel only.
    solver.gravity = gravity
    solver.max_vel = max_vel
    solver.pd_iters = 5
    solver.linear_iters = 2
    solver.custom.clear()
    solver.remove_custom()
    from qmyi.simulation.simulation_manager import simulation_manager

    simulation_manager._apply_panel_parameters()
    log(f"last applied: {solver.last_applied}")
    simulation_manager.setup_data()
    import Qianyi_DP as qydp

    simulator = qydp.simulator
    simulator.input_data({"mesh_list": simulation_manager.simulated_objects,
                          "sewings": simulation_manager.sewings})
    first_vertices = len(simulation_manager.simulated_objects[0]["vertices"]) // 3
    initial = simulator.get_simulation_data().reshape(-1, 3)[:first_vertices].copy()
    for _ in range(frames):
        simulator.update(0.0045)
    positions = simulator.get_simulation_data().reshape(-1, 3)[:first_vertices]
    displacement = positions - initial
    step = np.abs(displacement).sum(axis=1)
    log(f"gravity={gravity} max_vel={max_vel} frames={frames} "
        f"z mean {initial[:, 2].mean():.6f} -> {positions[:, 2].mean():.6f} "
        f"mean |dz|={np.abs(displacement[:, 2]).mean():.9f} "
        f"mean path={step.mean():.9f} max path={step.max():.9f}")
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
