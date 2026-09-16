"""Capture the simulation inputs of a Blender scene into a portable package.

The package is exactly what the frontend would hand to the engine in
``input_data({'mesh_list': ..., 'sewings': ...})``, plus the metadata a test
harness needs to rebuild the same scene without Blender: one ``scene.json``
sidecar and one ``scene.npz`` array file.

Capture is data only. It reads the scene, never saves the ``.blend`` and never
moves a vertex; the two things it does write back are the per-object
``simulation_index`` (the engine addresses cloth by that index) and, when the
sewing topology is stale, the regenerated pattern mesh that
``setup_sewings_for_simulation`` is defined to produce.

Units are the frontend's own, named in the sidecar: positions in metres,
``mass`` in g/m^2, ``thickness`` and ``granularity`` in millimetres, angles in
radians. The engine converts them on the way in, so the package must not.
"""

import os
import sys
import time

import bpy
import numpy as np

from ..model.model_data import refresh_all_uuids
from ..model.pattern import find_invalid_patterns
from . import scene_package
from .simulation_manager import build_object_payload

# entry key -> (array key pattern, dtype)
OBJECT_ARRAYS = (
    ("vertices", "obj{index}_vertices", np.float32),
    ("vertices_sim", "obj{index}_vertices_sim", np.float32),
    ("edges", "obj{index}_edges", np.int32),
    ("triangles", "obj{index}_triangles", np.int32),
    ("normals", "obj{index}_normals", np.float32),
    ("fixed_vertices", "obj{index}_fixed_vertices", np.float32),
    ("attached_vertices", "obj{index}_attached_vertices", np.float32),
)


def _participation_objects():
    """The objects ``SimulationManager.setup_data`` would send, in its order.

    Same rule: every mesh that is a pattern mesh or participates in the
    simulation, cloth first, obstacles after (the sort is stable, so the file
    order is kept inside each group).
    """
    pairs = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        props = obj.qmyi_simulation_props
        if props.is_pattern_mesh or props.participate_in_simulation:
            pairs.append((0 if props.is_pattern_mesh else 1, obj))
    pairs.sort(key=lambda item: item[0])
    return [obj for _, obj in pairs]


def _cloth_projects(objects):
    projects = []
    for obj in objects:
        props = obj.qmyi_simulation_props
        if props.is_pattern_mesh:
            project = props.pattern.project
            if project not in projects:
                projects.append(project)
    return projects


def _captured_patterns(objects):
    """The patterns whose mesh is part of the capture."""
    patterns = []
    for obj in objects:
        props = obj.qmyi_simulation_props
        if not props.is_pattern_mesh:
            continue
        try:
            pattern = props.pattern
        except ValueError:
            continue
        if pattern is not None and pattern not in patterns:
            patterns.append(pattern)
    return patterns


def _edge_lengths(entry):
    vertices = np.asarray(entry['vertices'], dtype=np.float32).reshape(-1, 3)
    edges = np.asarray(entry['edges'], dtype=np.int32).reshape(-1, 2)
    if len(edges) == 0:
        return np.zeros(0, dtype=np.float32)
    return np.linalg.norm(vertices[edges[:, 0]] - vertices[edges[:, 1]], axis=1)


