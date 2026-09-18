"""Sleeve preset, transcribed from GarmentCode's ``sleeves.py``.

Source classes: ``ArmholeCurve`` and ``SleevePanel``. One sleeve panel is
produced; mirror it for the other arm. Only panel geometry is ported: the
front/back opening equalisation, cuffs and placement are left out.
"""

from __future__ import annotations

import math

from ...curves import Bezier, Line
from ._common import CM_TO_MM
from ._kernel import (NCurve, Segment, curve_match_tangents, line_segment,
                      rel_to_abs_2d, segments_to_panel)

COMPONENT_ID = "gc_sleeve"
VERSION = 1
LABEL = "GC Sleeve"
CATEGORY = "GarmentCode"
DESCRIPTION = ("GarmentCode fitted sleeve panel with the classic curved "
               "armhole opening; mirror it for the other arm.")

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "armhole_incline": {"type": "float", "unit": "cm", "min": 0.0, "max": 30.0,
                            "default": 1.0, "label": "Armhole Incline"},
        "connecting_width": {"type": "float", "unit": "cm", "min": 2.0, "max": 60.0,
                             "default": 18.44, "label": "Connecting Width"},
        "shoulder_incl": {"type": "float", "unit": "deg", "min": 0.0, "max": 60.0,
                          "default": 21.6777, "label": "Shoulder Inclination"},
        "sleeve_angle": {"type": "float", "unit": "deg", "min": 0.0, "max": 80.0,
                         "default": 10.0, "label": "Sleeve Angle"},
        "arm_length": {"type": "float", "unit": "cm", "min": 20.0, "max": 120.0,
                       "default": 53.9697, "label": "Arm Length"},
        "wrist": {"type": "float", "unit": "cm", "min": 5.0, "max": 40.0,
                  "default": 16.5945, "label": "Wrist"},
        "sleeve_length": {"type": "float", "unit": "x", "min": 0.1, "max": 1.15,
                          "default": 0.3, "label": "Length"},
        "end_width": {"type": "float", "unit": "x", "min": 0.2, "max": 2.0,
                      "default": 1.0, "label": "End Width"},
        "opening_dir_mix": {"type": "float", "unit": "fraction", "min": -0.9, "max": 0.8,
                            "default": 0.1, "label": "Opening Direction Mix"},
        "standing_shoulder": {"type": "bool", "default": False,
                              "label": "Standing Shoulder"},
        "standing_shoulder_len": {"type": "float", "unit": "cm", "min": 4.0, "max": 10.0,
                                  "default": 5.0, "label": "Standing Shoulder Length"},
    },
}


def _rotate(point, centre, angle):
    cosine, sine = math.cos(angle), math.sin(angle)
    x, y = point[0] - centre[0], point[1] - centre[1]
    return (centre[0] + cosine * x - sine * y, centre[1] + sine * x + cosine * y)


def _normalize(vector):
    length = math.hypot(vector[0], vector[1])
    return (0.0, 0.0) if length <= 1e-12 else (vector[0] / length, vector[1] / length)


def _translate(segment, delta):
    dx, dy = delta
    p0 = (segment.p0[0] + dx, segment.p0[1] + dy)
    p1 = (segment.p1[0] + dx, segment.p1[1] + dy)
    if isinstance(segment.curve, Bezier):
        curve = Bezier(controls=tuple((c[0] + dx, c[1] + dy)
                                      for c in segment.curve.controls))
    else:
        curve = Line()
    return Segment(p0, p1, curve)


def armhole_shapes(incline, width, angle, direction_mix):
    """GarmentCode's ``ArmholeCurve``: ``(projection, opening)`` segments."""
    start = (incline, width)
    end = (0.0, 0.0)
    control_1 = rel_to_abs_2d(start, end, (0.5, 0.2))
    control_2 = rel_to_abs_2d(start, end, (0.8, 0.35))
    edge_length = NCurve(cps=[start, control_1, control_2, end]).length()

    chord = math.dist(start, end)
    inverse_end = (start[0], start[1] - chord)
    inverse_1 = rel_to_abs_2d(start, inverse_end, (0.5, 0.2))
    inverse_2 = rel_to_abs_2d(start, inverse_end, (0.8, -0.35))
    inverse_end = _rotate(inverse_end, start, -angle)
    inverse_1 = _rotate(inverse_1, start, -angle)
    inverse_2 = _rotate(inverse_2, start, -angle)

    direction = _normalize((inverse_end[0] - start[0], inverse_end[1] - start[1]))
    down = (0.0, -1.0)
    left = (-1.0, 0.0)
    if direction_mix > 0.0:
        target = ((1.0 - direction_mix) * direction[0] + direction_mix * down[0],
                  (1.0 - direction_mix) * direction[1] + direction_mix * down[1])
    else:
        target = ((1.0 - direction_mix) * direction[0] + (-direction_mix) * left[0],
                  (1.0 - direction_mix) * direction[1] + (-direction_mix) * left[1])

    matched = curve_match_tangents(
        [start, inverse_1, inverse_2, inverse_end], down, target, target_len=edge_length)
    # The projection is the original edge reversed; the opening is the
    # reversed matched curve. Both swap their control-point order.
    projection = Segment(end, start, Bezier(controls=(control_2, control_1)))
    opening = Segment(tuple(matched[3]), tuple(matched[0]),
                      Bezier(controls=(tuple(matched[2]), tuple(matched[1]))))
    return projection, opening


def armhole_opening(incline, width, angle, direction_mix):
    """The sleeve-side opening of ``ArmholeCurve``."""
    return armhole_shapes(incline, width, angle, direction_mix)[1]


def _sleeve_panel(name, opening, params):
    shoulder_angle = math.radians(float(params["shoulder_incl"]))
    rest_angle = max(math.radians(float(params["sleeve_angle"])), shoulder_angle)
    open_start, open_end = opening.p0, opening.p1
    end_width = float(params["end_width"]) * abs(open_start[1] - open_end[1])
    end_width = max(end_width, float(params["wrist"]) / 2.0)
    opening_length = abs(open_start[0] - open_end[0])
    arm_width = abs(open_start[1] - open_end[1])
    length = max(float(params["sleeve_length"]) * (float(params["arm_length"]) - opening_length),
                 5.0)

    base_0 = (0.0, 0.0)
    base_1 = (0.0, -end_width)
    base_2 = (length, -arm_width)
    opening = _translate(opening, (base_2[0] - open_start[0], base_2[1] - open_start[1]))
    closing_start = opening.p1

    segments = [line_segment(base_0, base_1), line_segment(base_1, base_2), opening]
    if bool(params["standing_shoulder"]) \
            and rest_angle > shoulder_angle + math.radians(5.0):
        standing = float(params["standing_shoulder_len"])
        x_shift = standing * math.cos(rest_angle - shoulder_angle)
        y_shift = standing * math.sin(rest_angle - shoulder_angle)
        standing_edge = line_segment(
            closing_start, (closing_start[0] - x_shift, closing_start[1] + y_shift))
        segments.append(standing_edge)
        segments.append(line_segment(standing_edge.p1, base_0))
    else:
        segments.append(line_segment(closing_start, base_0))
    return segments_to_panel(name, segments, scale=CM_TO_MM)


def build(params: dict):
    shoulder_angle = math.radians(float(params["shoulder_incl"]))
    rest_angle = max(math.radians(float(params["sleeve_angle"])), shoulder_angle)
    opening = armhole_opening(
        float(params["armhole_incline"]), float(params["connecting_width"]),
        rest_angle, float(params["opening_dir_mix"]))
    return [_sleeve_panel("sleeve", opening, params)]
