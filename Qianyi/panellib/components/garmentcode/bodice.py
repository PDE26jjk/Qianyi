"""Fitted bodice preset, transcribed from GarmentCode's ``bodice.py``.

Source classes: ``BodiceFrontHalf`` and ``BodiceBackHalf``. Only the two
panel geometries are ported: the sleeves, collars and the corner projections
that the full ``Shirt`` adds are separate pieces.
"""

from __future__ import annotations

import math

from ._common import CM_TO_MM
from ._kernel import (Segment, curve_from_tangents, insert_notches, line_segment,
                      quad_segment, segments_to_panel)

COMPONENT_ID = "gc_fitted_bodice"
VERSION = 1
LABEL = "GC Fitted Bodice"
CATEGORY = "GarmentCode"
DESCRIPTION = ("GarmentCode fitted bodice: front and back half panels with side "
               "and waist darts.")

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "bust": {"type": "float", "unit": "cm", "min": 50.0, "max": 200.0,
                 "default": 99.8407, "label": "Bust"},
        "back_width": {"type": "float", "unit": "cm", "min": 20.0, "max": 100.0,
                       "default": 47.6761, "label": "Back Width"},
        "shoulder_w": {"type": "float", "unit": "cm", "min": 10.0, "max": 80.0,
                       "default": 36.4568, "label": "Shoulder Width"},
        "waist": {"type": "float", "unit": "cm", "min": 40.0, "max": 200.0,
                  "default": 84.3338, "label": "Waist"},
        "waist_back_width": {"type": "float", "unit": "cm", "min": 10.0, "max": 120.0,
                             "default": 39.1358, "label": "Back Waist Width"},
        "bust_points": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                        "default": 16.9463, "label": "Bust Points"},
        "bum_points": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                       "default": 18.2342, "label": "Bum Points"},
        "waist_line": {"type": "float", "unit": "cm", "min": 10.0, "max": 80.0,
                       "default": 36.8913, "label": "Waist Line"},
        "waist_over_bust_line": {"type": "float", "unit": "cm", "min": 10.0, "max": 90.0,
                                 "default": 40.5603, "label": "Waist Over Bust Line"},
        "shoulder_incl": {"type": "float", "unit": "deg", "min": 0.0, "max": 60.0,
                          "default": 21.6777, "label": "Shoulder Inclination"},
        "bust_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                      "default": 25.6947, "label": "Bust Line"},
        "vert_bust_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                           "default": 21.1388, "label": "Vertical Bust Line"},
    },
}


def _dart_height(side_length: float, width: float) -> float:
    """Perpendicular dart depth; GarmentCode passes the depth as side length."""
    return math.sqrt(max(side_length * side_length - (width / 2.0) ** 2, 0.0))


def _centroid(points):
    # Deliberate comprehension: a handful of 2D tuples, not a numeric array
    # worth materialising.
    return (sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points))


def _evaluated_bust_line(params) -> float:
    """GarmentCode's derived ``_bust_line`` body measurement."""
    return ((1.0 - 1.0 / 3.0) * float(params["vert_bust_line"])
            + 1.0 / 3.0 * float(params["bust_line"]))


