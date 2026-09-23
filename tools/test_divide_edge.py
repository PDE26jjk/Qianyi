"""Runtime checks for the divide command, on a project built from scratch.

    blender.exe -b --factory-startup --python tools/test_divide_edge.py

No scene file: the script builds its own panels, internal lines, an instance
copy and sewings, runs the division paths against them, and finishes with the
section invariants as a whole-project sweep. Each check prints PASS or FAIL
and the process exits non-zero when anything failed.

What is covered:

1.  one outline edge, equal parts - the counts and the selection;
2.  several panels and an internal line in one command - a mixed selection;
3.  an instance copy - the outline and the internal lines sync to it;
4.  a sewing on a divided outline edge, and one on a divided internal line -
    both re-homed onto the pieces, the panels asked to relink;
5.  the corner command: an outline corner, a corner pulled to the end so the
    vertex merges away, and a corner of an internal line, on every copy;
6.  target-length boundaries: a distance that just fits, one that would leave
    a sliver, an edge too short to cut at all, a mixed selection that caps,
    and the same distances measured back from the edge's far end;
7.  a cut that lands on an existing point is reused, not written;
8.  a curved edge divides into fitted pieces without tolerance warnings;
9.  the uuid retry - a selection that does not resolve rebuilds the map,
    which is the path a re-run from the redo panel takes.
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
# The compiled triangulator the addon imports as `Qianyi_DP`.
QYIDP_BUILD = r"R:\code\cuda\qmyidp\build\Release"
FAILURES = []


def log(message):
    print(f"[divide-test] {message}", flush=True)


def import_addon(path, module_name):
    init_path = os.path.join(path, "__init__.py")
    spec = importlib.util.spec_from_file_location(module_name, init_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def check(label, condition, detail=""):
    if condition:
        log(f"PASS {label}")
    else:
        log(f"FAIL {label} {detail}")
        FAILURES.append(label)


def refuses(label, call, *args, **kwargs):
    from qmyi.model.pattern_geometry import GeometryRefused

    try:
        call(*args, **kwargs)
    except GeometryRefused as refused:
        log(f"PASS {label}: {refused.reason}")
        return refused
    log(f"FAIL {label}: no refusal was raised")
    FAILURES.append(label)
    return None


def select(project, edges):
    project.selected_edges.clear()
    for edge in edges:
        entry = project.selected_edges.add()
        entry.uuid = edge.global_uuid


def divide_selection(project, **kwargs):
    from qmyi.operators import _2d_divide_edge as divide_tools

    return divide_tools.divide_edges_on(divide_tools.selected_division_groups(project),
                                        **kwargs)


def build_square(project, name, size, origin=(0.0, 0.0)):
    """A closed square outline, one straight edge per side, the points ccw."""
    pattern = project.add_pattern()
    pattern.name = name
    half = size / 2.0
    points = [(origin[0] - half, origin[1] - half), (origin[0] + half, origin[1] - half),
              (origin[0] + half, origin[1] + half), (origin[0] - half, origin[1] + half)]
    for point in points:
        pattern.add_vertex(point)
    for index in range(len(points)):
        pattern.add_edge(index, (index + 1) % len(points), update=False)
    pattern.recreate_sections()
    pattern.forced_update()
    return pattern


def build_curved_panel(project, name, size, bulge1, bulge2=None, origin=(0.0, 0.0)):
    """A square whose bottom edge is a bezier bowed inward at its two handles.

    Equal bulges give a symmetric bow, whose parametric samples happen to be
    arc-symmetric too; unequal bulges make the samples drift off the arc, which
    is what a sewing-position read has to survive.
    """
    pattern = project.add_pattern()
    pattern.name = name
    half = size / 2.0
    points = [(-half, -half), (half, -half), (half, half), (-half, half)]
    for point in points:
        pattern.add_vertex(point)
    for index in range(len(points)):
        start, end = index, (index + 1) % len(points)
        if index == 0:
            pattern.add_edge(start, end,
                             control1=(0.0, -half + bulge1),
                             control2=(0.0, -half + (bulge2 if bulge2 is not None
                                                     else bulge1)),
                             handle1_type="FREE", handle2_type="FREE", update=False)
        else:
            pattern.add_edge(start, end, update=False)
    pattern.recreate_sections()
    pattern.forced_update()
    return pattern


def add_straight_line(pattern, start, end, is_loop=False):
    segments = [{"p0": start, "p1": end, "h1": (0.0, 0.0), "h2": (0.0, 0.0),
                 "h1_type": "VECTOR", "h2_type": "VECTOR"}]
    return pattern.add_internal_line(segments, is_loop=is_loop)


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
    from qmyi.operators import _2d_divide_edge as divide_tools

    project = bpy.data.node_groups.new("DivideTest", "QianyiNodeTree")
    project.get_default_fabric()

    # 1. one outline edge, equal parts
    panel = build_square(project, "plain", 40.0)
    refresh_all_uuids()
    before = len(panel.edges)
    report = divide_tools.divide_edges(panel, [0], parts=3)
    check("one outline edge into equal parts",
          len(panel.edges) == before + 2 and report["parts"] == 3
          and len(report["piece_uuids"]) == 3 and not report["capped"],
          f"edges {before}->{len(panel.edges)} report={report['parts']}")

    # 2. several panels and an internal line in one command
    panel_a = build_square(project, "with_line", 40.0)
    line_a = add_straight_line(panel_a, (-19.8, 0.0), (19.8, 0.0))
    panel_b = build_square(project, "plain_b", 30.0, origin=(100.0, 0.0))
    refresh_all_uuids()
    a_edges, b_edges, line_edges = len(panel_a.edges), len(panel_b.edges), len(line_a.edges)
    select(project, [panel_a.edges[0], panel_b.edges[2], line_a.edges[0]])
    groups = divide_tools.selected_division_groups(project)
    check("a mixed selection groups by panel",
          len(groups) == 2 and set(groups[0]["edges"]) == {None, 0}
          and set(groups[1]["edges"]) == {None},
          str([{key: sorted(value) for key, value in group["edges"].items()}
               for group in groups]))
    report = divide_tools.divide_edges_on(groups, parts=2)
    check("a mixed selection divides every container",
          len(panel_a.edges) == a_edges + 1 and len(panel_b.edges) == b_edges + 1
          and len(line_a.edges) == line_edges + 1
          and report["panel"] == "with_line, plain_b",
          f"a={len(panel_a.edges)} b={len(panel_b.edges)} "
          f"line={len(line_a.edges)} panel={report['panel']!r}")

    # 3. an instance copy: the outline syncs, a line does not
    owner = build_square(project, "owner", 40.0, origin=(200.0, 0.0))
    add_straight_line(owner, (200.0, -19.8), (200.0, 19.8))
    copy = owner.copy_pattern(as_instance=True)
    refresh_all_uuids()
    check("the copy mirrors the outline and carries its internal lines",
          len(copy.edges) == 4 and len(copy.vertices) == len(owner.vertices)
          and len(copy.internal_lines) == 1
          and len(copy.internal_lines[0].edges) == len(owner.internal_lines[0].edges),
          f"copy edges={len(copy.edges)} lines={len(copy.internal_lines)}")
    select(project, [owner.edges[1]])
    report = divide_selection(project, parts=2)
    check("an outline cut syncs to the copy",
          len(copy.edges) == len(owner.edges) == 5 and report["copies"] == 1,
          f"owner={len(owner.edges)} copy={len(copy.edges)} copies={report['copies']}")
    select(project, [owner.internal_lines[0].edges[0]])
    report = divide_selection(project, parts=2)
    check("a line cut syncs to every copy",
          len(owner.internal_lines[0].edges) == 2
          and len(copy.internal_lines[0].edges) == 2
          and len(copy.edges) == 5,
          f"line={len(owner.internal_lines[0].edges)} "
          f"copy_line={len(copy.internal_lines[0].edges)} "
          f"copy={len(copy.edges)}")

    # 4. sewings
    seam_a = build_square(project, "seam_a", 40.0, origin=(300.0, 0.0))
    seam_b = build_square(project, "seam_b", 40.0, origin=(400.0, 0.0))
    refresh_all_uuids()
    seam = project.add_sewing(seam_a.edges[0], 0.0, seam_a.edges[0], 1.0, False,
                              seam_b.edges[0], 0.0, seam_b.edges[0], 1.0, False)
    check("a seam between two panels was created", seam is not None,
          f"error={project.last_sewing_error!r}")
    if seam is not None:
        named = seam.side1.line1_uuid
        select(project, [seam_a.edges[0]])
        report = divide_selection(project, parts=2)
        pieces = set(report["piece_uuids"])
        side = seam.side1
        check("a seam on a divided outline edge is re-homed",
              report["sewings_moved"] >= 1 and named in pieces
              and side.line1 is not None and side.line1_uuid in pieces,
              f"moved={report['sewings_moved']} side_uuid={side.line1_uuid}")
        check("the divided seam asks both panels to relink",
              seam_a.need_sewing_update and seam_b.need_sewing_update,
              f"a={seam_a.need_sewing_update} b={seam_b.need_sewing_update}")

    line_panel = build_square(project, "line_seam", 40.0, origin=(500.0, 0.0))
    line_s = add_straight_line(line_panel, (482.0, 0.0), (518.0, 0.0))
    line_mate = build_square(project, "line_mate", 40.0, origin=(600.0, 0.0))
    line_m = add_straight_line(line_mate, (582.0, 0.0), (618.0, 0.0))
    refresh_all_uuids()
    seam = project.add_sewing(line_s.edges[0], 0.0, line_s.edges[0], 1.0, False,
                              line_m.edges[0], 0.0, line_m.edges[0], 1.0, False)
    check("a seam onto an internal line was created", seam is not None,
          f"error={project.last_sewing_error!r}")
    if seam is not None:
        select(project, [line_s.edges[0]])
        report = divide_selection(project, parts=2)
        side = seam.side1
        check("a seam on a divided internal line is re-homed",
              report["sewings_moved"] >= 1 and side.line1 is not None
              and side.line1_uuid in set(report["piece_uuids"])
              and ".internal_lines[" in side.line1.path_from_id(),
              f"moved={report['sewings_moved']} side_uuid={side.line1_uuid}")

    # a seam endpoint sitting exactly on the cut of a curved edge: the read
    # and the write of the sewing position both go through the arc length, so
    # the endpoint lands at the start of the far piece, not on the near one
    arc_panel = build_curved_panel(project, "arc_seam", 40.0, 12.0, 3.0,
                                   origin=(1400.0, 0.0))
    arc_mate = build_square(project, "arc_mate", 40.0, origin=(1500.0, 0.0))
    refresh_all_uuids()
    bow = arc_panel.edges[0]
    half_length = float(bow.length) / 2.0
    seam = project.add_sewing(bow, 0.0, bow, 0.5, False,
                              arc_mate.edges[0], 0.0, arc_mate.edges[0],
                              half_length / 40.0, False)
    check("a seam on an asymmetric curved edge was created", seam is not None,
          f"error={project.last_sewing_error!r}")
    if seam is not None:
        select(project, [bow])
        report = divide_selection(project, parts=2)
        side = seam.side1
        check("a seam endpoint at the cut lands on the far piece at its start",
              report["sewings_moved"] >= 1 and side.line2 is not None
              and side.line2_uuid in set(report["piece_uuids"])
              and side.line2_uuid != report["piece_uuids"][0]
              and abs(side.pos2) < 1e-6,
              f"moved={report['sewings_moved']} pos2={side.pos2:.6f} "
              f"lengths={report['lengths']}")

    # the corner command: an outline corner, the merged end, a line corner
    from qmyi.operators import _2d_corner as corner_tools

    corner_square = build_square(project, "corner_square", 40.0, origin=(1600.0, 0.0))
    refresh_all_uuids()
    report = corner_tools.corner_vertices(corner_square, [0], radius=8.0, mode="ROUND")
    check("an outline corner is rounded",
          len(corner_square.edges) == 5 and len(corner_square.vertices) == 5
          and not report["warnings"],
          f"edges={len(corner_square.edges)} vertices={len(corner_square.vertices)} "
          f"warnings={report['warnings']}")

    merge_square = build_square(project, "merge_square", 40.0, origin=(1650.0, 0.0))
    refresh_all_uuids()
    report = corner_tools.corner_vertices(merge_square, [0], radius=100.0,
                                          mode="ROUND", merge=True)
    check("a corner pulled to the end merges the vertex away",
          len(merge_square.edges) == 3 and len(merge_square.vertices) == 3
          and merge_square.edges[0].kind == "bezier" and not report["warnings"],
          f"edges={len(merge_square.edges)} vertices={len(merge_square.vertices)} "
          f"warnings={report['warnings']}")

    skew = build_square(project, "skew_merge", 40.0, origin=(1675.0, 0.0))
    skew.vertices[1].co = (1685.0, -20.0)
    skew.forced_update()
    refresh_all_uuids()
    report = corner_tools.corner_vertices(skew, [1], radius=45.0,
                                          mode="ROUND", merge=True)
    check("only the side the tangent reached merges",
          len(skew.edges) == 4 and len(skew.vertices) == 4
          and not report["warnings"],
          f"edges={len(skew.edges)} vertices={len(skew.vertices)} "
          f"warnings={report['warnings']}")

    line_corner_panel = build_square(project, "line_corner", 40.0, origin=(1700.0, 0.0))
    bend_segments = [
        {"p0": (-19.0, -19.0), "p1": (19.0, -19.0), "h1": (0.0, 0.0), "h2": (0.0, 0.0),
         "h1_type": "VECTOR", "h2_type": "VECTOR"},
        {"p0": (19.0, -19.0), "p1": (19.0, 19.0), "h1": (0.0, 0.0), "h2": (0.0, 0.0),
         "h1_type": "VECTOR", "h2_type": "VECTOR"},
    ]
    bend = line_corner_panel.add_internal_line(bend_segments, is_loop=False)
    line_copy = line_corner_panel.copy_pattern(as_instance=True)
    refresh_all_uuids()
    report = corner_tools.corner_vertices(line_corner_panel, [5], radius=2.0,
                                          mode="ROUND")
    check("an internal line corner is rounded, on every copy",
          len(bend.edges) == 3
          and len(line_copy.internal_lines[0].edges) == 3
          and not report["warnings"],
          f"line={len(bend.edges)} copy_line={len(line_copy.internal_lines[0].edges)} "
          f"warnings={report['warnings']}")

    vee_panel = build_square(project, "vee", 40.0, origin=(1800.0, 0.0))
    vee_segments = [
        {"p0": (-15.0, 15.0), "p1": (0.0, -10.0), "h1": (0.0, 0.0), "h2": (0.0, 0.0),
         "h1_type": "VECTOR", "h2_type": "VECTOR"},
        {"p0": (0.0, -10.0), "p1": (15.0, 15.0), "h1": (0.0, 0.0), "h2": (0.0, 0.0),
         "h1_type": "VECTOR", "h2_type": "VECTOR"},
    ]
    vee = vee_panel.add_internal_line(vee_segments, is_loop=False)
    refresh_all_uuids()
    report = corner_tools.corner_vertices(vee_panel, [5], radius=100.0,
                                          mode="ROUND", merge=True)
    check("a V tip merged past its ends keeps the outline untouched",
          len(vee.edges) == 1 and vee.edges[0].kind == "bezier"
          and len(vee_panel.edges) == 4 and len(vee_panel.vertices) == 6
          and not report["warnings"],
          f"line={len(vee.edges)} outline={len(vee_panel.edges)} "
          f"vertices={len(vee_panel.vertices)} warnings={report['warnings']}")

    # deleting an element of an internal line: a point is bridged out of the
    # chain, an edge is deleted as its two ends are, and a line left without an
    # edge goes away with the points nothing references any more
    from qmyi.operators import _2d_elements_delete as delete_tools

    del_panel = build_square(project, "del_line", 40.0, origin=(1900.0, 0.0))
    del_line_segments = [
        {"p0": (-19.0, -19.0), "p1": (0.0, 0.0), "h1": (0.0, 0.0), "h2": (0.0, 0.0),
         "h1_type": "VECTOR", "h2_type": "VECTOR"},
        {"p0": (0.0, 0.0), "p1": (19.0, -19.0), "h1": (0.0, 0.0), "h2": (0.0, 0.0),
         "h1_type": "VECTOR", "h2_type": "VECTOR"},
    ]
    del_line = del_panel.add_internal_line(del_line_segments, is_loop=False)
    refresh_all_uuids()
    # the point in the middle of a two-edge line: the edge before it carries on
    # to the point after it, so the two edges become one
    delete_tools.delete_line_elements(del_panel, 0, [del_panel.vertices[5]])
    del_panel.recreate_sections()
    del_panel.forced_update()
    check("deleting a middle point bridges the line through it",
          len(del_line.edges) == 1 and del_line.edges[0].kind == "straight"
          and len(del_panel.vertices) == 6,
          f"edges={len(del_line.edges)} vertices={len(del_panel.vertices)}")
    # the point the line ends on now: it has no point after it to carry on to,
    # so the edge that ran to it goes too and the line is empty
    delete_tools.delete_line_elements(del_panel, 0, [del_panel.vertices[5]])
    del_panel.recreate_sections()
    del_panel.forced_update()
    check("deleting the last point removes the empty line",
          len(del_panel.internal_lines) == 0 and len(del_panel.vertices) == 4,
          f"lines={len(del_panel.internal_lines)} vertices={len(del_panel.vertices)}")

    edge_del_panel = build_square(project, "del_edge", 40.0, origin=(1950.0, 0.0))
    three_segments = [
        {"p0": (-19.0, -19.0), "p1": (-6.0, 0.0), "h1": (0.0, 0.0), "h2": (0.0, 0.0),
         "h1_type": "VECTOR", "h2_type": "VECTOR"},
        {"p0": (-6.0, 0.0), "p1": (6.0, 0.0), "h1": (0.0, 0.0), "h2": (0.0, 0.0),
         "h1_type": "VECTOR", "h2_type": "VECTOR"},
        {"p0": (6.0, 0.0), "p1": (19.0, -19.0), "h1": (0.0, 0.0), "h2": (0.0, 0.0),
         "h1_type": "VECTOR", "h2_type": "VECTOR"},
    ]
    edge_line = edge_del_panel.add_internal_line(three_segments, is_loop=False)
    refresh_all_uuids()
    # the middle edge of a three-edge line, deleted as its two ends are: the
    # first edge carries on to the point beyond the gap
    delete_tools.delete_line_elements(edge_del_panel, 0,
                                      [edge_del_panel.vertices[5],
                                       edge_del_panel.vertices[6]])
    edge_del_panel.recreate_sections()
    edge_del_panel.forced_update()
    check("deleting a middle edge bridges the chain over it",
          len(edge_line.edges) == 1 and len(edge_del_panel.vertices) == 6
          and edge_line.edges[0].vertex0.get_index() == 4
          and edge_line.edges[0].vertex1.get_index() == 5,
          f"edges={len(edge_line.edges)} vertices={len(edge_del_panel.vertices)}")

    far_edge_panel = build_square(project, "del_far_edge", 40.0, origin=(2000.0, 0.0))
    far_edge_line = far_edge_panel.add_internal_line(three_segments, is_loop=False)
    refresh_all_uuids()
    # the edge an open line ends on, deleted as its two ends are: the edge that
    # ran into them has no point left to reach and goes with them, which is
    # what the maintainer confirmed - the last two edges of the line go
    delete_tools.delete_line_elements(far_edge_panel, 0,
                                      [far_edge_panel.vertices[6],
                                       far_edge_panel.vertices[7]])
    far_edge_panel.recreate_sections()
    far_edge_panel.forced_update()
    check("deleting the far edge takes the edge it leaves hanging",
          len(far_edge_line.edges) == 1 and len(far_edge_panel.vertices) == 6
          and far_edge_line.edges[0].vertex0.get_index() == 4
          and far_edge_line.edges[0].vertex1.get_index() == 5,
          f"edges={len(far_edge_line.edges)} vertices={len(far_edge_panel.vertices)}")

    # 5. target-length boundaries
    lengths = build_square(project, "lengths", 40.0, origin=(700.0, 0.0))
    refresh_all_uuids()
    report = divide_tools.divide_edges(lengths, [0], distance=25.0, cuts=1)
    check("a distance that fits cuts once",
          report["cut_count"] == 1 and not report["capped"],
          f"cuts={report['cut_count']} capped={report['capped']}")
    # the same, measured back from the edge's far end
    far = build_square(project, "far", 40.0, origin=(1200.0, 0.0))
    refresh_all_uuids()
    report = divide_tools.divide_edges(far, [0], distance=25.0, cuts=1, reverse=True)
    check("a reversed distance cuts from the far end",
          len(report["lengths"]) == 2
          and all(abs(got - want) < 1e-6
                  for got, want in zip(report["lengths"], (15.0, 25.0)))
          and report["reverse"],
          f"lengths={report['lengths']} reverse={report['reverse']}")
    report = divide_tools.divide_edges(far, [2], distance=12.0, cuts=2, reverse=True)
    check("a reversed run of cuts measures back from the far end",
          len(report["lengths"]) == 3
          and all(abs(got - want) < 1e-6
                  for got, want in zip(report["lengths"], (16.0, 12.0, 12.0))),
          f"lengths={report['lengths']}")
    select(project, [lengths.edges[1], lengths.edges[2]])
    report = divide_selection(project, distance=25.0, cuts=1)
    check("an edge too short for the distance caps, the others still cut",
          report["cut_count"] == 1 and report["capped"],
          f"cuts={report['cut_count']} capped={report['capped']}")
    tiny = build_square(project, "tiny", 0.8, origin=(800.0, 0.0))
    refresh_all_uuids()
    refuses("equal parts refuse an edge too short to cut",
            divide_tools.divide_edges, tiny, [0], parts=2)
    report = divide_tools.divide_edges(tiny, [0], distance=0.6, cuts=1)
    check("a distance with no room to cut finishes without touching the panel",
          report["cut_count"] == 0 and report["capped"] and len(tiny.edges) == 4
          and divide_tools.describe(report).startswith("nothing to divide"),
          f"cuts={report['cut_count']} edges={len(tiny.edges)} "
          f"describe={divide_tools.describe(report)!r}")
    mixed = build_square(project, "mixed", 40.0, origin=(900.0, 0.0))
    mixed_tiny = build_square(project, "mixed_tiny", 0.8, origin=(1000.0, 0.0))
    refresh_all_uuids()
    select(project, [mixed.edges[0], mixed_tiny.edges[0]])
    report = divide_selection(project, distance=0.6, cuts=1)
    check("a mixed selection cuts what fits and caps the rest",
          report["cut_count"] == 1 and report["capped"],
          f"cuts={report['cut_count']} capped={report['capped']}")

    # 6. a cut on an existing point
    tee = build_square(project, "tee", 40.0, origin=(1100.0, 0.0))
    add_straight_line(tee, (1100.0, -19.8), (1100.0, 19.8))
    refresh_all_uuids()
    # The line's feet sit 0.2mm inside the outline, so the cut at the middle of
    # the bottom edge lands on the foot and is reused; the right edge cuts free.
    select(project, [tee.edges[0], tee.edges[1]])
    report = divide_selection(project, distance=20.0, cuts=1)
    check("a cut on an existing point is reused, not written",
          report["merged"] == 1 and report["cut_count"] == 1,
          f"merged={report['merged']} cuts={report['cut_count']}")
    report = divide_tools.divide_edges(tee, [0], distance=20.0, cuts=1)
    check("a distance whose cuts all land on existing points finishes empty",
          report["cut_count"] == 0 and report["merged"] == 1
          and divide_tools.describe(report).startswith("nothing to divide"),
          f"cuts={report['cut_count']} merged={report['merged']} "
          f"describe={divide_tools.describe(report)!r}")

    # 7. a curved edge
    curved = build_curved_panel(project, "curved", 40.0, 8.0)
    refresh_all_uuids()
    report = divide_tools.divide_edges(curved, [0], parts=4)
    check("a curved edge divides into pieces fitted to tolerance",
          report["cut_count"] == 3 and not report["warnings"],
          f"cuts={report['cut_count']} warnings={report['warnings']}")
    kinds = {curved.edges[index].kind for index in range(4)}
    check("the bowed pieces come back as splines", "spline" in kinds, str(kinds))

    # 8. the uuid retry: the path a re-run from the redo panel takes
    select(project, [curved.edges[0]])
    global_data.uuid2obj.clear()
    groups = divide_tools.selected_division_groups(project)
    check("an unresolved selection rebuilds the uuid map",
          len(groups) == 1 and groups[0]["edges"] == {None: [0]},
          str(groups))

    # the whole-project sweep, with the sewings re-linked the way the editor does
    for pattern in project.patterns:
        pattern.need_sewing_update = True
    project.setup_sewings_for_simulation()
    spec = importlib.util.spec_from_file_location(
        "check_section_invariants", os.path.join(REPO, "tools", "check_section_invariants.py"))
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    swept = checker.run_checks("divide-test")

    log(f"done: {len(FAILURES)} failed check(s), "
        f"{swept} failed invariant group(s)")
    return 1 if (FAILURES or swept) else 0


if __name__ == "__main__":
    sys.path.insert(0, QYIDP_BUILD)
    import_addon(REPO_ADDON, "qmyi")
    status = 1
    try:
        status = main()
    except Exception:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
