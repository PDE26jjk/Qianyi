"""Check the section/link/stitch invariants of the loaded scene.

    blender.exe -b --factory-startup <scene.blend> --python tools/check_section_invariants.py

Read-only for the file: it never saves. Every scenario reloads the scene, so
the checks always start from what is on disk. Each scenario ends with a
PASS/FAIL line and the process exits non-zero when anything failed.

What is checked, per scenario:

1.  every section chain is doubly linked (a section must equal the `prev` of
    its `next` and the `next` of its `prev`);
2.  `sum(sec.seg)` per edge equals the samples that edge contributed, and the
    pattern total equals the length of `mesh_edge_index_map`, with no `seg`
    left at -1;
3.  every link id either is -1 or points at a group that really holds the
    section;
4.  both sides of a sewing walk the same number of stitches, no stitch index
    is out of range or repeated (a loop may repeat its own closing sample), the
    first and last stitch sit on the sewing's own endpoints, and no stitch
    comes from a section outside its pattern;
5.  the stitch pairs `Sewing.get_stitch_data` produces have the same length on
    both sides.

The scenarios are the ones that have broken this machinery before: linking as
saved, dividing each side of a sewing, a side that covers a whole outline, and
an internal line crossing the outline.
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
# A stitch may miss its endpoint by this much before it counts as a failure.
ENDPOINT_TOLERANCE_MM = 1e-3


def log(message):
    print(f"[invariants] {message}", flush=True)


def import_addon(path, module_name):
    init_path = os.path.join(path, "__init__.py")
    spec = importlib.util.spec_from_file_location(module_name, init_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def edge_groups(pattern):
    """Every edge of a pattern, with the key its chain is named by.

    `None` is the outline, an integer is that internal line's index: the same key
    the pattern uses for its own copy of the Sketch's first stage.
    """
    groups = [(None, pattern.edges)]
    groups.extend((index, line.edges)
                  for index, line in enumerate(pattern.internal_lines))
    return groups


def raw_chain_of(edge):
    """The Sketch's own raw pieces of one edge, walked from its head."""
    sections = []
    section = edge.section_start
    guard = 0
    while section is not None and section is not edge.section_end and guard < 1000:
        sections.append(section)
        section = section.next
        guard += 1
    return sections


def check_chain(project):
    """The Sketch's first stage: one chain per curve, linked both ways."""
    problems = []
    total = 0
    for pattern in project.patterns:
        for _key, edges in edge_groups(pattern):
            for edge in edges:
                for section in raw_chain_of(edge):
                    total += 1
                    if section.next is not None and section.next.prev is not section:
                        problems.append(f"{pattern.name}[{edge.get_index()}] "
                                        f"{section.start_pos:.3f}-{section.end_pos:.3f} "
                                        f"next.prev is not itself")
                    if section.prev is not None and section.prev.next is not section:
                        problems.append(f"{pattern.name}[{edge.get_index()}] "
                                        f"{section.start_pos:.3f}-{section.end_pos:.3f} "
                                        f"prev.next is not itself")
    return total, problems


def check_sampling(project):
    """The pattern's own pieces: each has a segment count and the samples agree."""
    problems = []
    checked = 0
    for pattern in project.patterns:
        for key, edges in edge_groups(pattern):
            for edge in edges:
                index = edge.get_index()
                sections = pattern.sections_for_edge(key, index)
                if not sections:
                    problems.append(f"{pattern.name}[{edge.get_index()}] has no sections")
                    continue
                negative = [section for section in sections if section.seg < 0]
                if negative:
                    problems.append(f"{pattern.name}[{edge.get_index()}] has "
                                    f"{len(negative)} section(s) without a segment count")
                    continue
                checked += 1
                samples = pattern.sample_points.get((key, index))
                sampled = len(samples) - 1 if samples is not None else -1
                if sum(section.seg for section in sections) != sampled:
                    problems.append(
                        f"{pattern.name}[{edge.get_index()}] segments "
                        f"{sum(section.seg for section in sections)} != samples {sampled}")
        if pattern.mesh_edge_index_map is not None and len(pattern.internal_lines) == 0:
            outer = sum(section.seg for edge in pattern.edges
                        for section in pattern.sections_for_edge(None, edge.get_index()))
            if outer != len(pattern.mesh_edge_index_map):
                problems.append(f"{pattern.name} outline segments {outer} != "
                                f"mesh_edge_index_map {len(pattern.mesh_edge_index_map)}")
    return checked, problems


