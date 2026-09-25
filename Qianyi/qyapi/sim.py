"""Simulation control of the Qianyi script surface.

One call per intent, with the order the engine needs owned here instead of by
the caller: validate the outlines, apply the solver parameters, build the
payload, bind the engine, then advance it. See ``qyapi.__doc__`` and
``docs/agent-api.md`` for the whole contract.

Two ways to run, and they exclude each other:

* ``step(frames)`` advances the engine on the calling thread and applies the
  result before returning. This is the path a script uses: the number of engine
  substeps depends on the argument alone, not on machine load.
* ``start()``/``stop()`` drive the timer-based run a human watches in the
  viewport. ``start()`` refuses while a step is in flight, ``step()`` refuses
  while that run is going.
"""

from __future__ import annotations

import time

import bpy
import numpy as np

from .errors import QyapiError
from ..model.model_data import refresh_all_uuids
from ..model.pattern import find_invalid_patterns
from ..simulation.simulation_manager import simulation_manager
from ..utilities.console import console_print

MODE_IDLE = "idle"
MODE_PREPARED = "prepared"
MODE_STEPPING = "stepping"
MODE_LIVE = "live"
MODE_FAILED = "failed"

# The engine subdivides nothing at this size: one call is one substep. 4.5 ms is
# the value the add-on ships with (the solver panel's own default).
DEFAULT_STEP_H = 0.0045


class _Session:
    """What the surface knows about the run: one place, one truth."""

    def __init__(self):
        self.clear()

    def clear(self):
        self.mode = MODE_IDLE
        self.prepared = False
        self.substeps = 0
        self.wall_time = 0.0
        self.step_h = None
        self.solver = None
        self.solver_source = None
        self.parameters_source = None
        self.parameter_count = 0
        self.last_error = None
        self.prepared_summary = None


_session = _Session()


def _scene():
    return getattr(bpy.context, "scene", None)


def _solver_panel():
    scene = _scene()
    qmyi = getattr(scene, "qmyi", None)
    return getattr(qmyi, "solver", None)


def _participation_objects():
    """The mesh objects a run would hand to the engine."""
    objects = []
    # Loop over the scene's objects: one RNA property read per object.
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        props = getattr(obj, "qmyi_simulation_props", None)
        if props is None:
            continue
        if props.is_pattern_mesh or props.participate_in_simulation:
            objects.append(obj)
    return objects


def _simulated_patterns():
    """Every pattern whose mesh a run would send to the engine."""
    patterns = []
    for obj in _participation_objects():
        props = obj.qmyi_simulation_props
        if not props.is_pattern_mesh:
            continue
        try:
            pattern = props.pattern
        except ValueError:
            # The mesh outlived its pattern; it carries no outline to check.
            pattern = None
        if pattern is not None and pattern not in patterns:
            patterns.append(pattern)
    return patterns


def _invalid_patterns():
    """Force a fresh outline test - a cached answer must not start a run."""
    refresh_all_uuids()
    return find_invalid_patterns(_simulated_patterns(), force=True)


def _refuse_invalid(invalid, action):
    names = ", ".join(pattern.name or "(unnamed pattern)" for pattern in invalid)
    raise QyapiError(
        f"{action} not started: {len(invalid)} pattern outline(s) intersect themselves",
        (f"patterns: {names}",
         "fix the outline; the pattern editor draws an intersecting outline in red"))


def _bound_engine():
    engine = simulation_manager.simulator
    if engine is None:
        raise QyapiError("the engine is not bound",
                         ("call qyapi.sim.prepare() first",))
    return engine


def _apply_parameters(solver, values):
    """Hand the solver name and the parameter block to the engine."""
    import Qianyi_DP as qydp

    engine = qydp.simulator
    known = tuple(engine.get_all_solver())
    if solver not in known:
        raise QyapiError(f"unknown solver {solver!r}",
                         (f"the engine offers: {', '.join(known)}",))
    engine.set_solver(solver)
    engine.set_parameters({str(key): float(value) for key, value in values.items()})
    return engine


