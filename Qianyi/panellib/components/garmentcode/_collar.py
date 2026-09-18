"""Neckline shape helpers and the hood panel from GarmentCode's ``collars.py``.

The neckline functions build the edge sequence that GarmentCode later projects
into the bodice corner; the hood panel uses them only for the opening lengths.
"""

from __future__ import annotations

import math

from ...curves import Arc, Bezier
from ._kernel import (NCurve, Segment, arc_segments_through, line_segment,
                      quad_segment, rel_to_abs_2d, split_segment,
                      curve_match_tangents)


def chain_length(segments) -> float:
    """Total arc length of a segment chain."""
    # Deliberate comprehension: one length per Python segment object.
    return sum(_segment_length(segment) for segment in segments)


def _segment_length(segment) -> float:
    points = [segment.p0]
    if isinstance(segment.curve, Bezier):
        points += list(segment.curve.controls)
    elif isinstance(segment.curve, Arc):
        geometry = segment.curve.geometry(segment.p0, segment.p1)
        if geometry is None:
            return math.dist(segment.p0, segment.p1)
        return abs(geometry[1] * geometry[3])
    points.append(segment.p1)
    return NCurve(cps=points).length()


def split_chain(segments, distance: float):
    """Split a segment chain at an arc-length distance from its start."""
    first, second = [], []
    cursor = 0.0
    done = False
    for segment in segments:
        if done:
            second.append(segment)
            continue
        length = _segment_length(segment)
        if cursor + length <= distance + 1e-12:
            first.append(segment)
            cursor += length
            if cursor >= distance - 1e-12:
                done = True
            continue
        fraction = 0.0 if length <= 1e-12 else (distance - cursor) / length
        left, right = split_segment(segment, fraction)
        first.append(left)
        second.append(right)
        done = True
    return first, second


def arc_parameters(segments):
    """``(radius, positive_angle)`` of the first arc in a chain, or None."""
    for segment in segments:
        if isinstance(segment.curve, Arc):
            geometry = segment.curve.geometry(segment.p0, segment.p1)
            if geometry is not None:
                return geometry[1], abs(geometry[3])
    return None


def neckline_half(kind: str, depth: float, width: float, angle: float = 90.0,
                  flip: bool = False, x: float = 0.5, y: float = 0.3):
    """One half of a GarmentCode neckline shape, as a segment chain."""
    kind = (kind or "").strip()
    start = (0.0, 0.0)
    end = (width / 2.0, -depth)
    if kind in ("V", "VNeckHalf"):
        return [line_segment(start, end)]
    if kind in ("Square", "SquareNeckHalf"):
        middle = (0.0, -depth)
        return [line_segment(start, middle), line_segment(middle, end)]
    if kind in ("Trapezoid", "TrapezoidNeckHalf"):
        radians = math.radians(angle)
        if abs(math.sin(radians)) <= 1e-9:
            return [line_segment(start, end)]
        bottom_x = -depth * math.cos(radians) / math.sin(radians)
        if bottom_x > width / 2.0:
            return [line_segment(start, end)]
        middle = (bottom_x, -depth)
        return [line_segment(start, middle), line_segment(middle, end)]
    if kind in ("Curvy", "CurvyNeckHalf"):
        sign = -1.0 if flip else 1.0
        control_1 = rel_to_abs_2d(start, end, (0.4, sign * 0.3))
        control_2 = rel_to_abs_2d(start, end, (0.8, sign * -0.3))
        return [Segment(start, end, Bezier(controls=(control_1, control_2)))]
    if kind in ("CircleArc", "CircleArcNeckHalf"):
        arc_angle = math.radians(angle)
        to_sum = arc_angle > math.pi
        if to_sum:
            arc_angle = 2.0 * math.pi - arc_angle
        radius = 1.0 / math.sin(arc_angle / 2.0) / 2.0
        height = 1.0 / math.tan(arc_angle / 2.0) / 2.0
        control_y = radius + height if to_sum else radius - height
        control_y *= -1.0 if not flip else 1.0
        return arc_segments_through(start, end,
                                    rel_to_abs_2d(start, end, (0.5, control_y)))
    if kind in ("Circle", "CircleNeckHalf"):
        full = arc_segments_through((0.0, 0.0), (width, 0.0), (width / 2.0, -depth))
        return split_chain(full, chain_length(full) / 2.0)[0]
    if kind in ("Bezier2", "Bezier2NeckHalf"):
        sign = 1.0 if flip else -1.0
        control = rel_to_abs_2d(start, end, (x, sign * y))
        return [quad_segment(start, end, control)]
    return neckline_half("CircleArc", depth, width, angle=angle, flip=flip)


def hood_spec(name, front_depth, back_depth, front_length, back_length,
              width, inside_length, depth):
    """GarmentCode's ``HoodPanel`` (one panel)."""
    half = width / 2.0
    length = inside_length + half / 2.0

    back_start = (-half, -back_depth)
    back_end = (0.0, 0.0)
    back_1 = rel_to_abs_2d(back_start, back_end, (0.3, -0.2))
    back_2 = rel_to_abs_2d(back_start, back_end, (0.6, 0.2))
    matched_back = curve_match_tangents(
        [back_start, back_1, back_2, back_end], (1.0, 0.0), (1.0, 0.0),
        target_len=back_length)
    bottom_back = Segment(tuple(matched_back[0]), tuple(matched_back[3]),
                          Bezier(controls=(tuple(matched_back[1]), tuple(matched_back[2]))))

    front_end = (half, -front_depth)
    front_1 = rel_to_abs_2d(bottom_back.p1, front_end, (0.3, 0.2))
    front_2 = rel_to_abs_2d(bottom_back.p1, front_end, (0.6, -0.2))
    matched_front = curve_match_tangents(
        [bottom_back.p1, front_1, front_2, front_end], (1.0, 0.0), (1.0, 0.0),
        target_len=front_length)
    bottom_front = Segment(tuple(matched_front[0]), tuple(matched_front[3]),
                           Bezier(controls=(tuple(matched_front[1]),
                                            tuple(matched_front[2]))))

    corner = (half * 1.2, length)
    inner = (half * 1.2 - depth, length)
    closing_control = rel_to_abs_2d(inner, tuple(matched_back[0]), (0.2, -0.5))
    closing = quad_segment(inner, tuple(matched_back[0]), closing_control)

    segments = [bottom_back, bottom_front,
                line_segment(bottom_front.p1, corner),
                line_segment(corner, inner),
                closing]
    return segments