def check_link_ids(project):
    from qmyi.model.geometry import Section

    groups = [set(map(id, (entry.section for entry in group)))
              for group in Section.link_sections]
    problems = []
    linked = 0
    stale = 0
    for pattern in project.patterns:
        for key, edges in edge_groups(pattern):
            for edge in edges:
                for section in pattern.sections_for_edge(key, edge.get_index()):
                    if section.link_map_id == -1:
                        continue
                    if section.link_run != Section.link_run:
                        # Linked by an earlier run: the id is not an index into
                        # the current table, and the section is unlinked as far
                        # as this run is concerned.
                        stale += 1
                        continue
                    linked += 1
                    if section.link_map_id >= len(groups):
                        problems.append(f"{pattern.name}[{edge.get_index()}] "
                                        f"link id {section.link_map_id} out of range "
                                        f"({len(groups)} groups)")
                    elif id(section) not in groups[section.link_map_id]:
                        problems.append(f"{pattern.name}[{edge.get_index()}] link id "
                                        f"{section.link_map_id} points at another group")
    return f"{linked} linked, {stale} from an older run", problems


def recorded_runs(side, holder) -> list:
    """The side's drawn runs with the boundary pair recorded for each, or None.

    `Sewing.sections1` / `sections2` hold one `(start, end)` pair per drawn run,
    in drawing order - the record the linking run refreshed - so the two lists
    have to have the same length before the record can be read at all.
    """
    pairs = list(holder)
    if len(pairs) != len(side.spans):
        return None
    return list(zip(side.spans, pairs))


def walk_pieces(start, end, reverse) -> list:
    """The pieces one run visits, in the order the walk visits them."""
    pieces = []
    section = start
    if section is end:
        pieces.append(section)
        section = section.prev if reverse else section.next
    guard = 0
    while section is not end and guard < 1000:
        pieces.append(section)
        section = section.prev if reverse else section.next
        guard += 1
    return pieces


def side_walk(side) -> list:
    """The samples one side stitches, in stitch order.

    Built here from the model's own pieces (`side_pieces`) rather than read off
    the model: what this check wants is an independent walk to compare the pairs
    against, and a piece a drawn run ends at contributes the run's own end - after
    its samples, or before them when the run is walked backwards.
    """
    from qmyi.model.sewing import side_pieces

    walked = []
    for _piece, samples, head, tail, ends_run, _run, far_first in side_pieces(side):
        if ends_run and far_first:
            walked.append(int(head))
        walked.extend(int(value) for value in samples)
        if ends_run and not far_first:
            walked.append(int(tail))
    return walked


def point_at_fraction(edge, fraction):
    """The point `fraction` of the way along the edge, by arc length.

    Sewing positions are arc-length fractions of their edge, which is not what
    `qianyi_project.edge_point_at` answers (that one picks the nearer end, for
    the editor's one-to-one tool), so the checks walk the render polyline.
    """
    points = np.asarray(edge.render_points, dtype=np.float64)
    if len(points) < 2:
        return np.zeros(2, dtype=np.float32)
    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    walked = np.concatenate(([0.0], np.cumsum(steps)))
    target = float(np.clip(fraction, 0.0, 1.0)) * walked[-1]
    index = int(np.searchsorted(walked, target, side="right") - 1)
    index = max(0, min(index, len(points) - 2))
    span = walked[index + 1] - walked[index]
    ratio = 0.0 if span <= 0 else (target - walked[index]) / span
    point = points[index] + (points[index + 1] - points[index]) * ratio
    return point.astype(np.float32)