def status():
    """What the surface is doing, and what the scene holds.

    ``live_running`` is read from the manager rather than from the mode, so a
    run started by a panel toggle is reported as live even though it did not go
    through this surface.
    """
    manager = simulation_manager
    live = bool(getattr(manager, "running", False))
    mode = MODE_LIVE if live else _session.mode
    scene = _scene()
    frame_hint = None
    step_h = float(_session.step_h) if _session.step_h else None
    if scene is not None and getattr(scene, "qmyi", None) is not None:
        frame_hint = float(getattr(scene.qmyi.simulation, "next_n_frames", 0) or 0) or None
    return {
        "mode": mode,
        "prepared": bool(_session.prepared),
        "engine_bound": manager.simulator is not None,
        "live_running": live,
        "objects": len(manager.simulated_objects),
        "substeps": int(_session.substeps),
        "wall_time_s": round(float(_session.wall_time), 6),
        "step_h_s": step_h,
        "solver": _session.solver,
        "solver_source": _session.solver_source,
        "parameters_source": _session.parameters_source,
        "parameter_count": int(_session.parameter_count),
        "last_error": _session.last_error,
        "panel_next_n_frames": frame_hint,
    }


def prepare(solver=None, parameters=None, step_h=None):
    """Make the scene runnable and bind it to the engine.

    Walks the order the engine needs: refresh the identities, test every
    participating outline, apply the solver name and parameter block, build the
    payload (which regenerates a mesh whose granularity changed) and hand it to
    the engine. Repeatable: the same arguments leave the same bound state.

    ``solver`` and ``parameters`` are the caller's values when they are given;
    otherwise the scene's solver panel supplies them, and the summary says
    which one it was. ``step_h`` is seconds per engine substep.
    """
    manager = simulation_manager
    if getattr(manager, "running", False):
        raise QyapiError("a live run is active",
                         ("call qyapi.sim.stop() before preparing",))
    if _session.mode == MODE_STEPPING:
        raise QyapiError("a step is in flight", ("finish it before preparing again",))

    invalid = _invalid_patterns()
    if invalid:
        _refuse_invalid(invalid, "simulation preparation")

    panel = _solver_panel()
    values = None
    solver_source = "caller" if solver is not None else "scene"
    parameters_source = "caller" if parameters is not None else "scene"
    if solver is None:
        if panel is None:
            raise QyapiError("no solver name was given and the scene has no solver panel")
        solver = str(panel.solver_name)
    if parameters is None:
        if panel is None:
            raise QyapiError("no parameters were given and the scene has no solver panel")
        values = dict(panel.as_dict())
    else:
        values = {str(key): float(value) for key, value in dict(parameters).items()}

    if step_h is None:
        raw = values.get("step_h")
        if raw is None and panel is not None:
            raw = getattr(panel, "step_h", None)
        step_h = float(raw) if raw else DEFAULT_STEP_H
    step_h = float(step_h)
    if not step_h > 0.0:
        raise QyapiError(f"step_h must be positive, got {step_h}")

    engine = _apply_parameters(str(solver), values)
    manager.setup_data()
    manager.simulator = engine
    engine.input_data({"mesh_list": manager.simulated_objects, "sewings": manager.sewings})

    summary = _payload_summary(manager, solver, values, solver_source,
                               parameters_source, step_h)
    _session.mode = MODE_PREPARED
    _session.prepared = True
    _session.step_h = step_h
    _session.solver = str(solver)
    _session.solver_source = solver_source
    _session.parameters_source = parameters_source
    _session.parameter_count = len(values)
    _session.last_error = None
    _session.prepared_summary = summary
    summary["undo_step"] = bool(_end_write(f"prepare simulation ({solver})"))
    return summary


def _payload_summary(manager, solver, values, solver_source, parameters_source, step_h):
    vertices = 0
    triangles = 0
    # Loop over the payload entries: the counts come from per-object RNA arrays.
    for entry in manager.simulated_objects:
        vertices += len(entry["vertices"]) // 3
        triangles += len(entry["triangles"]) // 3
    stitches = 0
    for sewing in manager.sewings:
        stitches += len(sewing["stitches"]) // 2
    return {
        "solver": str(solver),
        "solver_source": solver_source,
        "parameters_source": parameters_source,
        "parameter_count": len(values),
        "step_h_s": step_h,
        "objects": len(manager.simulated_objects),
        "vertices": vertices,
        "triangles": triangles,
        "sewings": len(manager.sewings),
        "stitches": stitches,
    }


