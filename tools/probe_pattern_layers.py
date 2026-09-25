"""Check the Sketch layer: its elements, its write signal and its section stage.

    blender.exe -b --factory-startup --python tools/probe_pattern_layers.py

Builds its own Sketches (no scene file) and checks what the first slice of the
layer split promises:

1. a Sketch holds vertices, edges and internal lines and is one object per
   instance chain;
2. a write that changes the shape marks the patterns that read the Sketch, and a
   write that sets a value it already has marks nothing;
3. the first section stage links one section per edge along each chain, closed
   for the outline and for a loop, open for a line that ends;
4. a crossing cuts the sections of both curves, and the pieces of an internal
   line that lie outside the outline are marked outside;
5. the measurement behind the crossing search is the Sketch's own constant, so
   no pattern's granularity takes part in it;
6. the draw points are the edges' own curves.

Each check prints PASS or FAIL; the process exits non-zero when anything failed.
"""

import importlib
import importlib.util
import os
import sys
import traceback

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ADDON = os.path.join(REPO, "Qianyi")
QYIDP_BUILD = r"R:\code\cuda\qmyidp\build\Release"
FAILURES = []


def log(message):
    print(f"[layers] {message}", flush=True)


def check(label, condition, detail=""):
    if condition:
        log(f"PASS {label}")
    else:
        log(f"FAIL {label} {detail}")
        FAILURES.append(label)


def _raises(call) -> bool:
    """Whether `call` refuses, which is what a missing Sketch has to do."""
    try:
        call()
    except Exception:
        return True
    return False