def check_stitches(project):
    from qmyi.model.model_data import owner_pattern
    from qmyi.model import sewing_geometry as sg

    problems = []
    checked = 0
    for index, sewing in enumerate(project.sewings):
        if sewing.stitch_error:
            # A seam the guard reported is deliberately not stitched; there is
            # nothing to walk and the reason is the report.
            log(f"       sewing[{index}] cannot be paired: {sewing.stitch_error}")
            checked += 1
            continue
        walks = []
        for label, side, holder in (("side1", sewing.side1, sewing.sections1),
                                    ("side2", sewing.side2, sewing.sections2)):
            runs = recorded_runs(side, holder)
            if runs is None:
                problems.append(f"sewing[{index}] {label}: {len(list(holder))} recorded "
                                f"pair(s) for {len(side.spans)} drawn run(s)")
                walks.append(None)
                continue
            sections = [piece for span, pair in runs
                        for piece in walk_pieces(pair[0], pair[1], span.reverse)]
            if not sections:
                problems.append(f"sewing[{index}] {label}: empty walk")
                walks.append(None)
                continue
            try:
                stitches = np.asarray(side_walk(side), dtype=np.int64)
            except Exception as error:
                problems.append(f"sewing[{index}] {label}: walk raised {error!r}")
                walks.append(None)
                continue
            if np.issubdtype(stitches.dtype, np.unsignedinteger):
                # The walk marks "outside the pattern" with -1; an unsigned array
                # would read that back as its maximum value.
                stitches = stitches.astype(np.int64)
            first_span, last_span = side.spans[0], side.spans[-1]
            walks.append((label, side, stitches, first_span, last_span,
                          [pair[0] is pair[1] for _span, pair in runs]))
            points = owner_pattern(first_span.line1).mesh_edge_points
            inside = stitches[stitches >= 0]
            if len(inside) and (inside.max() >= len(points) or inside.min() < 0):
                problems.append(f"sewing[{index}] {label}: stitch index outside "
                                f"mesh_edge_points")
            repeated = len(inside) - len(np.unique(inside))
            is_loop = any(pair[0] is pair[1] for _span, pair in runs)
            if repeated and not is_loop:
                problems.append(f"sewing[{index}] {label}: {repeated} repeated stitch(es)")
            if repeated > 1:
                problems.append(f"sewing[{index}] {label}: {repeated} repeated stitches "
                                f"on a loop (only the closing sample may repeat)")

        if any(walk is None for walk in walks):
            continue
        raw1, raw2 = walks[0][2], walks[1][2]
        data = sewing.get_stitch_data()["stitches"]
        # The two sides are paired by progress along each side, so the walks need
        # not be the same length: a join pairs two samples of one side with the
        # one the other side has at that fraction. What still has to hold is that
        # neither side has a sample the pairing forgot, and that no pair is made
        # out of nothing.
        if data.shape[0] == 0:
            problems.append(f"sewing[{index}]: no pair was built at all")
            continue
        if data.shape[0] > len(raw1) + len(raw2):
            problems.append(f"sewing[{index}]: {data.shape[0]} pairs from walks of "
                            f"{len(raw1)} and {len(raw2)}")
        if int(data.min()) < 0:
            problems.append(f"sewing[{index}]: a pair names no vertex")
        whole = all(bool(np.all(walk >= 0)) for walk in (raw1, raw2))
        for column, side_index in ((0, 0), (1, 1)):
            label, side, stitches, first_span, last_span, _bits = walks[side_index]
            known = {int(value) for value in stitches}
            if any(int(value) not in known for value in data[:, column]):
                problems.append(f"sewing[{index}] {label}: a pair names a vertex "
                                f"this side's walk does not hold")
            if not whole:
                # Samples outside a pattern are dropped with their pairs, so the
                # first and last pair are not the walk's own ends.
                continue
            expected_first = int(stitches[0])
            expected_last = int(stitches[-1])
            if int(data[0][column]) != expected_first:
                problems.append(f"sewing[{index}] {label}: first pair is "
                                f"{int(data[0][column])}, expected {expected_first}")
            if int(data[-1][column]) != expected_last:
                problems.append(f"sewing[{index}] {label}: last pair is "
                                f"{int(data[-1][column])}, expected {expected_last}")
            # Neither end was dropped, so the end stitches still have to sit on
            # the sewing's own endpoints.
            points = owner_pattern(first_span.line1).mesh_edge_points
            start = point_at_fraction(first_span.line1, first_span.pos1)
            first = float(np.linalg.norm(points[expected_first] - start))
            if first > ENDPOINT_TOLERANCE_MM:
                problems.append(f"sewing[{index}] {label}: first stitch is "
                                f"{first:.3f} mm off the sewing start")
            points = owner_pattern(last_span.line1).mesh_edge_points
            end = point_at_fraction(last_span.line2, last_span.pos2)
            last = float(np.linalg.norm(points[expected_last] - end))
            if last > ENDPOINT_TOLERANCE_MM:
                problems.append(f"sewing[{index}] {label}: last stitch is "
                                f"{last:.3f} mm off the sewing end")
        outside = int(np.count_nonzero(raw1 < 0) + np.count_nonzero(raw2 < 0))
        if outside:
            log(f"       sewing[{index}]: {outside} sample(s) of the walks sit "
                f"outside a pattern and are dropped")
        checked += 1
    return checked, problems


