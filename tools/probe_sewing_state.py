"""Reproduce the sewing state that makes "Sewing overlap!!!" appear.

    blender.exe -b --factory-startup <scene.blend> --python tools/probe_sewing_state.py

Read-only for the file: it works on the loaded scene and never saves. It adds
and removes sewings through the model API (the same calls the operator makes)
and prints the real exception behind the operator's "sewing overlap!" popup -
the operator shows that text for every failure, because add_sewing swallows the
reason and returns None.
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
    print(f"[sewing] {message}", flush=True)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def link_state(project):
    from qmyi.model.section import Section
    return (f"patterns={len(project.patterns)} sewings={len(project.sewings)} "
            f"link_maps={len(Section.link_sections)}")


def panel_of(element):
    """The panel that owns the Sketch an element lives in, or None."""
    from qmyi.model.model_data import owner_pattern
    return owner_pattern(element)


def edge_link_ids(pattern):
    ids = []
    for edge in pattern.edges:
        section = edge.section_start
        ids.append(section.link_map_id if section is not None else None)
    return ids


def sewn_edge_uuids(project):
    uuids = set()
    for sewing in project.sewings:
        for side in (sewing.side1, sewing.side2):
            uuids.add(side.line1_uuid)
            uuids.add(side.line2_uuid)
    return uuids


def try_add(project, label, edges):
    log(f"--- {label}: {link_state(project)}")
    log(f"    link_map_id on pattern[0] edges before: {edge_link_ids(project.patterns[0])}")
    sewing = project.add_sewing1to1(edge1=edges[0], edge2=edges[1])
    log(f"    add_sewing1to1 -> {'None (failed)' if sewing is None else 'ok'}")
    log(f"    {link_state(project)}")
    log(f"    link_map_id on pattern[0] edges after:  {edge_link_ids(project.patterns[0])}")
    return sewing


def check_colors_and_connectors(project, edges_random, edges_explicit):
    """Sewing color default/explicit, and the sampled connector lines."""
    from qmyi.gizmos.sewing_renderer import (STITCH_LINE_STEP_MM, polyline_length,
                                             stitch_connector_points)
    from qmyi.model.sewing import calc_sewing_side_render_points

    random_sewing = project.add_sewing1to1(edge1=edges_random[0], edge2=edges_random[1])
    if random_sewing is None:
        log("color check skipped: could not add a sewing")
        return
    color = tuple(round(float(value), 3) for value in random_sewing.color)
    log(f"color default (random): {color} white={color == (1.0, 1.0, 1.0)}")

    explicit = project.add_sewing1to1(edge1=edges_explicit[0], edge2=edges_explicit[1],
                                      color=(1.0, 0.0, 0.25))
    if explicit is None:
        log("explicit color check skipped: could not add the second sewing")
    else:
        log(f"color explicit (1,0,0.25) -> "
            f"{tuple(round(float(v), 3) for v in explicit.color)}")
        side1 = calc_sewing_side_render_points(explicit.side1)
        side2 = calc_sewing_side_render_points(explicit.side2)
        pattern1 = panel_of(explicit.side1.line1)
        pattern2 = panel_of(explicit.side2.line1)
        positions = stitch_connector_points(pattern1, side1, pattern2, side2)
        length1 = polyline_length(side1)
        length2 = polyline_length(side2)
        log(f"connectors: {len(positions)} positions = {len(positions) // 2} lines "
            f"for sides {length1:.1f} / {length2:.1f} mm "
            f"(one every {STITCH_LINE_STEP_MM} mm, ends included)")
        # The first and last pairs have to be the actual sewing ends.
        start1 = pattern1.pattern_to_view_pos(side1[0])
        start2 = pattern2.pattern_to_view_pos(side2[0])
        end1 = pattern1.pattern_to_view_pos(side1[-1])
        end2 = pattern2.pattern_to_view_pos(side2[-1])

        def close(left, right):
            return abs(left[0] - right[0]) < 1e-4 and abs(left[1] - right[1]) < 1e-4

        log(f"            start pair is the sewing start: "
            f"{close(positions[0], start1) and close(positions[1], start2)}")
        log(f"            end pair is the sewing end: "
            f"{close(positions[-2], end1) and close(positions[-1], end2)}")


def check_direction(project, edges):
    """The click end decides which ends of the two edges get stitched."""
    from qmyi.model.sewing import calc_sewing_side_sections

    edge1, edge2 = edges

    def point_at(edge, fraction):
        points = edge.render_points
        return points[int(round(fraction * (len(points) - 1)))]

    log("--- direction from the click position (0.1 = near the edge start, "
        "0.9 = near its end)")
    for label, (fraction1, fraction2) in (("start-start", (0.1, 0.1)),
                                          ("start-end", (0.1, 0.9)),
                                          ("end-start", (0.9, 0.1)),
                                          ("end-end", (0.9, 0.9))):
        sewing = project.add_sewing1to1_from_points(
            edge1, point_at(edge1, fraction1), edge2, point_at(edge2, fraction2))
        if sewing is None:
            log(f"    {label:<12} FAILED: {project.last_sewing_error}")
            continue
        parts = []
        for side in (sewing.side1, sewing.side2):
            sections, _, _ = calc_sewing_side_sections(side, [None, None], side.reverse)
            parts.append(f"pos {side.pos1}->{side.pos2} reverse={side.reverse} "
                         f"sections={len(sections)}")
        log(f"    {label:<12} ok  " + " | ".join(parts))
        project.sewings.remove(len(project.sewings) - 1)
        project.calc_all_sewings_sections()


def stitch_end_positions(sewing, pattern_index):
    """Where the first and the last stitch of one side sit, in pattern mm.

    The stitch indices are mesh vertex indices; the pattern mesh is generated
    in metres while the pattern space is millimetres, hence the factor.
    """
    data = sewing.get_stitch_data()
    stitches = np.asarray(data["stitches"])
    pattern = project_pattern_of(sewing, pattern_index)
    mesh = pattern.mesh_object.data
    first = np.array(mesh.vertices[int(stitches[0][pattern_index])].co[:2]) * 1000.0
    last = np.array(mesh.vertices[int(stitches[-1][pattern_index])].co[:2]) * 1000.0
    return first, last


def project_pattern_of(sewing, index):
    return panel_of((sewing.side1 if index == 0 else sewing.side2).line1)


def check_stitch_order(project):
    """What the physics actually pairs, for the existing sewings and for the
    four click combinations."""
    import numpy as np

    log("--- existing sewings: pos/reverse and which end their first stitch sits on")
    project.calc_all_sewings_sections()
    for index, sewing in enumerate(project.sewings):
        side1, side2 = sewing.side1, sewing.side2
        try:
            info = describe_first_stitch(sewing)
        except Exception as error:
            info = f"stitch data failed: {type(error).__name__}: {error}"
        log(f"    sewing[{index}] side1 pos {side1.pos1}->{side1.pos2} rev={side1.reverse} | "
            f"side2 pos {side2.pos1}->{side2.pos2} rev={side2.reverse} | {info}")

    log("--- click combinations: which end does the first stitch land on?")
    pattern = project.patterns[0]
    sewn = sewn_edge_uuids(project)
    free = [edge for edge in pattern.edges if edge.global_uuid not in sewn]
    if len(free) < 4:
        log("    not enough free edges")
        return
    edge1, edge2 = free[0], free[1]

    def point_at(edge, fraction):
        points = edge.render_points
        return points[int(round(fraction * (len(points) - 1)))]

    for label, (fraction1, fraction2) in (("start-start", (0.1, 0.1)),
                                          ("start-end", (0.1, 0.9)),
                                          ("end-start", (0.9, 0.1)),
                                          ("end-end", (0.9, 0.9))):
        clicked1 = point_at(edge1, fraction1)
        clicked2 = point_at(edge2, fraction2)
        sewing = project.add_sewing1to1_from_points(edge1, clicked1, edge2, clicked2)
        if sewing is None:
            log(f"    {label:<12} FAILED: {project.last_sewing_error}")
            continue
        side1, side2 = sewing.side1, sewing.side2
        try:
            check = describe_first_stitch(sewing)
        except Exception as error:
            check = f"stitch data failed: {type(error).__name__}: {error}"
        log(f"    {label:<12} side1 pos {side1.pos1}->{side1.pos2} rev={side1.reverse} | "
            f"side2 pos {side2.pos1}->{side2.pos2} rev={side2.reverse} | {check}")
        project.sewings.remove(len(project.sewings) - 1)
        project.calc_all_sewings_sections()


def describe_first_stitch(sewing):
    """Which end of its edge each side's first stitch sits on."""
    parts = []
    for pattern_index, edge in ((0, sewing.side1.line1), (1, sewing.side2.line1)):
        first, _ = stitch_end_positions(sewing, pattern_index)
        points = np.asarray(edge.render_points, dtype=np.float64)
        start = points[0][:2]
        end = points[-1][:2]
        to_start = float(np.linalg.norm(first - start))
        to_end = float(np.linalg.norm(first - end))
        where = "start" if to_start < to_end else "end"
        parts.append(f"side{pattern_index + 1} first stitch on the {where} "
                     f"({to_start:.1f} / {to_end:.1f} mm)")
    return "; ".join(parts)


