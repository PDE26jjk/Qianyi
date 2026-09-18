"""Pants half preset, transcribed from GarmentCode's ``pants.py``.

Source classes: ``PantsHalf`` and ``PantPanel``. The preset produces the right
half (front and back); the left half is its mirror.
Only panel geometry is ported: cuffs and placement are left out.
"""

from __future__ import annotations

import math

from ._common import CM_TO_MM, lerp
from ._kernel import (curve_from_tangents, insert_notches, line_segment,
                      quad_segment, segments_to_panel)

COMPONENT_ID = "gc_pants"
VERSION = 1
LABEL = "GC Pants (Right Half)"
CATEGORY = "GarmentCode"
DESCRIPTION = ("GarmentCode PantsHalf: the right front and back pant panels; "
               "mirror them for the left half.")

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "hips": {"type": "float", "unit": "cm", "min": 50.0, "max": 220.0,
                 "default": 103.478, "label": "Hips"},
        "hip_back_width": {"type": "float", "unit": "cm", "min": 10.0, "max": 140.0,
                           "default": 54.8237, "label": "Back Hip Width"},
        "waist": {"type": "float", "unit": "cm", "min": 40.0, "max": 200.0,
                  "default": 84.3338, "label": "Waist"},
        "waist_back_width": {"type": "float", "unit": "cm", "min": 10.0, "max": 120.0,
                             "default": 39.1358, "label": "Back Waist Width"},
        "hips_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                      "default": 23.4837, "label": "Hip Line"},
        "leg_length": {"type": "float", "unit": "cm", "min": 20.0, "max": 150.0,
                       "default": 85.2888, "label": "Leg Length"},
        "leg_circ": {"type": "float", "unit": "cm", "min": 20.0, "max": 120.0,
                     "default": 60.2039, "label": "Leg Circumference"},
        "crotch_hip_diff": {"type": "float", "unit": "cm", "min": 0.0, "max": 40.0,
                            "default": 8.81363, "label": "Crotch-Hip Difference"},
        "hip_inclination": {"type": "float", "unit": "deg", "min": 0.0, "max": 40.0,
                            "default": 9.86489, "label": "Hip Inclination"},
        "bust_points": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                        "default": 16.9463, "label": "Bust Points"},
        "bum_points": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                       "default": 18.2342, "label": "Bum Points"},
        "rise": {"type": "float", "unit": "fraction", "min": 0.5, "max": 1.0,
                 "default": 1.0, "label": "Rise"},
        "pants_length": {"type": "float", "unit": "x", "min": 0.2, "max": 0.9,
                         "default": 0.3, "label": "Length"},
        "crotch_width": {"type": "float", "unit": "x", "min": 1.0, "max": 1.5,
                         "default": 1.0, "label": "Crotch Width"},
        "flare": {"type": "float", "unit": "x", "min": 0.5, "max": 1.2,
                  "default": 1.0, "label": "Flare"},
    },
}


def _dart_height(side_length: float, width: float) -> float:
    """Perpendicular dart depth; GarmentCode passes the depth as side length."""
    return math.sqrt(max(side_length * side_length - (width / 2.0) ** 2, 0.0))


def _centroid(points):
    # Deliberate comprehension: a handful of 2D tuples.
    return (sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points))