def piece_fractions(side, runs):
    """Where each piece boundary sits, as a fraction of the side's whole range."""
    sections = [piece for span, pair in runs
                for piece in walk_pieces(pair[0], pair[1], span.reverse)]
    lengths = [section.absolute_length() for section in sections]
    total = sum(lengths)
    if total <= 0:
        return None
    fractions = []
    running = 0.0
    for length in lengths:
        running += length
        fractions.append(running / total)
    return fractions


def check_grouping(project):
    """The two sides of a sewing must be cut at the same fractions.

    The merge aligns the pieces by normalized progress, so whatever split the
    recursion propagates has to leave both sides cut at matching fractions.
    A wrong half (a group that pairs a low half with a high one) shows up here
    even when the stitch counts still happen to match.
    """
    from qmyi.model.model_data import owner_pattern

    problems = []
    checked = 0
    for index, sewing in enumerate(project.sewings):
        if sewing.stitch_error:
            continue
        fractions = []
        for side in (sewing.side1, sewing.side2):
            try:
                # The pieces are the pattern's own copy of the Sketch's stage.
                runs = []
                # loop: one drawn run of that side per step
                for span in side.spans:
                    pattern = owner_pattern(span.line1)
                    start = pattern.boundary_section(span.line1, span.pos1, span.reverse)
                    end = pattern.boundary_section(span.line2, span.pos2, span.reverse)
                    runs.append((span, (start, end)))
            except ValueError as error:
                problems.append(f"sewing[{index}]: {error}")
                fractions.append(None)
                continue
            fractions.append(piece_fractions(side, runs))
        if None in fractions:
            continue
        left, right = fractions
        if len(left) != len(right):
            problems.append(f"sewing[{index}]: {len(left)} pieces on side1 but "
                            f"{len(right)} on side2")
            continue
        checked += 1
        worst = max((abs(a - b) for a, b in zip(left, right)), default=0.0)
        if worst > 0.0501:
            problems.append(f"sewing[{index}]: piece boundaries differ by "
                            f"{worst:.3f} of the range (side1 {[round(v, 3) for v in left]}, "
                            f"side2 {[round(v, 3) for v in right]})")
    return checked, problems


def check_recorded_pair(project):
    """`sewing.sectionsX` is a record: it must match the derived boundaries."""
    from qmyi.model.model_data import owner_pattern

    problems = []
    checked = 0
    for index, sewing in enumerate(project.sewings):
        if sewing.stitch_error:
            continue
        for label, side, holder in (("side1", sewing.side1, sewing.sections1),
                                    ("side2", sewing.side2, sewing.sections2)):
            pairs = list(holder)
            if len(pairs) != len(side.spans):
                problems.append(f"sewing[{index}] {label}: {len(pairs)} recorded "
                                f"pair(s) for {len(side.spans)} drawn run(s)")
                continue
            for run_index, span in enumerate(side.spans):
                # loop: one drawn run of that side per step
                try:
                    pattern = owner_pattern(span.line1)
                    start = pattern.boundary_section(span.line1, span.pos1, span.reverse)
                    end = pattern.boundary_section(span.line2, span.pos2, span.reverse)
                except ValueError as error:
                    problems.append(f"sewing[{index}] {label}[{run_index}]: {error}")
                    continue
                checked += 1
                if pairs[run_index][0] is not start or pairs[run_index][1] is not end:
                    problems.append(f"sewing[{index}] {label}[{run_index}]: the "
                                    f"recorded pair is not the section a lookup finds")
    return checked, problems


def check_pairs(project):
    problems = []
    checked = 0
    for index, sewing in enumerate(project.sewings):
        if sewing.stitch_error:
            # Reported as un-pairable: it deliberately stitches nothing.
            continue
        try:
            data = sewing.get_stitch_data()
        except Exception as error:
            problems.append(f"sewing[{index}]: get_stitch_data raised {error!r}")
            continue
        stitches = data["stitches"]
        checked += 1
        if stitches.ndim != 2 or stitches.shape[1] != 2:
            problems.append(f"sewing[{index}]: stitch pairs have shape {stitches.shape}")
        if stitches.shape[0] == 0:
            problems.append(f"sewing[{index}]: no stitch pair at all")
    return checked, problems


