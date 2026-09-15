"""Check a captured scene package without Blender.

    python tools/verify_capture.py <package-dir> [<second-package-dir>]

Prints the summary, lists any absolute path in the sidecar (must be none) and,
when a second package is given, compares the two (they must be identical apart
from the documented timestamp).
"""

import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_MODULE = os.path.join(REPO, "Qianyi", "simulation", "scene_package.py")


def load_package_module():
    spec = importlib.util.spec_from_file_location("scene_package", PACKAGE_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    package = load_package_module()
    left = package.read(argv[0])
    summary = left["json"]["summary"]
    print(f"format={left['json']['format']} version={left['json']['format_version']} "
          f"blender={left['json']['blender_version']}")
    print(f"source={left['json']['source']} solver={left['json']['solver']}")
    print(f"objects={summary['object_count']} cloth={summary['cloth_count']} "
          f"obstacles={summary['obstacle_count']} vertices={summary['vertex_count']} "
          f"edges={summary['edge_count']} triangles={summary['triangle_count']} "
          f"stitches={summary['stitch_count']}")
    lengths = summary['cloth_edge_length']
    print(f"cloth edge length: median={lengths['median']:.6f} m "
          f"mean={lengths['mean']:.6f} m max={lengths['max']:.6f} m")
    for obj in left["json"]["objects"]:
        print(f"  obj[{obj['index']}] {obj['name']} type={obj['object_type']} "
              f"verts={obj['vertex_count']} layer={obj['collision_layer']} "
              f"mass={obj['mass']} arrays={sorted(obj['array_keys'])}")
    for sewing in left["json"]["sewings"]:
        print(f"  sewing[{sewing['index']}] patterns={sewing['patterns']} "
              f"stitches={sewing['stitch_count']}")
    paths = package.absolute_paths(left)
    print(f"absolute paths: {paths if paths else 'none'}")
    status = 0
    if paths:
        status = 1
    if len(argv) > 1:
        right = package.read(argv[1])
        differences = package.compare(left, right)
        if differences:
            print("captures differ:")
            for line in differences:
                print(f"  {line}")
            status = 1
        else:
            print("two captures agree (excluding the timestamp)")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