def _object_json(entry, index, arrays):
    obj = entry['obj']
    data = {
        "index": index,
        "name": obj.name,
        "object_type": int(entry['object_type']),
        "is_cloth": int(entry['object_type']) == 0,
        "vertex_count": int(len(entry['vertices']) // 3),
        "edge_count": int(len(entry['edges']) // 2),
        "triangle_count": int(len(entry['triangles']) // 3),
        "world_matrix": [float(v) for v in np.asarray(entry['world_matrix'], dtype=np.float32).reshape(-1)],
        "collision_layer": int(entry['collision_layer']),
        "mass": float(entry['mass']),
        "array_keys": arrays,
    }
    if data["is_cloth"]:
        data.update({
            "grain_dir": float(entry['grain_dir']),
            "granularity": float(entry['granularity']),
            "thickness": float(entry['thickness']),
            "friction": float(entry['friction']),
            "stretch": [float(v) for v in np.asarray(entry['stretch'], dtype=np.float32).reshape(-1)],
            "bending": [float(v) for v in np.asarray(entry['bending'], dtype=np.float32).reshape(-1)],
            "fixed_vertex_count": int(np.count_nonzero(entry['fixed_vertices'])),
            "attached_vertex_count": int(np.count_nonzero(entry['attached_vertices'])),
        })
    return data


def _summary(objects, sewings, cloth_edge_lengths):
    cloth = [obj for obj in objects if obj["is_cloth"]]
    lengths = np.asarray(cloth_edge_lengths, dtype=np.float64)
    return {
        "object_count": len(objects),
        "cloth_count": len(cloth),
        "obstacle_count": len(objects) - len(cloth),
        "vertex_count": int(sum(obj["vertex_count"] for obj in objects)),
        "edge_count": int(sum(obj["edge_count"] for obj in objects)),
        "triangle_count": int(sum(obj["triangle_count"] for obj in objects)),
        "stitch_count": int(sum(sewing["stitch_count"] for sewing in sewings)),
        "cloth_edge_length": {
            "count": int(lengths.size),
            "min": float(lengths.min()) if lengths.size else 0.0,
            "median": float(np.median(lengths)) if lengths.size else 0.0,
            "mean": float(lengths.mean()) if lengths.size else 0.0,
            "max": float(lengths.max()) if lengths.size else 0.0,
        },
    }


def collect(solver=None, parameters=None):
    """Read the scene and return ``{'json': ..., 'arrays': {...}}``.

    ``solver`` / ``parameters`` are the state the engine should be started
    with; when they are None the scene's own solver panel is used.

    Order matters. The objects are indexed first (that is the addressing the
    engine and the sewing pairs use), then the sewing topology is rebuilt - the
    same rebuild ``setup_data`` performs when a simulation starts, which also
    regenerates a pattern mesh whose granularity changed since it was saved -
    and only then is the mesh read. Reading before the rebuild would capture
    the mesh stored in the file instead of the mesh the engine receives, and a
    second capture in the same session would then disagree with the first.
    """
    refresh_all_uuids()
    objects = _participation_objects()
    for index, obj in enumerate(objects):
        obj.qmyi_simulation_props.simulation_index = index

    sewings = []
    for project in _cloth_projects(objects):
        for sewing in project.setup_sewings_for_simulation():
            sewings.append(sewing)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    entries = []
    for obj in objects:
        entry = build_object_payload(obj, depsgraph, ensure_shape_keys=False)
        if entry is not None:
            entries.append(entry)

    arrays = {}
    objects_json = []
    cloth_edge_lengths = []
    for index, entry in enumerate(entries):
        present = {}
        for field, key_pattern, dtype in OBJECT_ARRAYS:
            if field not in entry:
                continue
            key = key_pattern.format(index=index)
            arrays[key] = np.asarray(entry[field], dtype=dtype).reshape(-1)
            present[field] = key
        item = _object_json(entry, index, present)
        if item["is_cloth"]:
            cloth_edge_lengths.append(_edge_lengths(entry))
        objects_json.append(item)

    sewings_json = []
    for index, sewing in enumerate(sewings):
        stitches = np.asarray(sewing['stitches'], dtype=np.int32).reshape(-1, 2)
        key = f"sewing{index}_stitches"
        arrays[key] = stitches.reshape(-1)
        sewings_json.append({
            "index": index,
            "patterns": [int(sewing['patterns'][0]), int(sewing['patterns'][1])],
            "stitch_count": int(stitches.shape[0]),
            "angle": float(sewing.get('angle', 0.0)),
            "array_key": key,
        })

    summary = _summary(objects_json, sewings_json,
                       np.concatenate(cloth_edge_lengths) if cloth_edge_lengths
                       else np.zeros(0, dtype=np.float32))
    # A capture is a simulation input for somewhere else, and a crossing outline
    # is not meshed here at all, so the package would carry the stale mesh. The
    # capture still goes out - it may be the repro - but it says so.
    summary["invalid_patterns"] = sorted(
        pattern.name or "(unnamed pattern)"
        for pattern in find_invalid_patterns(_captured_patterns(objects)))
    blend = bpy.data.filepath
    payload = {
        "format": scene_package.FORMAT_NAME,
        "format_version": scene_package.FORMAT_VERSION,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "blender_version": bpy.app.version_string,
        "source": {
            # Relative-path rule: the file name only, never the local path the
            # capture ran on.
            "blend": os.path.basename(blend) if blend else "",
            "scene": bpy.context.scene.name,
            "frame": int(bpy.context.scene.frame_current),
        },
        "units": {
            "length": "m",
            "mass": "g/m^2",
            "thickness": "mm",
            "granularity": "mm",
            "angle": "rad",
        },
        "solver": solver,
        "parameters": {key: float(value) for key, value in (parameters or {}).items()},
        "objects": objects_json,
        "sewings": sewings_json,
        "summary": summary,
        "layout": {
            "object_arrays": "obj{index}_{field}",
            "sewing_arrays": "sewing{index}_stitches",
            "ordering": "cloth objects first, then obstacles; cumulative offsets follow this order",
            "world": "obj{i}_vertices is the local rest position, obj{i}_world_matrix maps it to world space",
        },
    }
    return {"json": payload, "arrays": arrays}


def capture(directory, solver=None, parameters=None):
    """Collect the scene and write the package into ``directory``."""
    scene_solver, scene_parameters = scene_solver_state()
    package = collect(solver=solver if solver is not None else scene_solver,
                      parameters=parameters if parameters is not None else scene_parameters)
    json_path, array_path = scene_package.write(package, directory)
    return package, json_path, array_path


def main(argv=None):
    """CLI for a background session: ``blender -b file.blend --python ...``.

    Everything after ``--`` is ours: ``--out DIR`` is required, the solver name
    comes from the scene unless ``--solver NAME`` is given.
    """
    argv = list(sys.argv if argv is None else argv)
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out = None
    solver = None
    index = 0
    while index < len(argv):
        if argv[index] == "--out" and index + 1 < len(argv):
            out = argv[index + 1]
            index += 2
        elif argv[index] == "--solver" and index + 1 < len(argv):
            solver = argv[index + 1]
            index += 2
        else:
            print(f"[capture] ignoring argument {argv[index]!r}")
            index += 1
    if not out:
        print("[capture] --out DIR is required")
        return 2
    scene_solver, scene_parameters = scene_solver_state()
    package, json_path, array_path = capture(
        out, solver=solver if solver is not None else scene_solver,
        parameters=scene_parameters)
    summary = package["json"]["summary"]
    print(f"[capture] objects={summary['object_count']} "
          f"(cloth {summary['cloth_count']}, obstacles {summary['obstacle_count']}) "
          f"vertices={summary['vertex_count']} stitches={summary['stitch_count']}")
    print(f"[capture] edge length median={summary['cloth_edge_length']['median']:.6f} m")
    if summary["invalid_patterns"]:
        print(f"[capture] WARNING: outline intersects itself in "
              f"{len(summary['invalid_patterns'])} pattern(s): "
              f"{', '.join(summary['invalid_patterns'])}")
    print(f"[capture] wrote {json_path}")
    print(f"[capture] wrote {array_path}")
    return 0


def scene_solver_state():
    """``(solver name, parameter map)`` from the scene's solver panel."""
    scene = bpy.context.scene
    if scene is None or not hasattr(scene, "qmyi"):
        return None, {}
    solver = getattr(scene.qmyi, "solver", None)
    if solver is None:
        return None, {}
    return solver.solver_name, solver.as_dict()


if __name__ == "__main__":
    sys.exit(main())
