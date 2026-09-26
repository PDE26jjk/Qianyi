"""Where a sewing half runs, and what a pointer can snap to while drawing one.

A half is a run of a chain: from a place on one edge to a place on another, with
the direction it was drawn in. The chain is the outline a pattern reads - closed,
so a run may go round it and come back - or one internal line, which is open
unless it was drawn as a loop: a run on an open chain stays between its ends and
turns round rather than wrapping past them.

A place is stored as a fraction of its own edge's length (`SewingOneSide.pos1` /
`pos2`) - a relative length - so everything here that measures converts through
the edge lengths and answers in millimetres.

Work therefore happens in one space per chain: the distance along it, from the
start of its first edge. `run_of` names the chain an edge belongs to,
`run_origin` puts a stored place in it, `run_place` answers what a distance lands
on, and `run_from` walks one distance of it into the polyline a half is drawn as.
A run that would be longer than its chain, or leave an open one, is refused
rather than wrapping onto itself.
"""

from __future__ import annotations

import numpy as np

from ..utilities.curve_fit import polyline_length, slice_by_arc_length


def run_of(line):
    """The chain an edge runs along: its pattern's outline, or its internal line.

    An edge knows what holds it - the Sketch for outline edges, the internal line
    for the pieces of one - and that holder is what a run between two of its edges
    is measured in. Several patterns read one Sketch, so the answer is the chain
    itself and not a member: the outline is shared, and so is the distance.
    """
    return line.get_parent()


def run_edges(run):
    """The edges of a chain, in the order it runs."""
    return run.edges


def run_is_loop(run) -> bool:
    """Whether a chain closes on itself.

    A pattern's outline always does; an internal line says so itself, because a
    pen may draw one that comes back to where it started.
    """
    return bool(getattr(run, "is_loop", True))


def run_is_internal(run) -> bool:
    """Whether a chain is an internal line rather than an outline."""
    return hasattr(run, "is_loop")


def run_key(run) -> int:
    """The identity of a chain, for the session records that name one.

    An outline is shared by every pattern of a chain, so a pattern answers with
    the Sketch it reads: two members of one chain, and the Sketch itself, all name
    that one outline. An internal line is its own.
    """
    if run_is_internal(run):
        return int(run.global_uuid)
    sketch_uuid = int(getattr(run, "sketch_uuid", -1))
    return sketch_uuid if sketch_uuid != -1 else int(run.global_uuid)


def edge_index(pattern, edge) -> int:
    """Where an edge sits in a pattern's outline, or -1 when it is not one."""
    for index in range(len(pattern.edges)):  # loop: one outline edge per check
        if pattern.edges[index].global_uuid == edge.global_uuid:
            return index
    return -1


def edge_samples(edge) -> tuple:
    """One edge's own draw points, and the distance along them of each sample."""
    points = np.asarray(edge.render_points, dtype=np.float64)
    if len(points) < 2:
        return np.zeros((0, 2)), np.zeros(0)
    steps = np.concatenate(([0.0], np.cumsum(
        np.linalg.norm(np.diff(points, axis=0), axis=1))))
    return points, steps


def point_on_edge(edge, pos) -> np.ndarray:
    """The point at a relative length along one edge, in the pattern's space."""
    points, steps = edge_samples(edge)
    if len(points) == 0:
        raise ValueError("this edge has no curve to place a point on")
    total = float(steps[-1])
    distance = min(max(float(pos), 0.0), 1.0) * total
    return np.array((np.interp(distance, steps, points[:, 0]),
                     np.interp(distance, steps, points[:, 1])), dtype=np.float64)


def run_length(run) -> float:
    """How long a chain is, in millimetres."""
    return float(sum(float(edge.length or 0.0) for edge in run_edges(run)))


def run_origin(run, edge, pos) -> float:
    """Where a stored place sits, as a distance along the whole chain."""
    edges = run_edges(run)
    index = next((index for index in range(len(edges))
                  if edges[index].global_uuid == edge.global_uuid), -1)
    if index < 0:
        raise ValueError("this edge is not part of the chain it is stored in")
    distance = 0.0
    for before in range(index):  # loop: one edge in front of it per step
        distance += float(edges[before].length or 0.0)
    return distance + float(pos) * float(edge.length or 0.0)


