"""Where a sewing half runs, and what a pointer can snap to while drawing one.

A half is a run of a pattern's outline: from a place on one edge to a place on
another, with the direction it was drawn in. A place is stored as a fraction of
its own edge's length (`SewingOneSide.pos1` / `pos2`) - a relative length - so
everything here that measures converts through the edge lengths and answers in
millimetres.

Work therefore happens in one absolute space: the distance around the outline,
from the start of its first edge. `outline_origin` puts a stored place in it,
`outline_place` answers what a distance lands on, and `run_from` walks one
distance of the outline into the polyline a half is drawn as. A run that would
be longer than the outline is refused rather than wrapping onto itself.
"""

from __future__ import annotations

import numpy as np

from ..utilities.curve_fit import polyline_length, slice_by_arc_length


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


def outline_length(pattern) -> float:
    """How long a pattern's outline is, in millimetres."""
    return float(sum(float(edge.length or 0.0) for edge in pattern.edges))


def outline_origin(pattern, edge, pos) -> float:
    """Where a stored place sits, as a distance around the whole outline."""
    index = edge_index(pattern, edge)
    if index < 0:
        raise ValueError("this edge is not part of the pattern's outline")
    distance = 0.0
    for before in range(index):  # loop: one edge in front of it per step
        distance += float(pattern.edges[before].length or 0.0)
    return distance + float(pos) * float(edge.length or 0.0)


def outline_place(pattern, distance) -> tuple:
    """What a distance around the outline lands on: ``(edge, pos, point)``."""
    total = outline_length(pattern)
    if total <= 0.0:
        raise ValueError("this pattern's outline has no length to walk")
    distance = float(distance) % total
    walked = 0.0
    for edge in pattern.edges:  # loop: one edge per step around the outline
        length = float(edge.length or 0.0)
        if length > 0.0 and distance <= walked + length:
            pos = min(max((distance - walked) / length, 0.0), 1.0)
            return edge, pos, point_on_edge(edge, pos)
        walked += length
    last = pattern.edges[-1]
    return last, 1.0, point_on_edge(last, 1.0)


def nearest_outline_distance(pattern, point) -> float:
    """The distance around the outline of the place closest to a point.

    A snap candidate is a place in the pattern's own space - a vertex, or the end
    of a sewing half - and a seam stores places as distances around the outline,
    so a candidate is measured against every edge and answered in that space.
    """
    point = np.asarray(point, dtype=np.float64)
    best = None
    walked = 0.0
    for edge in pattern.edges:  # loop: one edge per comparison
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
        raise ValueError("this pattern's outline has no samples to measure against")
    return float(best[1])


def outline_step(pattern, from_distance, to_distance) -> float:
    """The signed distance from one place on the outline to another, the short way."""
    total = outline_length(pattern)
    step = float(to_distance) - float(from_distance)
    if total <= 0.0:
        return step
    return step - total * round(step / total)


def run_from(pattern, start_distance, travel) -> dict:
    """The run a drag of `travel` millimetres from a place on the outline makes.

    The travel is signed: a negative one runs the other way round the outline.
    The answer carries the polyline in the order it was drawn, its length, the
    two places a seam records for it, and the point the run ends on. A run
    longer than the outline is refused - there would be no way to say which way
    round it went twice.
    """
    total = outline_length(pattern)
    if total <= 0.0:
        raise ValueError("this pattern's outline has no length to draw on")
    travel = float(travel)
    if abs(travel) > total:
        raise ValueError("a half cannot be longer than the outline it runs on")
    start_edge, start_pos, _start_point = outline_place(pattern, start_distance)
    end_edge, end_pos, end_point = outline_place(pattern, float(start_distance) + travel)
    forward = travel >= 0.0
    pieces = []
    remaining = abs(travel)
    distance = float(start_distance)
    guard = 0
    while remaining > 1e-9 and guard <= len(pattern.edges) + 1:
        guard += 1
        edge, pos, _point = outline_place(pattern, distance)
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


def side_places(pattern, side) -> tuple:
    """Where a stored side of a seam begins and how far it runs: (from, travel)."""
    line1, line2 = side.line1, side.line2
    if line1 is None or line2 is None:
        raise ValueError("this sewing side names an edge that is no longer in the scene")
    return run_span(pattern, line1, side.pos1, line2, side.pos2, side.reverse)


def run_span(pattern, line1, pos1, line2, pos2, reverse) -> tuple:
    """The span of the outline a run covers: ``(from, travel)`` in millimetres.

    The run is read from the place it starts at, and `travel` is signed - it is
    negative when the run goes the other way round the outline. The stored
    places are relative lengths on their own edges, so they are turned into
    distances around the whole outline here, which is the space every comparison
    between two runs uses.
    """
    start = outline_origin(pattern, line1, pos1)
    end = outline_origin(pattern, line2, pos2)
    travel = end - start
    total = outline_length(pattern)
    if total > 0.0:
        travel -= total * round(travel / total)
        if reverse and travel > 0.0:
            travel -= total
        elif not reverse and travel < 0.0:
            travel += total
    return start, travel


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


def snap_candidates(project, pattern, exclude_side_uuid=None) -> list:
    """The places a drawn half may snap to on one pattern.

    The pattern's own outline vertices, and the two ends of every sewing half made
    on this pattern. Each source is read on its own, so a half never offers its
    own ends back to itself, while an end that is also a vertex is still there
    because the vertex put it there. Returns ``(point, kind, side_uuid)``, kind
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

    for vertex in pattern.vertices:  # loop: one outline point per entry
        add(vertex.co, "vertex", None)
    for sewing in getattr(project, "sewings", ()):  # loop: one seam per entry
        for side in (sewing.side1, sewing.side2):
            pattern_of_side = side.pattern
            if pattern_of_side is None or pattern_of_side.global_uuid != pattern.global_uuid:
                continue
            if exclude_side_uuid is not None and side.global_uuid == exclude_side_uuid:
                continue
            try:
                for line, pos in ((side.line1, side.pos1), (side.line2, side.pos2)):
                    add(point_on_edge(line, pos), "sewing", side.global_uuid)
            except ValueError:
                continue
    return entries
