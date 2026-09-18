"""Shared panel builders used by several GarmentCode presets."""

from __future__ import annotations

import math

from ._common import CM_TO_MM, polygon_cm
from ._kernel import (arc_segments, arc_segments_through, line_segment,
                      segments_to_panel)


def circle_arc_spec(name, top_rad, length, angle):
    """GarmentCode's ``CircleArcPanel``: two arcs joined by two straight sides."""
    half_arc = angle / 2.0
    dist_w = 2.0 * top_rad * math.sin(half_arc)
    dist_out = 2.0 * (top_rad + length) * math.sin(half_arc)
    vertical = length * math.cos(half_arc)

    top_start = (-dist_w / 2.0, 0.0)
    top_end = (dist_w / 2.0, 0.0)
    right_end = (dist_out / 2.0, -vertical)
    bottom_end = (-dist_out / 2.0, -vertical)

    segments = []
    segments += arc_segments(top_start, top_end, top_rad, half_arc > math.pi / 2, True)
    segments.append(line_segment(top_end, right_end))
    segments += arc_segments(right_end, bottom_end, top_rad + length,
                             half_arc > math.pi / 2, False)
    segments.append(line_segment(bottom_end, top_start))
    return segments_to_panel(name, segments, scale=CM_TO_MM)


def straight_band(name, width, depth):
    """GarmentCode's ``StraightBandPanel`` as a ``PanelSpec``."""
    return polygon_cm(name, [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)])


def circle_arc_from_all_length(name, length, top_width, bottom_width):
    """``CircleArcPanel.from_all_length`` (FittedWB panels).

    A vanishing difference degrades to a straight band instead of dividing by
    zero. Negative differences are not produced by the fitted waistband, whose
    top width is always narrower than its bottom width, but a negative radius
    would not be representable; fall back to the straight band there too.
    """
    difference = bottom_width - top_width
    if abs(difference) <= 1e-9 or length <= 1e-9 or top_width <= 1e-9:
        return polygon_cm(name, [(0.0, 0.0), (top_width, 0.0),
                                 (top_width, length), (0.0, length)])
    arc = difference / length
    radius = top_width / arc
    if radius <= 1e-9:
        return polygon_cm(name, [(0.0, 0.0), (top_width, 0.0),
                                 (top_width, length), (0.0, length)])
    return circle_arc_spec(name, radius, length, arc)


def circle_arc_from_w_length_suns(name, length, top_width, sun_fraction):
    """``CircleArcPanel.from_w_length_suns`` (circle skirt panels)."""
    angle = sun_fraction * 2.0 * math.pi
    if abs(angle) <= 1e-9 or top_width <= 1e-9:
        return polygon_cm(name, [(0.0, 0.0), (top_width, 0.0),
                                 (top_width, length), (0.0, length)])
    return circle_arc_spec(name, top_width / angle, length, angle)


def asym_half_circle_spec(name, top_rad, length_front, length_side):
    """GarmentCode's ``AsymHalfCirclePanel``."""
    dist_w = 2.0 * top_rad
    dist_out = 2.0 * (top_rad + length_side)

    top_start = (-dist_w / 2.0, 0.0)
    top_end = (dist_w / 2.0, 0.0)
    right_end = (dist_out / 2.0, 0.0)
    bottom_end = (-dist_out / 2.0, 0.0)
    apex = (0.0, -(top_rad + length_front))

    segments = []
    segments += arc_segments(top_start, top_end, top_rad, False, True)
    segments.append(line_segment(top_end, right_end))
    segments += arc_segments_through(right_end, bottom_end, apex)
    segments.append(line_segment(bottom_end, top_start))
    return segments_to_panel(name, segments, scale=CM_TO_MM)


def thin_skirt_spec(name, top_width, bottom_width, length, bottom_curvature=0.0):
    """GarmentCode's ``ThinSkirtPanel`` (panel-skirt piece with a curved hem)."""
    flare = (bottom_width - top_width) / 2.0
    p0 = (0.0, 0.0)
    p1 = (flare, length)
    p2 = (flare + top_width, length)
    p3 = (flare * 2.0 + top_width, 0.0)

    segments = [line_segment(p0, p1), line_segment(p1, p2), line_segment(p2, p3)]
    if abs(bottom_curvature) <= 1e-9:
        segments.append(line_segment(p3, p0))
    else:
        segments += arc_segments_through(p3, p0, (0.5, bottom_curvature), relative=True)
    return segments_to_panel(name, segments, scale=CM_TO_MM)