def _substep(manager, engine, step_h):
    """One engine update: the world matrices, then the step."""
    # Loop over the payload entries: one matrix comparison per object, which is
    # a per-object RNA read.
    for index, entry in enumerate(manager.simulated_objects):
        matrix = entry["obj"].matrix_world
        if matrix != manager.world_matrixs[index]:
            manager.world_matrixs[index] = matrix.copy()
            engine.update_world_matrix(index, manager.world_matrixs[index])
    engine.update(step_h)


def _engine_statistics(engine):
    """Whatever the engine reports, passed through unchanged.

    A statistic the engine does not offer is absent rather than zero, so a
    missing residual cannot be read as a converged one.
    """
    statistics = {}
    getter = getattr(engine, "get_residual_metrics", None)
    if callable(getter):
        try:
            residuals = getter()
        except Exception:
            residuals = None
        if residuals is not None:
            statistics["residuals"] = {
                str(key): float(value) for key, value in dict(residuals).items()}
    return statistics


def step(frames=1, dt=None):
    """Advance the engine by ``frames`` substeps on this thread, then report.

    Applies the resulting positions to the pattern meshes before returning, so
    the geometry a caller reads is the geometry of that substep. A failure
    raised by the engine is reported to the caller: the session leaves the
    stepping mode and needs a new ``prepare()``, because the engine's own state
    after a failed update is not knowable from here.
    """
    manager = simulation_manager
    if getattr(manager, "running", False):
        raise QyapiError("a live run is active",
                         ("call qyapi.sim.stop() before stepping",))
    if _session.mode == MODE_FAILED:
        raise QyapiError("the previous run failed",
                         (f"last error: {_session.last_error}",
                          "call qyapi.sim.prepare() again"))
    if not _session.prepared:
        raise QyapiError("nothing is prepared", ("call qyapi.sim.prepare() first",))

    frames = int(frames)
    if frames < 1:
        raise QyapiError(f"frames must be at least 1, got {frames}")
    step_h = float(dt) if dt is not None else float(_session.step_h or DEFAULT_STEP_H)
    if not step_h > 0.0:
        raise QyapiError(f"dt must be positive, got {step_h}")

    engine = _bound_engine()
    _session.mode = MODE_STEPPING
    start = time.perf_counter()
    try:
        # Loop over substeps: each one is an engine call, which is inherently
        # sequential and cannot be expressed as one array operation.
        for _index in range(frames):
            _substep(manager, engine, step_h)
        vertices = np.asarray(engine.get_simulation_data()).reshape(-1).copy()
        colors = None
        try:
            colors = np.asarray(engine.get_debug_colors()).reshape(-1).copy()
        except Exception:
            colors = None
        manager.apply_simulation_data(vertices, colors)
    except Exception as error:
        _session.mode = MODE_FAILED
        _session.prepared = False
        _session.last_error = f"{type(error).__name__}: {error}"
        console_print("qyapi.sim.step failed: ", _session.last_error)
        raise QyapiError(
            f"the engine failed during a step: {_session.last_error}",
            ("the session is no longer stepping",
             "call qyapi.sim.prepare() before running again")) from error

    elapsed = time.perf_counter() - start
    manager.record_frame(step_h * frames, elapsed)
    _session.substeps += frames
    _session.wall_time += elapsed
    _session.mode = MODE_PREPARED
    _session.last_error = None
    return {
        "substeps": frames,
        "frames": int(_session.substeps),
        "wall_time_s": round(elapsed, 6),
        "total_wall_time_s": round(_session.wall_time, 6),
        "substeps_per_second": round(frames / elapsed, 3) if elapsed > 0 else None,
        "step_h_s": step_h,
        "mode": _session.mode,
        "engine_statistics": _engine_statistics(engine),
    }