def import_addon(path, module_name):
    init_path = os.path.join(path, "__init__.py")
    spec = importlib.util.spec_from_file_location(module_name, init_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def build_square_sketch(project, size, origin=(0.0, 0.0)):
    """A Sketch with a closed square outline, one straight edge per side."""
    sketch = project.add_sketch()
    half = size / 2.0
    points = [(origin[0] - half, origin[1] - half), (origin[0] + half, origin[1] - half),
              (origin[0] + half, origin[1] + half), (origin[0] - half, origin[1] + half)]
    for point in points:
        sketch.add_vertex(point)
    for index in range(len(points)):
        sketch.add_edge(index, (index + 1) % len(points), update=False)
    sketch.update_draw_points()
    return sketch


def add_line(sketch, points, is_loop=False):
    """One internal line through these points: a segment between each pair."""
    pairs = [(index, index + 1) for index in range(len(points) - 1)]
    if is_loop:
        pairs.append((len(points) - 1, 0))
    segments = [{"p0": points[start], "p1": points[end],
                 "h1": (0.0, 0.0), "h2": (0.0, 0.0),
                 "h1_type": "VECTOR", "h2_type": "VECTOR"}
                for start, end in pairs]
    return sketch.add_internal_line(segments, is_loop=is_loop)


def chain_report(sketch, first_section):
    """Walk one section chain: its pieces, its order and the length it covers."""
    sections = []
    section = first_section
    guard = 0
    while section is not None and section not in sections and guard < 100000:
        sections.append(section)
        section = section.next
        guard += 1
    length = sum(section.absolute_length() for section in sections)  # loop: one piece each
    linked = all(sections[index].next is sections[index + 1]
                 for index in range(len(sections) - 1))
    return sections, length, linked


def main():
    log(f"blender {bpy.app.version_string}")
    from qmyi import global_data

    global_data.renderers_enabled = False
    from qmyi.registration import core_modules

    for name in core_modules:
        importlib.import_module(f"qmyi.{name}")
    for name in core_modules:
        module = sys.modules.get(f"qmyi.{name}")
        if module is not None and hasattr(module, "register"):
            try:
                module.register()
            except Exception:
                log(f"register {name} failed")
                traceback.print_exc()

    from qmyi.model.model_data import refresh_all_uuids
    from qmyi.model.sketch import MEASURE_STEP_MM, Sketch

    project = bpy.data.node_groups.new("LayersProbe", "QianyiNodeTree")
    project.get_default_fabric()
    refresh_all_uuids()

    # 1. the elements of a Sketch and the signal a write sends
    sketch = build_square_sketch(project, 40.0)
    check("a Sketch holds the outline it was given",
          len(sketch.vertices) == 4 and len(sketch.edges) == 4
          and isinstance(sketch, Sketch) and sketch.owner is None,
          f"vertices={len(sketch.vertices)} edges={len(sketch.edges)}")
    vertex = sketch.vertices[0]
    original_x = float(vertex.co[0])
    check("moving a point leaves the shape it had",
          sketch.set_vertex_position(0, (original_x, float(vertex.co[1])))
          is False)
    check("moving a point to a new place is a write",
          sketch.set_vertex_position(0, (original_x - 2.0, float(vertex.co[1])))
          is True)
    check("the moved point is where it was put",
          abs(sketch.vertices[0].co[0] - original_x) > 1.0,
          f"co={tuple(sketch.vertices[0].co)}")
    sketch.set_vertex_position(0, (original_x, float(vertex.co[1])))

    # 3. the first section stage
    sketch.update()
    sections, length, linked = chain_report(sketch, sketch.edges[0].section_start)
    check("the outline's sections form one closed chain",
          len(sections) == 4 and linked and sections[-1].next is sections[0]
          and abs(length - 160.0) < 1e-6,
          f"pieces={len(sections)} closed={sections[-1].next is sections[0]} length={length}")

    inside = add_line(sketch, [(-10.0, -10.0), (-10.0, 10.0)])
    sketch.update()
    line_sections = sketch.line_sections(inside)
    check("an internal line's sections form an open chain",
          len(line_sections) == 1 and line_sections[0].next is None
          and line_sections[0].prev is None,
          f"pieces={len(line_sections)}")
    check("a line inside the pattern has no outside piece",
          all(not section.outsize for section in sketch.line_sections(inside)),
          f"outsize={[section.outsize for section in sketch.line_sections(inside)]}")

    # 4. a crossing cuts both curves, and the outside is marked
    outer = build_square_sketch(project, 40.0, origin=(100.0, 0.0))
    upright = add_line(outer, [(100.0, -10.0), (100.0, 10.0)])
    crossing = add_line(outer, [(70.0, 0.0), (130.0, 0.0)])
    outer.update()
    line_sections = outer.line_sections(crossing)
    outline_pieces = len(chain_report(outer, outer.edges[0].section_start)[0])
    check("a crossing cuts the line into pieces inside and outside",
          len(line_sections) == 4
          and [section.outsize for section in line_sections]
          == [True, False, False, True],
          f"pieces={len(line_sections)} "
          f"outsize={[section.outsize for section in line_sections]}")
    check("a crossing is recorded on the outline it crosses",
          outline_pieces > 4,
          f"outline pieces={outline_pieces}")
    check("two internal lines crossing cut each other",
          len(outer.line_sections(upright)) > 1,
          f"pieces={len(outer.line_sections(upright))}")

    # 5. the measurement does not follow a pattern
    samples = sketch.measured_points(sketch.edges[0])
    expected = int(np.ceil(40.0 / MEASURE_STEP_MM)) + 1
    check("the crossing search measures at the Sketch's own step",
          len(samples) == expected,
          f"points={len(samples)} expected={expected}")
    steps = np.linalg.norm(np.diff(samples, axis=0), axis=1)
    check("the measured edge is sampled at equal arc steps",
          float(steps.max() - steps.min()) < 1e-6,
          f"step range={steps.min()}..{steps.max()}")
    again = sketch.measured_points(sketch.edges[0])
    check("measuring twice gives the same points",
          np.allclose(samples, again),
          "")

    # 6. the draw points are the edges' own curves
    draw = sketch.draw_points()
    check("the draw points cover every edge",
          len(draw) == sum(len(edge.render_points) for edge in sketch.edges)
          and draw.shape[1] == 2
          and all(len(edge.render_points) >= 2 for edge in sketch.edges),
          f"shape={draw.shape}")
    straight = np.asarray(sketch.edges[0].render_points)
    ends = straight[[0, -1]]
    direction = ends[1] - ends[0]
    normal = np.array((-direction[1], direction[0])) / np.linalg.norm(direction)
    deviation = np.abs((straight - ends[0]) @ normal)
    check("a straight edge's draw points follow its line",
          float(deviation.max()) < 1e-3,
          f"deviation={float(deviation.max())}")

    # 7. a pattern holds no geometry of its own: it reads the Sketch it names
    pattern = project.add_pattern()
    pattern.name = "layers_pattern"
    for point in ((-20.0, -20.0), (20.0, -20.0), (20.0, 20.0), (-20.0, 20.0)):
        pattern.add_vertex(point)
    for index in range(4):
        pattern.add_edge(index, (index + 1) % 4, update=True)
    refresh_all_uuids()
    check("a pattern's points are its Sketch's points",
          pattern.sketch is not None
          and pattern.vertices == pattern.sketch.vertices
          and len(pattern.vertices) == 4,
          f"sketch={pattern.sketch is not None}")
    pattern.sketch_uuid = -1
    check("a pattern that names no Sketch reports no geometry",
          pattern.sketch is None and _raises(pattern.require_sketch),
          f"sketch={pattern.sketch}")
    pattern.sketch = sketch
    check("a pattern reads the Sketch it is given",
          len(pattern.vertices) == len(sketch.vertices),
          f"points={len(pattern.vertices)}")

    # 8. a copy shares the Sketch, and a detach gives it one of its own
    before_sketches = len(project.sketches)
    copy = pattern.copy_pattern(as_instance=True)
    refresh_all_uuids()
    check("a copy shares its source's Sketch",
          copy.sketch is pattern.sketch and len(project.sketches) == before_sketches,
          f"sketches {before_sketches} -> {len(project.sketches)}")
    moved = (float(copy.vertices[0].co[0]) + 3.0, float(copy.vertices[0].co[1]))
    copy.sketch.set_vertex_position(0, moved)
    check("editing through the copy edits the one Sketch",
          abs(float(pattern.vertices[0].co[0]) - moved[0]) < 1e-6,
          f"source x={float(pattern.vertices[0].co[0])}")
    pattern.need_geo_update = False
    copy.need_geo_update = False
    moved = (float(copy.vertices[0].co[0]) + 2.0, float(copy.vertices[0].co[1]))
    copy.sketch.set_vertex_position(0, moved)
    check("a write marks every pattern that reads the Sketch",
          pattern.need_geo_update and copy.need_geo_update,
          f"source={pattern.need_geo_update} copy={copy.need_geo_update}")
    pattern.sections_for_edge(None, 0)
    check("a pattern that builds its copy still has its mesh to build",
          not pattern.need_sections and pattern.need_geo_update,
          f"sections={pattern.need_sections} geo={pattern.need_geo_update}")
    report = copy.detach()
    refresh_all_uuids()
    check("a detach gives the copy a Sketch of its own",
          report["detached"] and copy.sketch is not None
          and copy.sketch is not pattern.sketch and report["staying"] == [pattern.name],
          f"report={report}")
    alone = copy.detach()
    check("a detach with nothing to detach says so",
          alone["detached"] is False and "alone" in alone["reason"],
          f"report={alone}")
    check("a pattern alone in its chain still holds its geometry",
          copy.sketch is not None and len(copy.vertices) == len(pattern.vertices),
          f"points={len(copy.vertices)}")
    copy.generate_mesh()
    samples = copy.mesh_edge_points
    check("a pattern keeps a copy of the samples its mesh was built from",
          samples is not None and len(copy.geo_points) == len(samples)
          and abs(float(copy.geo_points[0].co[0]) - float(samples[0][0])) < 1e-4,
          f"stored={len(copy.geo_points)} samples={0 if samples is None else len(samples)}")

    # 9. a Sketch lives exactly as long as a pattern reads it
    before_sketches = len(project.sketches)
    project.remove_patterns([pattern])
    check("removing the last pattern of a Sketch removes the Sketch",
          len(project.sketches) < before_sketches,
          f"sketches {before_sketches} -> {len(project.sketches)}")

    log(f"done: {len(FAILURES)} failed check(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.path.insert(0, QYIDP_BUILD)
    status = 1
    try:
        import_addon(REPO_ADDON, "qmyi")
        status = main()
    except Exception:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
