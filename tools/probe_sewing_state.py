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
        pattern1 = explicit.side1.line1.pattern
        pattern2 = explicit.side2.line1.pattern
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

    try_add(project, "first add (fresh sections)", free[0:2])
    if len(free) >= 4:
        try_add(project, "second add (sections carry the previous link ids)", free[2:4])
    if len(free) >= 8:
        log("--- color and connector lines")
        check_colors_and_connectors(project, free[4:6], free[6:8])

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