def start():
    """Start the timer-driven run a human watches in the viewport."""
    manager = simulation_manager
    if _session.mode == MODE_STEPPING:
        raise QyapiError("a step is in flight",
                         ("step() is synchronous; start() refused",
                          "the active mode is stepping"))
    if getattr(manager, "running", False):
        return status()

    invalid = _invalid_patterns()
    if invalid:
        # Refusing here is what keeps the manager's own refusal (which reports
        # through a popup in a UI session) out of a scripted call.
        _refuse_invalid(invalid, "simulation")

    panel = _solver_panel()
    restore = None
    if panel is not None and _session.parameters_source == "caller":
        # The caller's parameters won: the panel must not overwrite them.
        restore = panel.apply_on_start
        panel.apply_on_start = False
    try:
        started = manager.start_simulation()
    finally:
        if panel is not None and restore is not None:
            panel.apply_on_start = restore
    if not started:
        raise QyapiError("the run was refused", ("call qyapi.sim.status() to see why",))
    _session.mode = MODE_LIVE
    return status()


def stop():
    """End a live run, whichever path started it."""
    manager = simulation_manager
    if not getattr(manager, "running", False) and _session.mode != MODE_LIVE:
        return status()
    manager.stop_simulation()
    # The frame-driven flavour installs its own handler; end it as well so a
    # stop from here really stops whatever is running.
    manager.stop_simulation_with_animation()
    _session.mode = MODE_IDLE
    _session.prepared = False
    return status()


def _object_positions(obj):
    """Simulated local positions, the rest pose when nothing ran yet."""
    props = obj.qmyi_simulation_props
    mesh = obj.data
    count = len(mesh.vertices)
    simulated = None
    if props.is_pattern_mesh:
        simulated = props.get_simulation_vertices()
    if simulated is not None and len(simulated) == count:
        return np.asarray(simulated, dtype=np.float32)
    local = np.empty(count * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", local)
    return local.reshape(-1, 3)


def read(patterns=None):
    """The positions of every participating object, local and world.

    ``patterns`` filters by pattern name (one name or a list). Reading moves
    nothing: it reads the simulated shape key, falls back to the mesh, and
    counts the positions that are not finite instead of failing on them.
    """
    refresh_all_uuids()
    wanted = None
    if patterns is not None:
        wanted = {patterns} if isinstance(patterns, str) else {str(name) for name in patterns}

    entries = []
    for obj in _participation_objects():  # loop: one RNA read per object
        props = obj.qmyi_simulation_props
        name = None
        if props.is_pattern_mesh:
            try:
                name = props.pattern.name
            except ValueError:
                name = None
        if wanted is not None and (name is None or name not in wanted):
            continue
        local = _object_positions(obj)
        matrix = np.asarray(obj.matrix_world, dtype=np.float32)
        world = local @ matrix[:3, :3].T + matrix[:3, 3]
        entries.append({
            "name": name or obj.name,
            "object": obj.name,
            "vertex_count": int(local.shape[0]),
            "local": local,
            "world": world,
            # Count vertices, not components: one bad coordinate is one vertex
            # a caller has to deal with.
            "non_finite": int(np.count_nonzero(~np.isfinite(local).all(axis=1))),
        })

    if wanted is not None:
        found = {entry["name"] for entry in entries}
        missing = sorted(wanted - found)
        if missing:
            raise QyapiError(f"no participating pattern named {', '.join(missing)}",
                             ("qyapi.sim.read() lists every participating object",
                              "call qyapi.state() for the pattern names of the scene"))
    return _plain({"objects": entries})


def _plain(value):
    """Plain data out, without importing the surface's own converter."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def reset():
    """Discard the simulated positions and go back to the rest pose.

    Patterns, sewings and solver parameters are untouched. The session becomes
    idle, so the next run needs a ``prepare()`` - which is also what re-binds
    the engine, and therefore what makes the following run start from rest.
    """
    refresh_all_uuids()
    cleared = 0
    for obj in _participation_objects():  # loop: one shape-key write per object
        mesh = obj.data
        keys = mesh.shape_keys.key_blocks if mesh.shape_keys is not None else None
        if keys is None or "QYSim" not in keys or "QYBasis" not in keys:
            continue
        count = len(mesh.vertices) * 3
        rest = np.empty(count, dtype=np.float32)
        keys["QYBasis"].data.foreach_get("co", rest)
        keys["QYSim"].data.foreach_set("co", rest)
        mesh.update()
        cleared += 1

    summary = status()
    _session.clear()
    return {"objects": cleared, "mode": _session.mode, "before_reset": summary}


def _end_write(message):
    """Close a write call with one undo step (see qyapi.transaction)."""
    from . import end_write

    return end_write(message)