def _pant_panel(name, length, waist, hips, hips_depth, crotch_width, dart_position,
                dart_frac, double_dart, hipline_ext, hip_inclination, leg_circ,
                crotch_hip_diff, flare_frac):
    flare = leg_circ * (flare_frac - 1.0) / 4.0
    adjusted_hips_depth = hips_depth * hipline_ext
    hip_side_inclination = math.radians(hip_inclination / 2.0)
    dart_depth = adjusted_hips_depth * dart_frac
    difference = hips - waist
    side_shift = math.tan(hip_side_inclination) * adjusted_hips_depth
    if side_shift > difference:
        side_shift = difference

    a = (-flare, 0.0)
    b = (0.0, length)
    c = (side_shift, length + adjusted_hips_depth)
    d = (difference + waist, length + adjusted_hips_depth)
    e = (hips, length + 0.45 * adjusted_hips_depth)
    f = (hips + crotch_width, length - crotch_hip_diff)
    g = (f[0] - 2.0 + flare, min(0.0, length - crotch_hip_diff * 1.5))

    if abs(flare) <= 1e-9:
        right_bottom = line_segment(a, b)
    else:
        control = curve_from_tangents(a, b, tan1=(0.0, 1.0), guess=(0.75, 0.0))
        right_bottom = quad_segment(a, b, control)
    right_top = quad_segment(
        b, c, curve_from_tangents(b, c, tan0=(0.0, 1.0), guess=(0.5, 0.0)))
    crotch_bottom = quad_segment(
        e, f, curve_from_tangents(e, f, tan0=(0.0, -1.0), tan1=(1.0, 0.0),
                                  guess=(0.5, -0.5)))
    left_control = curve_from_tangents(
        f, g, tan1=(flare, g[1] - f[1]), guess=(0.3, 0.0))
    left = quad_segment(f, g, left_control)
    bottom = line_segment(g, a)

    interior = _centroid((a, b, c, d, e, f, g))
    if difference > side_shift:
        dart_width = difference - side_shift
        top_length = math.dist(c, d)
        if double_dart:
            distance = dart_position * 0.5
            offsets = [-(dart_position + distance / 2.0 + dart_width / 2.0 + dart_width / 4.0),
                       -(dart_position - distance / 2.0) - dart_width / 4.0]
            widths = [dart_width / 2.0, dart_width / 2.0]
            sides = [dart_depth * 0.9, dart_depth]
        else:
            offsets = [-(dart_position + dart_width / 2.0)]
            widths = [dart_width]
            sides = [dart_depth]
        depths = [_dart_height(side, width) for side, width in zip(sides, widths)]
        # Deliberate comprehension: one (centre, width, depth) record per dart.
        notches = [(top_length + offset, width, depth)
                   for offset, width, depth in zip(offsets, widths, depths)]
        top = insert_notches(line_segment(c, d), notches, interior)
    else:
        top = [line_segment(c, d)]

    segments = ([right_bottom, right_top] + top
                + [line_segment(d, e), crotch_bottom, left, bottom])
    edge_names = {0: "right_lower", 1: "right_upper",
                  2 + len(top) + 2: "left"}
    return segments_to_panel(name, segments, scale=CM_TO_MM, edge_names=edge_names)


def seams(params: dict, panels):
    """The outside and inside leg seams of the pants half."""
    return [
        ("pant_front", "right_lower", "pant_back", "right_lower"),
        ("pant_front", "right_upper", "pant_back", "right_upper"),
        ("pant_front", "left", "pant_back", "left"),
    ]


def build(params: dict):
    hips = float(params["hips"])
    hip_back_width = float(params["hip_back_width"])
    waist = float(params["waist"])
    waist_back_width = float(params["waist_back_width"])
    hips_line = float(params["hips_line"])
    leg_length = float(params["leg_length"])
    leg_circ = float(params["leg_circ"])
    crotch_hip_diff = float(params["crotch_hip_diff"])
    hip_inclination = float(params["hip_inclination"])
    bust_points = float(params["bust_points"])
    bum_points = float(params["bum_points"])
    rise = float(params["rise"])

    adjusted_waist = lerp(hips, waist, rise)
    adjusted_hips_depth = rise * hips_line
    adjusted_back_waist = lerp(hip_back_width, waist_back_width, rise)
    length = float(params["pants_length"]) * leg_length

    minimum_extension = leg_circ - hips / 2.0 + 5.0
    front_hip = (hips - hip_back_width) / 2.0
    crotch_extension = minimum_extension * float(params["crotch_width"])
    front_extension = front_hip / 4.0
    back_extension = crotch_extension - front_extension

    return [
        _pant_panel("pant_front", length,
                    waist=(adjusted_waist - adjusted_back_waist) / 2.0,
                    hips=(hips - hip_back_width) / 2.0,
                    hips_depth=adjusted_hips_depth, crotch_width=front_extension,
                    dart_position=bust_points / 2.0, dart_frac=0.8,
                    double_dart=False, hipline_ext=1.0,
                    hip_inclination=hip_inclination, leg_circ=leg_circ,
                    crotch_hip_diff=crotch_hip_diff,
                    flare_frac=float(params["flare"])),
        _pant_panel("pant_back", length,
                    waist=adjusted_back_waist / 2.0,
                    hips=hip_back_width / 2.0,
                    hips_depth=adjusted_hips_depth, crotch_width=back_extension,
                    dart_position=bum_points / 2.0, dart_frac=0.8,
                    double_dart=True, hipline_ext=1.1,
                    hip_inclination=hip_inclination, leg_circ=leg_circ,
                    crotch_hip_diff=crotch_hip_diff,
                    flare_frac=float(params["flare"])),
    ]