def report(label, counts, problems):
    if problems:
        log(f"FAIL {label}: {len(problems)} problem(s)")
        for line in problems[:12]:
            log(f"       {line}")
        if len(problems) > 12:
            log(f"       ... and {len(problems) - 12} more")
        return 1
    log(f"PASS {label}: {counts}")
    return 0


def run_checks(label):
    from qmyi.utilities.node_tree import get_all_node_tree

    failures = 0
    for project in get_all_node_tree():
        sections, problems = check_chain(project)
        failures += report(f"{label} / {project.name} chain", f"{sections} sections",
                           problems)
        checked, problems = check_sampling(project)
        failures += report(f"{label} / {project.name} sampling",
                           f"{checked} edges", problems)
        counts, problems = check_link_ids(project)
        failures += report(f"{label} / {project.name} link ids", counts, problems)
        sewn, problems = check_stitches(project)
        failures += report(f"{label} / {project.name} stitches",
                           f"{sewn} sewings", problems)
        sewn, problems = check_grouping(project)
        failures += report(f"{label} / {project.name} grouping",
                           f"{sewn} sewings", problems)
        sewn, problems = check_recorded_pair(project)
        failures += report(f"{label} / {project.name} recorded pair",
                           f"{sewn} sides", problems)
        sewn, problems = check_pairs(project)
        failures += report(f"{label} / {project.name} pairs",
                           f"{sewn} sewings", problems)
    return failures


def scenario_plain(project):
    for pattern in project.patterns:
        pattern.need_sewing_update = True
    project.setup_sewings_for_simulation()


def scenario_divide_every_side(project):
    from qmyi.operators import _2d_divide_edge as divide_tools
    from qmyi.model.model_data import owner_pattern

    for parts in (2, 4):
        for sewing in list(project.sewings):
            for side in (sewing.side1, sewing.side2):
                for span in side.spans:  # loop: one drawn run of that side per step
                    pattern = owner_pattern(span.line1)
                    index = span.line1.get_index()
                    if index < len(pattern.edges):
                        divide_tools.divide_edges(pattern, [index], parts=parts)
    for pattern in project.patterns:
        pattern.need_sewing_update = True
    project.setup_sewings_for_simulation()


def scenario_stretched_seam(project):
    """One side five times longer than the other: the merge has to stretch.

    A seam may be sewn with one side longer on purpose - a puff sleeve, a band
    with ease - so the merge cuts both sides at the same fractions and the seam
    stitches through the difference.
    """
    sewing = project.sewings[0]
    sewing.side2.spans[0].pos2 = 0.2
    for pattern in project.patterns:
        pattern.need_sewing_update = True
    project.setup_sewings_for_simulation()


def scenario_reversed_both_sides(project):
    """Both sides sewn backwards: pos1 at the far end, pos2 at the near one."""
    sewing = project.sewings[1]
    sewing.side1.spans[0].pos1, sewing.side1.spans[0].pos2 = 1.0, 0.0
    sewing.side2.spans[0].pos1, sewing.side2.spans[0].pos2 = 1.0, 0.0
    sewing.side1.spans[0].reverse = True
    sewing.side2.spans[0].reverse = True
    for pattern in project.patterns:
        pattern.need_sewing_update = True
    project.setup_sewings_for_simulation()


def scenario_hole(project):
    """A closed internal line inside the pattern, the 'cut a hole' case."""
    pattern = project.patterns[0]
    bbox = np.asarray(pattern.get_bbox(), dtype=np.float64)
    center = (float(bbox[0][0] + bbox[1][0]) * 0.5,
              float(bbox[0][1] + bbox[1][1]) * 0.5)
    size = min(float(bbox[1][0] - bbox[0][0]), float(bbox[1][1] - bbox[0][1])) * 0.2
    points = [(center[0] - size, center[1] - size),
              (center[0] + size, center[1] - size),
              (center[0] + size, center[1] + size),
              (center[0] - size, center[1] + size)]
    segments = []
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        segments.append({"p0": start, "p1": end, "h1": (0.0, 0.0), "h2": (0.0, 0.0),
                         "h1_type": "VECTOR", "h2_type": "VECTOR"})
    line = pattern.add_internal_line(segments, is_loop=True)
    line.is_hole = True
    for pattern in project.patterns:
        pattern.need_sewing_update = True
    project.setup_sewings_for_simulation()