def run_place(run, distance) -> tuple:
    """What a distance along the chain lands on: ``(edge, pos, point)``.

    A closed chain wraps: its own length and zero are the same place. An open
    chain has ends, so a distance outside it is not a place on it at all, and it
    is refused here - that is what keeps a run on an internal line inside the
    line instead of wrapping past its end.
    """
    edges = run_edges(run)
    total = run_length(run)
    if total <= 0.0:
        raise ValueError("this chain has no length to walk")
    distance = float(distance)
    if run_is_loop(run):
        distance %= total
    elif distance < -1e-6 or distance > total + 1e-6:
        raise ValueError("that place is past the end of the chain")
    distance = min(max(distance, 0.0), total)
    walked = 0.0
    for edge in edges:  # loop: one edge per step along the chain
        length = float(edge.length or 0.0)
        if length > 0.0 and distance <= walked + length:
            pos = min(max((distance - walked) / length, 0.0), 1.0)
            return edge, pos, point_on_edge(edge, pos)
        walked += length
    last = edges[-1]
    return last, 1.0, point_on_edge(last, 1.0)


def run_nearest_distance(run, point) -> float:
    """The distance along the chain of the place closest to a point.

    A snap candidate is a place in the pattern's own space - a vertex, or the end
    of a sewing half - and a seam stores places as distances along the chain, so
    a candidate is measured against every edge of it and answered in that space.
    """
    point = np.asarray(point, dtype=np.float64)
    best = None
    walked = 0.0
    for edge in run_edges(run):  # loop: one edge per comparison
        points, steps = edge_samples(edge)
        if len(points) == 0:
            continue
        starts = points[:-1]
        deltas = points[1:] - starts
        squares = (deltas * deltas).sum(axis=1)
        ratios = np.clip(((point - starts) * deltas).sum(axis=1)
                         / np.where(squares > 0.0, squares, 1.0), 0.0, 1.0)
        spots = starts + deltas * ratios[:, None]
        nearest = int(np.argmin(((spots - point) ** 2).sum(axis=1)))
        at = float(steps[nearest] + ratios[nearest] * float(np.sqrt(squares[nearest])))
        away = float(np.linalg.norm(spots[nearest] - point))
        if best is None or away < best[0]:
            best = (away, walked + at)
        walked += float(steps[-1])
    if best is None:
        raise ValueError("this chain has no samples to measure against")
    return float(best[1])


def run_place_under(context, project, pointer_region, pixels) -> tuple:
    """The place on a chain under the pointer: ``(pattern, run, distance, point)``.

    The outline comes from the project's own edge finder, which is the search the
    rest of the editor snaps with, and answers with the place nearest the pointer
    rather than the place the pointer is exactly on - what a click on a thin line
    needs. An internal line is measured here, from its own pieces: it is a handful
    of segments, and reading them directly keeps the sewing tools independent of
    the finder's snapshot, which the point tools are the ones that need. Whichever
    answers nearer to the pointer wins, and a pointer further than `pixels` from
    the nearest chain has no place on one at all. The pattern comes with the
    answer because that is what draws the chain and what a preview is built in.
    """
    from ..utilities.coords_transform import region2view_coord

    if pointer_region is None:
        return None
    view = np.asarray(region2view_coord(context, pointer_region), dtype=np.float64)
    best = None

    def consider(pattern, run, point, distance, away):
        nonlocal best
        if best is None or away < best[0]:
            best = (away, pattern, run, point, distance)

    def drawn_away(pattern, point):
        """How far a place of a pattern is from the pointer, on screen."""
        return float(np.linalg.norm(np.asarray(pattern.view_points([point])[0],
                                               dtype=np.float64) - view))

    project.find_nearest_point_on_edge(view)
    if project.nearest_point is not None and project.nearest_pattern is not None:
        try:
            pattern, edge, point, fraction = project.get_nearest_point_data()
            run = run_of(edge)
            consider(pattern, run, np.asarray(point, dtype=np.float64),
                     run_origin(run, edge, fraction), drawn_away(pattern, point))
        except (ValueError, KeyError):
            # The snapshot went stale between the search and the read; the next
            # move asks again.
            pass

    for pattern in project.patterns:  # loop: one pattern's lines per step
        local = np.asarray(pattern.view_to_pattern_pos(view), dtype=np.float64)
        for line in pattern.internal_lines:  # loop: one internal line per step
            for edge in run_edges(line):  # loop: one piece of that line
                points, steps = edge_samples(edge)
                if len(points) < 2:
                    continue
                starts = points[:-1]
                deltas = points[1:] - starts
                squares = (deltas * deltas).sum(axis=1)
                ratios = np.clip(((local - starts) * deltas).sum(axis=1)
                                 / np.where(squares > 0.0, squares, 1.0), 0.0, 1.0)
                spots = starts + deltas * ratios[:, None]
                nearest = int(np.argmin(((spots - local) ** 2).sum(axis=1)))
                point = spots[nearest]
                walked = float(steps[nearest] + ratios[nearest]
                               * float(np.sqrt(squares[nearest])))
                total = float(steps[-1])
                fraction = min(max(walked / total, 0.0), 1.0) if total > 0.0 else 0.0
                consider(pattern, line, point, run_origin(line, edge, fraction),
                         drawn_away(pattern, point))

    if best is None:
        return None
    away, pattern, run, point, distance = best
    if away > snap_radius(context, pattern, pointer_region, pixels):
        return None
    return pattern, run, float(distance), np.asarray(point, dtype=np.float64)