def front_segments(params):
    bust = float(params["bust"])
    back_width = float(params["back_width"])
    shoulder_w = float(params["shoulder_w"])
    waist = float(params["waist"])
    waist_back_width = float(params["waist_back_width"])
    bust_points = float(params["bust_points"])
    waist_over_bust_line = float(params["waist_over_bust_line"])
    waist_line = float(params["waist_line"])
    shoulder_inclination = float(params["shoulder_incl"])
    body_bust_line = _evaluated_bust_line(params)

    front_fraction = ((bust - back_width) / 2.0) / bust if bust else 0.0
    width = front_fraction * bust
    panel_waist = (waist - waist_back_width) / 2.0
    shoulder_tan = math.tan(math.radians(shoulder_inclination))
    shoulder_length = shoulder_tan * width
    bottom_dart_width = (width - panel_waist) * 2.0 / 3.0
    adjustment = shoulder_tan * (width - shoulder_w / 2.0)
    max_length = waist_over_bust_line - adjustment
    front_back_difference = (front_fraction - (0.5 - front_fraction)) * bust
    back_adjustment = shoulder_tan * (back_width / 2.0 - shoulder_w / 2.0)
    side_length = waist_line - back_adjustment - shoulder_tan * front_back_difference
    bust_line = waist_line - body_bust_line
    side_dart_depth = 0.75 * (width - bust_points / 2.0)
    side_dart_width = max_length - side_length

    a = (0.0, 0.0)
    b = (-width, 0.0)
    c = (-width, max_length)
    d = (0.0, max_length + shoulder_length)
    interior = _centroid((a, b, c, d))

    bottom = insert_notches(
        line_segment(a, b),
        [(bust_points / 2.0 + bottom_dart_width / 2.0, bottom_dart_width,
          _dart_height(0.9 * bust_line, bottom_dart_width))],
        interior)
    side = insert_notches(
        line_segment(b, c),
        [(bust_line + side_dart_width / 2.0, side_dart_width,
          _dart_height(side_dart_depth, side_dart_width))],
        interior)

    b2 = (-(panel_waist + bottom_dart_width), 0.0)
    shoulder_shift = width - shoulder_w / 2.0
    c2 = (-width + shoulder_shift, max_length + shoulder_tan * shoulder_shift)
    bottom[-1] = Segment(bottom[-1].p0, b2, bottom[-1].curve)
    side[0] = Segment(b2, side[0].p1, side[0].curve)
    side[-1] = Segment(side[-1].p0, c2, side[-1].curve)

    return bottom + side + [line_segment(c2, d), line_segment(d, a)]


def back_segments(params):
    back_width = float(params["back_width"])
    shoulder_w = float(params["shoulder_w"])
    waist_back_width = float(params["waist_back_width"])
    bum_points = float(params["bum_points"])
    waist_line = float(params["waist_line"])
    shoulder_inclination = float(params["shoulder_incl"])
    body_bust_line = _evaluated_bust_line(params)

    width = back_width / 2.0
    panel_waist = waist_back_width / 2.0
    waist_width = max(width, panel_waist)
    shoulder_tan = math.tan(math.radians(shoulder_inclination))
    shoulder_length = shoulder_tan * width
    back_adjustment = shoulder_tan * (width - shoulder_w / 2.0)
    length = waist_line - back_adjustment

    p0 = (0.0, shoulder_length / 4.0)
    p1 = (-waist_width, 0.0)
    control = curve_from_tangents(p0, p1, tan0=(-1.0, 0.0))
    waist_edge = quad_segment(p0, p1, control)

    tail_1 = (-width, waist_line - body_bust_line)
    tail_2 = (-width, length)
    tail_3 = (0.0, length + shoulder_length)
    tail = [line_segment(p1, tail_1), line_segment(tail_1, tail_2),
            line_segment(tail_2, tail_3)]
    closing = line_segment(tail_3, p0)
    interior = _centroid((p0, p1, tail_1, tail_2, tail_3))

    if panel_waist < width:
        difference = waist_width - panel_waist
        side_adjustment = 0.0 if difference < 4.0 else difference / 6.0
        dart_width = (difference - side_adjustment) / 2.0
        dart_depth = length - body_bust_line
        position = bum_points / 2.0
        distance = position * 0.5
        outer_center = position + distance / 2.0 + dart_width + dart_width / 2.0
        inner_center = position - distance / 2.0 + dart_width / 2.0
        pieces = insert_notches(
            waist_edge,
            [(outer_center, dart_width, _dart_height(0.9 * dart_depth, dart_width))],
            interior)
        leading = insert_notches(
            pieces[0],
            [(inner_center, dart_width, _dart_height(dart_depth, dart_width))],
            interior)
        pieces = leading + pieces[1:]
        p1 = (-waist_width + side_adjustment, 0.0)
        pieces[-1] = Segment(pieces[-1].p0, p1, pieces[-1].curve)
        tail[0] = Segment(p1, tail[0].p1, tail[0].curve)
    else:
        pieces = [waist_edge]

    return pieces + tail + [closing]


def build(params: dict):
    return [segments_to_panel("bodice_front_half", front_segments(params), scale=CM_TO_MM),
            segments_to_panel("bodice_back_half", back_segments(params), scale=CM_TO_MM)]