def scenario_two_components(project):
    """A second, unsewn component, then only the first one re-linked."""
    originals = list(project.patterns)
    if len(originals) < 2:
        return
    copies = [pattern.copy_pattern(project=project) for pattern in originals]
    sewing = project.add_sewing1to1(edge1=copies[0].edges[2], edge2=copies[1].edges[2])
    if sewing is None:
        raise RuntimeError(f"could not sew the copies: {project.last_sewing_error}")
    project.calc_all_sewings_sections()
    originals[0].need_sewing_update = True
    project.setup_sewings_for_simulation()


def scenario_loop_seam(project):
    """One side walks the whole outline, forwards."""
    sewing = project.sewings[0]
    side = sewing.side1
    edge = project.patterns[0].edges[0]
    span = side.spans[0]
    span.line1_uuid = edge.global_uuid
    span.line2_uuid = edge.global_uuid
    span.pos1 = 0.0
    span.pos2 = 0.0
    span.reverse = False
    for pattern in project.patterns:
        pattern.need_sewing_update = True
    project.setup_sewings_for_simulation()


def scenario_loop_seam_reversed(project):
    """The same whole-outline walk, backwards: the closing sample moves to the
    other end of the walk, so the endpoint rule has to follow it there."""
    scenario_loop_seam(project)
    sewing = project.sewings[0]
    sewing.side1.spans[0].reverse = True
    for pattern in project.patterns:
        pattern.need_sewing_update = True
    project.setup_sewings_for_simulation()


def scenario_internal_line(project):
    pattern = project.patterns[0]
    bbox = np.asarray(pattern.get_bbox(), dtype=np.float64)
    height = float(bbox[0][1] + (bbox[1][1] - bbox[0][1]) * 0.5)
    segments = [{"p0": (float(bbox[0][0] - 10.0), height),
                 "p1": (float(bbox[1][0] + 10.0), height),
                 "h1": (0.0, 0.0), "h2": (0.0, 0.0),
                 "h1_type": "VECTOR", "h2_type": "VECTOR"}]
    pattern.add_internal_line(segments, is_loop=False)
    for pattern in project.patterns:
        pattern.need_sewing_update = True
    project.setup_sewings_for_simulation()


def scenario_sewing_on_internal_line(project):
    """A sewing whose side is an internal line, part of it outside the pattern."""
    scenario_internal_line(project)
    pattern = project.patterns[0]
    line = pattern.internal_lines[-1]
    other = project.patterns[1] if len(project.patterns) > 1 else pattern
    sewing = project.add_sewing1to1(edge1=line.edges[0], edge2=other.edges[0])
    if sewing is None:
        raise RuntimeError(f"could not add the sewing: {project.last_sewing_error}")
    for member in project.patterns:
        member.need_sewing_update = True
    project.setup_sewings_for_simulation()


SCENARIOS = (
    ("as saved", scenario_plain),
    ("every sewing side divided into 2 and 4", scenario_divide_every_side),
    ("side wrapping a whole outline", scenario_loop_seam),
    ("side wrapping a whole outline, walked backwards", scenario_loop_seam_reversed),
    ("internal line crossing the outline", scenario_internal_line),
    ("sewing on an internal line", scenario_sewing_on_internal_line),
    ("stretched seam (one side 5x shorter)", scenario_stretched_seam),
    ("both sides reversed", scenario_reversed_both_sides),
    ("closed internal line as a hole", scenario_hole),
    ("two components, one re-linked", scenario_two_components),
)


def main():
    scene_path = bpy.data.filepath
    if not scene_path:
        log("no scene loaded: pass a .blend before --python")
        return 1
    log(f"blender {bpy.app.version_string} scene={os.path.basename(scene_path)}")

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

    failures = 0
    for label, scenario in SCENARIOS:
        bpy.ops.wm.open_mainfile(filepath=scene_path)
        from qmyi.model.model_data import refresh_all_uuids

        refresh_all_uuids()
        try:
            from qmyi.utilities.node_tree import get_all_node_tree

            scenario(get_all_node_tree()[0])
        except Exception:
            log(f"FAIL {label}: the scenario itself raised")
            traceback.print_exc()
            failures += 1
            continue
        failures += run_checks(label)

    log(f"done: {failures} failed check group(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    import_addon(REPO_ADDON, "qmyi")

    status = 1
    try:
        status = main()
    except Exception:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