def run_step(run, from_distance, to_distance) -> float:
    """The signed distance from one place on the chain to another.

    A closed chain is measured the short way round - the pointer never crosses
    more than half of it between two frames. An open chain has no other way, so
    the answer is simply the difference.
    """
    if not run_is_loop(run):
        return float(to_distance) - float(from_distance)
    total = run_length(run)
    step = float(to_distance) - float(from_distance)
    if total <= 0.0:
        return step
    return step - total * round(step / total)


def run_travel(run, tail_distance, head_distance, direction) -> float:
    """How far a run goes from its tail to its head, the way `direction` names.

    On a closed chain the run is the arc between the two ends in the direction it
    runs in - the direction it was drawn in - not the shorter of the two arcs, so
    its length wraps at the place where the two ends meet: an end dragged past the
    other one keeps going and lays the run the long way round, which is how a seam
    spans almost the whole outline. `direction` is +1 for the chain's own way
    round and -1 for the other; the answer carries the same sign.

    An open chain has one way between two places, so there is nothing to wrap: the
    answer is signed by which end is which, and an end dragged past the other one
    turns the run round instead of making it span the chain.
    """
    if not run_is_loop(run):
        return float(head_distance) - float(tail_distance)
    total = run_length(run)
    travel = (float(head_distance) - float(tail_distance)) * float(direction)
    if total > 0.0:
        travel -= total * np.floor(travel / total)
    return float(direction) * travel


def run_from(run, start_distance, travel) -> dict:
    """The run a drag of `travel` millimetres from a place on the chain makes.

    The travel is signed: a negative one runs the other way along the chain. The
    answer carries the polyline in the order it was drawn, its length, the two
    places a seam records for it, and the point the run ends on. A run longer than
    its chain - or one that would leave an open chain - is refused.
    """
    total = run_length(run)
    if total <= 0.0:
        raise ValueError("this chain has no length to draw on")
    travel = float(travel)
    if abs(travel) > total:
        raise ValueError("a half cannot be longer than the chain it runs on")
    start_edge, start_pos, _start_point = run_place(run, start_distance)
    end_edge, end_pos, end_point = run_place(run, float(start_distance) + travel)
    forward = travel >= 0.0
    pieces = []
    remaining = abs(travel)
    distance = float(start_distance)
    guard = 0
    while remaining > 1e-9 and guard <= len(run_edges(run)) + 1:
        guard += 1
        edge, pos, _point = run_place(run, distance)
        length = float(edge.length or 0.0)
        if length <= 0.0:
            distance += 1e-6 if forward else -1e-6
            continue
        room = (1.0 - pos) * length if forward else pos * length
        step = min(remaining, room)
        if step <= 1e-9:
            # The place sits exactly on a vertex: step over it rather than
            # asking the same edge for another nothing-long piece.
            distance += 1e-6 if forward else -1e-6
            continue
        to_pos = pos + step / length if forward else pos - step / length
        points, steps = edge_samples(edge)
        piece = slice_by_arc_length(points, min(pos, to_pos) * length,
                                    max(pos, to_pos) * length)
        pieces.append(piece if forward else piece[::-1])
        remaining -= step
        distance += step if forward else -step
    if not pieces:
        raise ValueError("this run covers nothing")
    polyline = pieces[0] if len(pieces) == 1 else np.vstack(pieces)
    return {"polyline": np.asarray(polyline, dtype=np.float64),
            "length": abs(travel), "reverse": not forward,
            "start_edge": start_edge, "start_pos": start_pos,
            "end_edge": end_edge, "end_pos": end_pos, "end_point": end_point}