def segment_crosses(p1, p2, p3, p4):
    """Do the two segments cross (proper intersection)?"""
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1 = orient(p3, p4, p1)
    d2 = orient(p3, p4, p2)
    d3 = orient(p1, p2, p3)
    d4 = orient(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def check_display_pairing(project):
    """Old display pairing vs the pairing the engine actually stitches."""
    from qmyi.model.sewing import calc_sewing_side_render_points

    log("--- pairing: display (low-low / high-high) vs the stitches the engine gets")
    for index, sewing in enumerate(project.sewings[:4]):
        side1, side2 = sewing.side1, sewing.side2
        points1 = np.asarray(calc_sewing_side_render_points(side1), dtype=np.float64)
        points2 = np.asarray(calc_sewing_side_render_points(side2), dtype=np.float64)
        a0, a1 = points1[0][:2], points1[-1][:2]
        b0, b1 = points2[0][:2], points2[-1][:2]
        first1, _ = stitch_end_positions(sewing, 0)
        first2, _ = stitch_end_positions(sewing, 1)
        a_first = a0 if np.linalg.norm(first1 - a0) < np.linalg.norm(first1 - a1) else a1
        b_first = b0 if np.linalg.norm(first2 - b0) < np.linalg.norm(first2 - b1) else b1
        a_last = a1 if a_first is a0 else a0
        b_last = b1 if b_first is b0 else b0
        display_cross = segment_crosses(a0, b0, a1, b1)
        stitch_cross = segment_crosses(a_first, b_first, a_last, b_last)
        log(f"    sewing[{index}] side1 pos {side1.pos1}->{side1.pos2} rev={side1.reverse} | "
            f"side2 pos {side2.pos1}->{side2.pos2} rev={side2.reverse}")
        log(f"        first stitch on {'low' if a_first is a0 else 'high'} end of side1, "
            f"{'low' if b_first is b0 else 'high'} end of side2")
        log(f"        display pairing (low-low/high-high) crosses: {display_cross}")
        log(f"        engine pairing (first-first/last-last) crosses: {stitch_cross}")


def check_preview_matches_render(project, edges):
    """The hover preview must be the connector pair the created sewing draws."""
    from qmyi.gizmos.sewing_renderer import stitch_connector_points
    from qmyi.model.qianyi_project import edge_point_at, sewing_half_directions
    from qmyi.model.sewing import calc_sewing_side_render_points

    edge1, edge2 = edges
    log("--- preview lines vs the connectors the sewing is drawn with")
    for label, (fraction1, fraction2) in (("same end (start, start)", (0.1, 0.1)),
                                          ("different ends (start, end)", (0.1, 0.9))):
        check_preview_for_click_pair(project, edge1, edge2, label, fraction1, fraction2)


def check_preview_for_click_pair(project, edge1, edge2, label, fraction1, fraction2):
    from qmyi.gizmos.sewing_renderer import stitch_connector_points
    from qmyi.model.qianyi_project import edge_point_at, sewing_half_directions
    from qmyi.model.sewing import calc_sewing_side_render_points

    def point_at(edge, fraction):
        points = edge.render_points
        return points[int(round(fraction * (len(points) - 1)))]

    click1 = point_at(edge1, fraction1)
    click2 = point_at(edge2, fraction2)
    sewing = project.add_sewing1to1_from_points(edge1, click1, edge2, click2)
    if sewing is None:
        log(f"    {label}: could not create the sewing: {project.last_sewing_error}")
        return
    points1 = np.asarray(calc_sewing_side_render_points(sewing.side1), dtype=np.float64)
    points2 = np.asarray(calc_sewing_side_render_points(sewing.side2), dtype=np.float64)
    connectors = stitch_connector_points(panel_of(sewing.side1.line1), points1,
                                         panel_of(sewing.side2.line1), points2)
    drawn_ends = [connectors[0], connectors[1], connectors[-2], connectors[-1]]
    first_half, second_half = sewing_half_directions(edge1, click1, edge2, click2)
    preview = [
        panel_of(edge1).pattern_to_view_pos(edge_point_at(edge1, first_half[0])),
        panel_of(edge2).pattern_to_view_pos(edge_point_at(edge2, second_half[0])),
        panel_of(edge1).pattern_to_view_pos(edge_point_at(edge1, first_half[1])),
        panel_of(edge2).pattern_to_view_pos(edge_point_at(edge2, second_half[1])),
    ]
    distances = [float(np.linalg.norm(np.array(drawn) - np.array(shown)))
                 for drawn, shown in zip(drawn_ends, preview)]
    log(f"    {label}: side1 {sewing.side1.pos1}->{sewing.side1.pos2} "
        f"rev={sewing.side1.reverse} | side2 {sewing.side2.pos1}->{sewing.side2.pos2} "
        f"rev={sewing.side2.reverse}")
    log(f"        preview vs drawn: max {max(distances):.6f} mm "
        f"({[round(value, 4) for value in distances]})")
    log(f"        first connector {tuple(round(float(v), 2) for v in drawn_ends[0][:2])} -> "
        f"{tuple(round(float(v), 2) for v in drawn_ends[1][:2])}")
    log(f"    side1 pos {sewing.side1.pos1}->{sewing.side1.pos2} rev={sewing.side1.reverse} | "
        f"side2 pos {sewing.side2.pos1}->{sewing.side2.pos2} rev={sewing.side2.reverse}")
    project.sewings.remove(len(project.sewings) - 1)
    project.calc_all_sewings_sections()


def check_half_variants(project, edges):
    """What each (pos1, pos2, reverse) combination does to one half.

    A half that walks the long way round the pattern shows up as many sections
    instead of one, so this says whether a combination is usable at all.
    """
    from qmyi.model.sewing import calc_sewing_side_sections

    edge1, edge2 = edges
    edge_length = float(np.linalg.norm(
        np.asarray(edge1.render_points)[0][:2] - np.asarray(edge1.render_points)[-1][:2]))
    log("--- one half: position range / reverse -> sections covered "
        f"(edge {edge_length:.1f} mm between its ends)")
    variants = (
        ("pos 0->1, reverse=False", 0.0, 1.0, False),
        ("pos 0->1, reverse=True ", 0.0, 1.0, True),
        ("pos 1->0, reverse=True ", 1.0, 0.0, True),
        ("pos 1->0, reverse=False", 1.0, 0.0, False),
    )
    for label, pos1, pos2, reverse in variants:
        sewing = project.add_sewing(edge1, pos1, edge1, pos2, reverse,
                                    edge2, 0.0, edge2, 1.0, False)
        if sewing is None:
            log(f"    {label}: rejected ({project.last_sewing_error})")
            continue
        side = sewing.side1
        sections, lengths, _ = calc_sewing_side_sections(side, [None, None], side.reverse)
        covered = float(np.sum(np.abs(lengths))) if len(lengths) else 0.0
        log(f"    {label}: sections={len(sections)} "
            f"total length={covered * edge_length:.1f} mm")
        project.sewings.remove(len(project.sewings) - 1)
        project.calc_all_sewings_sections()


def check_click_crossing(project, edges):
    """For each click order: do the two end connectors cross each other?"""
    from qmyi.gizmos.sewing_renderer import stitch_connector_points
    from qmyi.model.sewing import calc_sewing_side_render_points

    edge1, edge2 = edges
    log(f"--- click order -> crossing? (edges {edge1.global_uuid} / {edge2.global_uuid})")

    def point_at(edge, fraction):
        points = edge.render_points
        return points[int(round(fraction * (len(points) - 1)))]

    for label, (fraction1, fraction2) in (("first/first", (0.1, 0.1)),
                                          ("first/second", (0.1, 0.9)),
                                          ("second/first", (0.9, 0.1)),
                                          ("second/second", (0.9, 0.9))):
        sewing = project.add_sewing1to1_from_points(
            edge1, point_at(edge1, fraction1), edge2, point_at(edge2, fraction2))
        if sewing is None:
            log(f"    {label:<14} rejected: {project.last_sewing_error}")
            continue
        points1 = np.asarray(calc_sewing_side_render_points(sewing.side1), dtype=np.float64)
        points2 = np.asarray(calc_sewing_side_render_points(sewing.side2), dtype=np.float64)
        connectors = stitch_connector_points(panel_of(sewing.side1.line1), points1,
                                             panel_of(sewing.side2.line1), points2)
        first_pair = (connectors[0][:2], connectors[1][:2])
        last_pair = (connectors[-2][:2], connectors[-1][:2])
        crosses = segment_crosses(first_pair[0], first_pair[1], last_pair[0], last_pair[1])
        log(f"    {label:<14} side2 {sewing.side2.pos1}->{sewing.side2.pos2} "
            f"rev={sewing.side2.reverse} | connectors cross: {crosses}")
        project.sewings.remove(len(project.sewings) - 1)
        project.calc_all_sewings_sections()


def main():
    import_addon(ADDON_PATH, "qmyi")
    from qmyi import global_data
    from qmyi import model
    from qmyi.model import model_data
    from qmyi.utilities.node_tree import get_all_node_tree

    global_data.renderers_enabled = False
    model.register()
    model_data.refresh_all_uuids()
    project = get_all_node_tree()[0]
    log(f"start: {link_state(project)}")

    pattern = project.patterns[0]
    sewn = sewn_edge_uuids(project)
    free = [edge for edge in pattern.edges if edge.global_uuid not in sewn]
    log(f"pattern[0]: edges={len(pattern.edges)} sewn={len(sewn)} free={len(free)}")
    if len(free) < 4:
        log("not enough free edges on pattern[0] for the test")

    # First, because it needs untouched edges: what the physics really pairs.
    check_stitch_order(project)
    check_display_pairing(project)
    if len(free) >= 4:
        check_half_variants(project, free[2:4])
        # Real sewings join two different patterns; a pair of neighbouring
        # edges of one pattern has a different notion of "crossing".
        if len(project.patterns) > 1:
            pattern2 = project.patterns[1]
            free2 = [edge for edge in pattern2.edges
                     if edge.global_uuid not in sewn_edge_uuids(project)]
            if free2:
                check_click_crossing(project, [free[2], free2[0]])
        check_click_crossing(project, free[2:4])
    check_preview_matches_render(project, free[0:2] if len(free) >= 2 else [])

    try_add(project, "first add (fresh sections)", free[0:2])
    if len(free) >= 4:
        try_add(project, "second add (sections carry the previous link ids)", free[2:4])
    if len(free) >= 8:
        log("--- color and connector lines")
        check_colors_and_connectors(project, free[4:6], free[6:8])
        check_direction(project, free[8:10] if len(free) >= 10 else free[4:6])

    log("--- deleting pattern[1] (which owns two sewings), then adding again")
    target = project.patterns[1] if len(project.patterns) > 1 else pattern
    try:
        project.remove_patterns([target])
    except Exception:
        log("    remove_patterns raised:")
        traceback.print_exc()
    log(f"    {link_state(project)}")
    pattern = project.patterns[0]
    sewn = sewn_edge_uuids(project)
    free = [edge for edge in pattern.edges if edge.global_uuid not in sewn]
    if len(free) >= 2:
        try_add(project, "add after deletion", free[0:2])
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
