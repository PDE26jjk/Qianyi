"""Format contract and reader/writer for a captured frontend scene package.

This module deliberately does not import ``bpy``: the package is plain data, so
the same writer, reader and comparison run inside Blender (the addon) and in a
plain Python session (a verification script, or the engine-side test harness
loader).

Layout of a package directory
-----------------------------

``scene.json``
    - ``format`` / ``format_version``: ``qianyi-frontend-scene`` / ``1``.
    - ``created_utc``: capture time; the only field that differs between two
      captures of the same unchanged scene.
    - ``blender_version``, ``source`` (``.blend`` file *name*, scene name,
      frame): no absolute path is ever written.
    - ``units``: ``length`` m, ``mass`` g/m^2, ``thickness``/``granularity``
      mm, ``angle`` rad. These are the frontend's units; the engine converts
      them on the way in, so the package must not pre-convert.
    - ``solver`` / ``parameters``: the solver the scene was configured with and
      its parameter block, or null / empty.
    - ``objects``: one entry per simulated object, in the order the engine
      addresses them (cloth first, then obstacles). Per object: name, type,
      counts, ``world_matrix`` (row-major, 16 floats), ``collision_layer``,
      ``mass``, and for cloth ``grain_dir``, ``granularity``, ``thickness``,
      ``friction``, ``stretch``, ``bending`` and the fixed/attached vertex
      counts. ``array_keys`` names the arrays that belong to it.
    - ``sewings``: one entry per sewing chain, with ``patterns`` (the two cloth
      object indices the stitches join), ``stitch_count`` and ``array_key``.
    - ``summary``: total counts, the cloth edge-length statistics, the
      bounding volume and the names of the patterns whose outline crosses
      itself (empty when there is none), for a quick sanity check without
      loading the arrays.
    - ``layout``: the naming rule of the arrays.

``scene.npz``
    - ``obj{i}_vertices`` (float32, N*3): local rest positions.
    - ``obj{i}_vertices_sim`` (float32, N*3): local simulated positions.
    - ``obj{i}_edges`` (int32, E*2), ``obj{i}_triangles`` (int32, T*3): indices
      into that object's own vertices.
    - ``obj{i}_normals`` (float32, T*3): obstacles only.
    - ``obj{i}_fixed_vertices`` / ``obj{i}_attached_vertices`` (float32, N):
      pin weights in ``[0, 1]``, cloth only.
    - ``sewing{k}_stitches`` (int32, M*2): per pair, the vertex index inside
      each of the two patterns named by that sewing's ``patterns``.
"""

import json
import os

import numpy as np

FORMAT_NAME = "qianyi-frontend-scene"
FORMAT_VERSION = 1
JSON_NAME = "scene.json"
ARRAY_NAME = "scene.npz"

# Fields that differ between two captures of the same unchanged scene.
VOLATILE_KEYS = ("created_utc",)


def write(package, directory):
    """Write a package. Returns ``(json_path, array_path)``."""
    os.makedirs(directory, exist_ok=True)
    json_path = os.path.join(directory, JSON_NAME)
    array_path = os.path.join(directory, ARRAY_NAME)
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(package["json"], handle, indent=2, sort_keys=True)
        handle.write("\n")
    arrays = package["arrays"]
    np.savez_compressed(array_path, **{key: arrays[key] for key in sorted(arrays)})
    return json_path, array_path


def read(directory):
    """Read a package: ``{'json': {...}, 'arrays': {key: ndarray}}``."""
    with open(os.path.join(directory, JSON_NAME), "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    with np.load(os.path.join(directory, ARRAY_NAME)) as data:
        arrays = {key: data[key] for key in data.files}
    return {"json": payload, "arrays": arrays}


def compare(left, right):
    """Return a list of human-readable differences (empty when identical)."""
    differences = []
    left_json = {key: value for key, value in left["json"].items() if key not in VOLATILE_KEYS}
    right_json = {key: value for key, value in right["json"].items() if key not in VOLATILE_KEYS}
    if left_json != right_json:
        for key in sorted(set(left_json) | set(right_json)):
            if left_json.get(key) != right_json.get(key):
                differences.append(f"json.{key} differs")
    if set(left["arrays"]) != set(right["arrays"]):
        differences.append(f"array keys differ: {sorted(set(left['arrays']) ^ set(right['arrays']))}")
        return differences
    for key in sorted(left["arrays"]):
        array_left = left["arrays"][key]
        array_right = right["arrays"][key]
        if array_left.shape != array_right.shape:
            differences.append(f"{key}: shape {array_left.shape} != {array_right.shape}")
        elif np.issubdtype(array_left.dtype, np.floating):
            if not np.array_equal(array_left, array_right):
                differences.append(f"{key}: values differ (max {np.abs(array_left - array_right).max()})")
        elif not np.array_equal(array_left, array_right):
            differences.append(f"{key}: values differ")
    return differences


def absolute_paths(package):
    """Any absolute-path-looking string in the sidecar (must stay empty)."""
    import re

    pattern = re.compile(r"^([A-Za-z]:[\\/]|\\\\|/)")
    found = []

    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str) and pattern.match(value):
            found.append(f"{path}={value}")

    walk(package["json"], "json")
    return found