def side_run(side) -> tuple:
    """What a stored side of a seam runs on, and where: ``(run, from, travel)``.

    The chain comes from the edge the side names, so a side made on an internal
    line is read in the internal line's own space. `travel` is signed - negative
    when the run goes the other way - and on a closed chain it is the arc the
    stored flag names: the run is read the way it was drawn, which can be nearly
    the whole outline. An open chain has one way between two places, so the travel
    is simply the distance from one end to the other and the run turns round
    rather than wrapping when an end passes the other.
    """
    line1, line2 = side.line1, side.line2
    if line1 is None or line2 is None:
        raise ValueError("this sewing side names an edge that is no longer in the scene")
    run = run_of(line1)
    start = run_origin(run, line1, side.pos1)
    end = run_origin(run, line2, side.pos2)
    if not run_is_loop(run):
        return run, start, end - start
    travel = end - start
    total = run_length(run)
    if total > 0.0:
        travel -= total * round(travel / total)
        if side.reverse and travel > 0.0:
            travel -= total
        elif not side.reverse and travel < 0.0:
            travel += total
    return run, start, travel


def snap_radius(context, pattern, pointer_region, pixels=None) -> float:
    """How far, in the pattern's own millimetres, a snap reaches at this zoom.

    The threshold belongs to the screen: that many pixels of it, measured at the
    pointer and taken through the pattern's transform, so zooming in makes the
    snap finer rather than larger. The pointer comes in region pixels - the space
    a mouse event reports - because that is what the conversion needs; a view
    position would have to be turned back into pixels first, and that is exactly
    the step that used to be left out.
    """
    from ..utilities.snap import SNAP_PIXELS

    if pixels is None:
        pixels = SNAP_PIXELS
    region = getattr(context, "region", None)
    if region is None or pointer_region is None:
        return 0.0
    try:
        view = region.view2d.region_to_view(float(pointer_region[0]),
                                            float(pointer_region[1]))
        beside = region.view2d.region_to_view(float(pointer_region[0]) + pixels,
                                              float(pointer_region[1]))
        here = np.asarray(pattern.view_to_pattern_pos(view), dtype=np.float64)
        there = np.asarray(pattern.view_to_pattern_pos(beside), dtype=np.float64)
    except Exception:
        return 0.0
    return float(np.linalg.norm(there - here))


def nearest_candidate(context, pattern, pointer, entries, radius=None):
    """The snap candidate closest to the pointer, or None when none is close.

    `pointer` is a view-space position and `entries` is what `snap_candidates`
    answered. The distance is measured in the pattern's own space - the space the
    radius is in - by taking the pointer through the pattern's inverse transform,
    so a mirrored or scaled member compares where its points really are.
    """
    if radius is None:
        radius = snap_radius(context, pattern, pointer)
    if radius <= 0.0 or not entries:
        return None
    here = np.asarray(pattern.view_to_pattern_pos(pointer), dtype=np.float64)
    best = None
    for point, kind, uuid_value in entries:  # loop: one candidate per compare
        distance = float(np.linalg.norm(np.asarray(point, dtype=np.float64) - here))
        if best is None or distance < best[0]:
            best = (distance, point, kind, uuid_value)
    if best is None or best[0] > radius:
        return None
    return best


def run_points(run) -> list:
    """A chain's own points, in the pattern's space.

    A pattern's outline has a vertex per corner; an internal line has the places
    its pieces meet, which are the sketch vertices its edges were built from, plus
    the far end of its last piece when it does not close.
    """
    if hasattr(run, "vertices"):
        return [vertex.co for vertex in run.vertices]
    edges = run_edges(run)
    points = [edge.vertex0.co for edge in edges]
    if not run_is_loop(run) and edges:
        points.append(edges[-1].vertex1.co)
    return points


def run_candidates(project, run, exclude_side_uuid=None) -> list:
    """The places a drawn half may snap to on one chain.

    The chain's own points, and the two ends of every sewing half made on that
    same chain. Each source is read on its own, so a half never offers its own ends
    back to itself, while an end that is also a point of the chain is still there
    because the chain put it there. Returns ``(point, kind, side_uuid)``, kind
    being ``"vertex"`` or ``"sewing"``.
    """
    entries = []
    seen = set()

    def add(point, kind, uuid_value):
        key = (round(float(point[0]), 4), round(float(point[1]), 4))
        if key in seen:
            return
        seen.add(key)
        entries.append((np.asarray(point, dtype=np.float64), kind, uuid_value))

    for point in run_points(run):  # loop: one point of the chain per entry
        add(point, "vertex", None)
    for sewing in getattr(project, "sewings", ()):  # loop: one seam per entry
        for side in (sewing.side1, sewing.side2):
            if side.line1 is None:
                continue
            if run_key(run_of(side.line1)) != run_key(run):
                continue
            if exclude_side_uuid is not None and side.global_uuid == exclude_side_uuid:
                continue
            try:
                for line, pos in ((side.line1, side.pos1), (side.line2, side.pos2)):
                    add(point_on_edge(line, pos), "sewing", side.global_uuid)
            except ValueError:
                continue
    return entries
